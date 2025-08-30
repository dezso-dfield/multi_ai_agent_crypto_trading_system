import asyncio
from macats.event_bus import Event, EventBus

class StrategyAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def run(self):
        sub_r = self.bus.subscribe("regime.current")
        sub_s = self.bus.subscribe("sentiment.raw")

        regime = None
        sentiment_window = []

        async def handle_regime():
            nonlocal regime
            async for e in sub_r:
                regime = e.payload["regime"]
                await self.bus.publish(Event(topic="strategy.log", payload={"note": f"Regime={regime}"}))
                break

        async def handle_sentiment():
            nonlocal regime
            async for e in sub_s:
                sentiment_window.append(e.payload["score"])
                if len(sentiment_window) >= 8:
                    s = sum(sentiment_window[-8:])
                    if regime and "trend_up" in regime and s > 0:
                        sig = {"side": "long", "strength": min(1.0, 0.1 + 0.1*s)}
                    elif regime and "trend_down" in regime and s < 0:
                        sig = {"side": "short", "strength": min(1.0, 0.1 + 0.1*(-s))}
                    else:
                        sig = {"side": "flat", "strength": 0.0}
                    await self.bus.publish(Event(topic="signals.target", payload=sig))

        await asyncio.gather(handle_regime(), handle_sentiment())