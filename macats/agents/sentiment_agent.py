import asyncio, random, time, re
from macats.event_bus import Event
from macats.event_bus import EventBus

POS = {"moon","pump","breakout","bullish","rocket","win","long"}
NEG = {"dump","bearish","rug","short","liquidate","fear","crash"}

class SentimentAgent:
    def __init__(self, bus):
        self.bus = bus

    def _toy_stream(self):
        import random, time, re
        samples = [
            "BTC looks bullish, breakout soon?",
            "Funding too high, crash coming",
            "ETH on a rocket, careful at resistance",
            "Chop city. Staying flat.",
            "Bearish div on 4h, likely dump",
            "Macro improving, DXY down, risk on",
        ]
        while True:
            text = random.choice(samples)
            toks = re.findall(r"[a-z]+", text.lower())
            # ✅ correct membership checks:
            score = sum(1 for t in toks if t in POS) - sum(1 for t in toks if t in NEG)
            yield {"ts": time.time(), "text": text, "score": float(score)}

    async def run(self):
        import asyncio
        for msg in self._toy_stream():
            await self.bus.publish(Event(topic="sentiment.raw", payload=msg))
            await asyncio.sleep(0.2)