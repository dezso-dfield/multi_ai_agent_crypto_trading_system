# macats/agents/council_agent.py
from macats.event_bus import Event, EventBus

DIR = {"long": 1, "short": -1, "flat": 0}

class CouncilAgent:
    """
    Combines LLM analyst votes into a single action.
    Weights: tech 0.5, sentiment 0.3, macro 0.2 (tweak as you like).
    Emits 'signals.target' with side + strength 0..1
    """
    def __init__(self, bus: EventBus, w_tech=0.5, w_sent=0.3, w_macro=0.2):
        self.bus = bus
        self.w = (w_tech, w_sent, w_macro)

    async def run(self):
        sub = self.bus.subscribe("analysis.result")
        async for e in sub:
            d = e.payload
            tech, sent, macro = d["technical"], d["sentiment"], d["macro"]
            w_tech, w_sent, w_macro = self.w

            def score(x):
                side = x.get("signal","flat").lower()
                conf = float(x.get("confidence", 0.0))
                return DIR.get(side, 0) * max(0.0, min(conf, 1.0))

            s = w_tech*score(tech) + w_sent*score(sent) + w_macro*score(macro)

            # Map s -> final side & strength
            if s > 0.1:
                side, strength = "long", min(1.0, s)
            elif s < -0.1:
                side, strength = "short", min(1.0, -s)
            else:
                side, strength = "flat", 0.0

            await self.bus.publish(Event(topic="strategy.log", payload={"note": f"Council s={s:.3f}", "votes": {"tech":tech,"sent":sent,"macro":macro}}))
            await self.bus.publish(Event(topic="signals.target", payload={"side": side, "strength": strength}))