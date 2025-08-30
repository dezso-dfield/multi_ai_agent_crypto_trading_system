import asyncio
from macats.event_bus import Event
from macats.data.market import load_ohlcv, indicators
from macats.config import SETTINGS

class TechAgent:
    def __init__(self, bus, yf_symbol=None, interval=None, lookback="60d", exchange_id=None):
        self.bus = bus
        self.symbol = yf_symbol or SETTINGS.symbol
        self.interval = interval or SETTINGS.timeframe
        self.lookback = lookback
        self.exchange_id = exchange_id or SETTINGS.exchange_id

    async def run(self):
        while True:
            try:
                df = load_ohlcv(
                    symbol=self.symbol,
                    interval=self.interval,
                    lookback=self.lookback,
                    exchange_id=self.exchange_id,
                )
                feats = indicators(df).tail(500)
                await self.bus.publish(Event(topic="market.features", payload={"df": feats}))
            except Exception as e:
                await self.bus.publish(Event(topic="strategy.log", payload={"note": f"TechAgent error: {e}"}))
            await asyncio.sleep(10)  # adjust cadence as you like