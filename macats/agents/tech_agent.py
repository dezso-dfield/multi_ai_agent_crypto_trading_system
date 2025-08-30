import asyncio
import pandas as pd
import yfinance as yf
from macats.event_bus import Event, EventBus

def indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower).rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'}).dropna()
    df["sma_fast"] = df["c"].rolling(20).mean()
    df["sma_slow"] = df["c"].rolling(50).mean()
    r = df["c"].pct_change().fillna(0)
    up = r.clip(lower=0).rolling(14).mean()
    down = (-r.clip(upper=0)).rolling(14).mean().replace(0, 1e-9)
    rs = up / down
    df["rsi"] = 100 - (100 / (1 + rs))
    df["atr"] = (df["h"] - df["l"]).rolling(14).mean()
    return df.dropna()

class TechAgent:
    def __init__(self, bus: EventBus, yf_symbol="BTC-USD", interval="1h", lookback="60d"):
        self.bus = bus
        self.yf_symbol = yf_symbol
        self.interval = interval
        self.lookback = lookback

    async def run(self):
        df = yf.download(
            self.yf_symbol,
            interval=self.interval,
            period=self.lookback,
            auto_adjust=False,      # add this line
            progress=False,
        )
        feats = indicators(df).tail(500)
        await self.bus.publish(Event(topic="market.features", payload={"df": feats}))
        await asyncio.sleep(0)  # one-shot for demo