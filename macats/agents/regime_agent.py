from macats.event_bus import Event

class RegimeAgent:
    def __init__(self, bus):
        self.bus = bus

    async def run(self):
        sub = self.bus.subscribe("market.features")
        async for e in sub:
            df = e.payload["df"]
            latest = df.iloc[-1]

            # ✅ robust scalar extraction
            fast  = latest["sma_fast"].item()
            slow  = latest["sma_slow"].item()
            atr   = latest["atr"].item()
            close = latest["c"].item()

            trend = "trend_up" if fast > slow else ("trend_down" if fast < slow else "flat")
            vol   = "high_vol" if (atr / close) > 0.01 else "low_vol"
            regime = f"{trend}:{vol}"

            await self.bus.publish(Event(topic="regime.current",
                                         payload={"regime": regime, "price": float(close)}))
            break