import asyncio
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from macats.event_bus import Event, EventBus
from macats.data.market import load_ohlcv, indicators
from macats.config import SETTINGS


@dataclass
class FSVZOParams:
    vol_mult: float = 2.0        # Volume anomaly threshold vs SMA(20)
    zone_pct: float = 0.003      # “near zone” within 0.3%
    atr_mult_sl: float = 1.5     # SL distance in ATRs
    r_multiple_tp: float = 1.0   # TP at 1R (can trail)
    min_confluence: int = 3      # trade if >=3 out of F,S,V,Z,O


def _latest(df: pd.DataFrame, col: str) -> float:
    """Return the last scalar value of df[col] as float."""
    val = df[col].iloc[-1]
    # in case it's a 0-dim array/Series, item() handles it
    try:
        return float(getattr(val, "item", lambda: val)())
    except Exception:
        return float(val)


def _volume_anomaly(df: pd.DataFrame, mult: float) -> bool:
    v = _latest(df, "v")
    v_sma = float(df["v"].rolling(20).mean().iloc[-1])
    return bool(v > mult * v_sma)


def _key_zones(df: pd.DataFrame) -> Dict[str, float]:
    # Simple zones: lookback window highs/lows and prior pivot
    d1 = df.tail(48).copy()
    yh = float(d1["h"].max())
    yl = float(d1["l"].min())
    # prior bar pivot
    if len(df) >= 2:
        prior = df.iloc[-2]
        pivot = float((prior["h"] + prior["l"] + prior["c"]) / 3.0)
    else:
        pivot = float((yh + yl) / 2.0)
    return {"y_high": yh, "y_low": yl, "pivot": pivot}


def _near_zone(price: float, zones: Dict[str, float], tol_pct: float) -> bool:
    for z in zones.values():
        if z != 0 and abs(price - z) / abs(z) <= tol_pct:
            return True
    return False


def _overlay_long(df: pd.DataFrame) -> bool:
    c = _latest(df, "c")
    # EMAs and BB mid as scalars
    ema_fast = float(df["c"].ewm(span=20, min_periods=20).mean().iloc[-1])
    ema_slow = float(df["c"].ewm(span=50, min_periods=50).mean().iloc[-1])
    bb_mid   = float(df["c"].rolling(20).mean().iloc[-1])
    # RSI trend up?
    rsi_now = _latest(df, "rsi")
    rsi_prev = float(df["rsi"].iloc[-3:-1].mean()) if len(df) >= 3 else rsi_now
    return bool((ema_fast > ema_slow) and (c > bb_mid) and (rsi_now >= rsi_prev))


def _overlay_short(df: pd.DataFrame) -> bool:
    c = _latest(df, "c")
    ema_fast = float(df["c"].ewm(span=20, min_periods=20).mean().iloc[-1])
    ema_slow = float(df["c"].ewm(span=50, min_periods=50).mean().iloc[-1])
    bb_mid   = float(df["c"].rolling(20).mean().iloc[-1])
    rsi_now = _latest(df, "rsi")
    rsi_prev = float(df["rsi"].iloc[-3:-1].mean()) if len(df) >= 3 else rsi_now
    return bool((ema_fast < ema_slow) and (c < bb_mid) and (rsi_now <= rsi_prev))


def _sentiment_proxy_long(df: pd.DataFrame) -> bool:
    rsi_now = _latest(df, "rsi")
    rsi_prev = float(df["rsi"].iloc[-3:-1].mean()) if len(df) >= 3 else rsi_now
    return bool((rsi_now < 40.0) and (rsi_now > rsi_prev))


def _sentiment_proxy_short(df: pd.DataFrame) -> bool:
    rsi_now = _latest(df, "rsi")
    rsi_prev = float(df["rsi"].iloc[-3:-1].mean()) if len(df) >= 3 else rsi_now
    return bool((rsi_now > 60.0) and (rsi_now < rsi_prev))


def _direction(df: pd.DataFrame) -> str:
    sma_fast = _latest(df, "sma_fast")
    sma_slow = _latest(df, "sma_slow")
    if sma_fast > sma_slow:
        return "long"
    if sma_fast < sma_slow:
        return "short"
    return "flat"


