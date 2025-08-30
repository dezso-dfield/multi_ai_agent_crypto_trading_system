import pandas as pd
import yfinance as yf

def load_ohlcv(symbol="BTC-USD", interval="1h", lookback="60d") -> pd.DataFrame:
    """
    Fetch OHLCV data from Yahoo Finance.
    Columns: o,h,l,c,v
    """
    df = yf.download(
        tickers=symbol,
        interval=interval,
        period=lookback,
        auto_adjust=False,
        progress=False,
    )
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("No data returned from yfinance")

    df = df.rename(columns=str.lower)
    df = df.rename(columns={
        "open": "o",
        "high": "h",
        "low": "l",
        "close": "c",
        "volume": "v",
    })
    return df.dropna()