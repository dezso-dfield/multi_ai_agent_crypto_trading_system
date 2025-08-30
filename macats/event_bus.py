import asyncio
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class Event:
    topic: str
    payload: Dict[str, Any]

class EventBus:
    def __init__(self):
        self.queues: dict[str, asyncio.Queue] = {}

    def topic(self, name: str) -> asyncio.Queue:
        if name not in self.queues:
            self.queues[name] = asyncio.Queue()
        return self.queues[name]

    async def publish(self, event: Event):
        await self.topic(event.topic).put(event)

    async def subscribe(self, name: str):
        q = self.topic(name)
        while True:
            yield await q.get()