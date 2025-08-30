from macats.event_bus import Event, EventBus

class RiskAgent:
    def __init__(self, bus: EventBus, balance: float = 10000):
        self.bus = bus
        self.balance = balance

    async def run(self):
        sub = self.bus.subscribe("signals.target")
        async for e in sub:
            side = e.payload["side"]
            strength = e.payload["strength"]
            qty = 0.0 if side == "flat" or strength <= 0 else round(self.balance * 0.01 * strength, 2)
            await self.bus.publish(Event(topic="orders.planned", payload={"side": side, "qty": qty}))