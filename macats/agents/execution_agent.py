from macats.event_bus import Event, EventBus

class ExecutionAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def run(self):
        sub = self.bus.subscribe("orders.planned")
        async for e in sub:
            order = e.payload
            # Paper “fill” for now
            await self.bus.publish(Event(topic="exec.fills", payload={"status": "filled", **order}))