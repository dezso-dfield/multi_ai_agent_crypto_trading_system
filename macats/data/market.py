import pandas as pd
import yfinance as yf
import ccxt

COMMON_QUOTES = ["USDT", "USDC", "BUSD", "USD"]

def _normalize_to_yf(symbol: str) -> str | None:
    """
    Try to convert common crypto symbols to Yahoo Finance format.
    Examples:
      BTC/USDT -> BTC-USD
      BTCUSDT  -> BTC-USD
      ETH-USD  -> ETH-USD (already fine)
    Returns None if we can't be sure.
    """
    s = symbol.strip()
    if "-" in s and s.endswith("USD"):
        return s  # looks like ETH-USD, BTC-USD

    # BTC/USDT style
    if "/" in s:
        base, quote = s.split("/", 1)
        quote = quote.upper()
        if quote in ("USDT", "USDC", "BUSD", "USD"):
            return f"{base.upper()}-USD"

    # BTCUSDT style
    upper = s.upper()
    for q in COMMON_QUOTES:
        if upper.endswith(q):
            base = upper[: -len(q)]
            if q in ("USDT", "USDC", "BUSD", "USD"):
                return f"{base}-USD"

    # Unknown
    return None

def _yf_download(yf_symbol: str, interval: str, lookback: str) -> pd.DataFrame:
    df = yf.download(
        tickers=yf_symbol,
        interval=interval,
        period=lookback,
        auto_adjust=False,
        progress=False,
    )
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError(f"No data returned from yfinance for {yf_symbol}")
    df = df.rename(columns=str.lower)
    df = df.rename(columns={"open":"o","high":"h","low":"l","close":"c","volume":"v"})
    return df.dropna()

def _ccxt_download(exchange_id: str, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """
    Fetch OHLCV via CCXT (public). symbol must be exchange-style, e.g. 'BTC/USDT'.
    """
    if not hasattr(ccxt, exchange_id):
        raise ValueError(f"Unknown exchange_id: {exchange_id}")
    ex = getattr(ccxt, exchange_id)()
    # Ensure market is known
    markets = ex.load_markets()
    if symbol not in markets:
        # try to coerce BTCUSDT -> BTC/USDT
        if "/" not in symbol and symbol.upper().endswith(("USDT","USDC","BUSD","USD")):
            for q in COMMON_QUOTES:
                if symbol.upper().endswith(q):
                    base = symbol.upper()[:-len(q)]
                    guess = f"{base}/{q}"
                    if guess in markets:
                        symbol = guess
                        break
        if symbol not in markets:
            raise ValueError(f"Symbol {symbol} not found on {exchange_id}")

    ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if not ohlcv:
        raise ValueError(f"No OHLCV from {exchange_id} for {symbol}")
    df = pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("ts").sort_index()
    return df.dropna()

def load_ohlcv(symbol: str = "BTC-USD",
               interval: str = "1h",
               lookback: str = "60d",
               exchange_id: str = "binance") -> pd.DataFrame:
    """
    Try Yahoo Finance first (after normalizing symbol), then fall back to CCXT.
    For CCXT we use `exchange_id` and assume `symbol` is exchange-style (BTC/USDT or BTCUSDT).
    """
    # 1) Try Yahoo Finance
    yf_sym = _normalize_to_yf(symbol) or (symbol if "-" in symbol else None)
    if yf_sym:
        try:
            return _yf_download(yf_sym, interval, lookback)
        except Exception as e:
            # fall through to CCXT
            pass

    # 2) Fallback to CCXT (ensure exchange-style symbol)
    ex_symbol = symbol
    if "/" not in ex_symbol and ex_symbol.upper().endswith(tuple(COMMON_QUOTES)):
        for q in COMMON_QUOTES:
            if ex_symbol.upper().endswith(q):
                base = ex_symbol.upper()[:-len(q)]
                ex_symbol = f"{base}/{q}"
                break
    return _ccxt_download(exchange_id, ex_symbol, interval)

def indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute basic TA features used by downstream agents.
    Adds: sma_fast, sma_slow, rsi, atr
    """
    d = df.copy()
    d["sma_fast"] = d["c"].rolling(20).mean()
    d["sma_slow"] = d["c"].rolling(50).mean()

    r = d["c"].pct_change().fillna(0.0)
    up = r.clip(lower=0).rolling(14).mean()
    down = (-r.clip(upper=0)).rolling(14).mean().replace(0, 1e-9)
    rs = up / down
    d["rsi"] = 100 - (100 / (1 + rs))

    # simple ATR proxy
    d["atr"] = (d["h"] - d["l"]).rolling(14).mean()

    return d.dropna()