class FSVZOScannerAgent:
    """
    Scans a universe of symbols and emits trade signals when FSVZO confluence >= min_confluence.
    Emits:
      - strategy.log  (informational)
      - market.last   {"symbol","price"}  (so PortfolioAgent can MTM)
      - signals.target {"symbol","side","strength","sl_price","tp_price","atr"}
    """

    def __init__(self, bus: EventBus, params: FSVZOParams | None = None):
        self.bus = bus
        self.params = params or FSVZOParams()
        self.universe: List[str] = [s.strip() for s in getattr(SETTINGS, "universe", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT,DOGE/USDT,AVAX/USDT,DOT/USDT,MATIC/USDT,TRX/USDT,LINK/USDT,ATOM/USDT,LTC/USDT,UNI/USDT,ETC/USDT,XMR/USDT,APT/USDT,ARB/USDT,NEAR/USDT,OP/USDT,HBAR/USDT,ICP/USDT,FIL/USDT,STX/USDT,SUI/USDT,ALGO/USDT,VET/USDT,MKR/USDT,GRT/USDT,SAND/USDT,AXS/USDT,AAVE/USDT,RUNE/USDT,THETA/USDT,EGLD/USDT,KAVA/USDT,INJ/USDT,CRV/USDT,FTM/USDT,DYDX/USDT,LDO/USDT,GMX/USDT,ENS/USDT,CHZ/USDT,COMP/USDT,1INCH/USDT,BAL/USDT,ZIL/USDT,FLR/USDT").split(",")]
        self.exchange_id = SETTINGS.exchange_id
        self.interval = SETTINGS.timeframe
        self.lookback = "7d"

    def _evaluate(self, sym: str, df: pd.DataFrame) -> Tuple[str, Dict]:
        df = indicators(df)

        # === latest scalars ===
        price = _latest(df, "c")
        atr   = _latest(df, "atr")

        # Signals
        v = _volume_anomaly(df, self.params.vol_mult)
        zones = _key_zones(df)
        z = _near_zone(price, zones, self.params.zone_pct)
        bias = _direction(df)

        if bias == "long":
            o = _overlay_long(df)
            s = _sentiment_proxy_long(df)
            side = "long"
        elif bias == "short":
            o = _overlay_short(df)
            s = _sentiment_proxy_short(df)
            side = "short"
        else:
            # No clear bias: require strong confluence in either direction
            long_o = _overlay_long(df)
            short_o = _overlay_short(df)
            if long_o and z and v:
                side = "long"; o = True; s = _sentiment_proxy_long(df)
            elif short_o and z and v:
                side = "short"; o = True; s = _sentiment_proxy_short(df)
            else:
                return "flat", {"why": "no bias", "price": price}

        # Fundamental (F) hook — off by default
        f = False

        # All are plain booleans now
        score = int(bool(f)) + int(bool(s)) + int(bool(v)) + int(bool(z)) + int(bool(o))

        if score >= self.params.min_confluence:
            sl_dist = self.params.atr_mult_sl * atr
            if side == "long":
                sl_price = price - sl_dist
                tp_price = price + self.params.r_multiple_tp * sl_dist
            else:
                sl_price = price + sl_dist
                tp_price = price - self.params.r_multiple_tp * sl_dist

            strength = min(1.0, 0.6 + 0.1 * (score - self.params.min_confluence))  # small boost
            detail = {
                "score": score,
                "price": price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "atr": atr,
                "zones": zones,
                "signals": {"F": f, "S": s, "V": v, "Z": z, "O": o},
            }
            return side, detail

        return "flat", {"score": score, "price": price, "signals": {"F": f, "S": s, "V": v, "Z": z, "O": o}}

    async def run(self):
        while True:
            for sym in self.universe:
                try:
                    df = load_ohlcv(symbol=sym, interval=self.interval, lookback=self.lookback, exchange_id=self.exchange_id)
                    side, detail = self._evaluate(sym, df)

                    # publish latest price for PortfolioAgent mark-to-market
                    await self.bus.publish(Event(topic="market.last", payload={"symbol": sym, "price": float(detail.get("price", float(df['c'].iloc[-1]))) }))

                    note = {"symbol": sym, **detail}
                    await self.bus.publish(Event(topic="strategy.log", payload={"note": f"FSVZO scan {sym}: {side}", **note}))

                    if side != "flat":
                        await self.bus.publish(Event(topic="signals.target", payload={
                            "symbol": sym,
                            "side": side,
                            "strength": float(min(1.0, 0.8)),   # base strength; tune or derive from score
                            "sl_price": detail["sl_price"],
                            "tp_price": detail["tp_price"],
                            "atr": detail["atr"],
                        }))
                except Exception as e:
                    await self.bus.publish(Event(topic="strategy.log", payload={"note": f"FSVZO error {sym}: {e}"}))
                await asyncio.sleep(0)  # yield between symbols

            await asyncio.sleep(20)     # rescan cadence