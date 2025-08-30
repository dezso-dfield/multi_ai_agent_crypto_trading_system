# macats/agents/ta_strategy_agent.py
import asyncio
import math
import pandas as pd
from macats.event_bus import Event, EventBus

class TAStrategyAgent:
    """
    TA-only strategy:
      - Trend filter: SMA(20) vs SMA(50)
      - Momentum/Exits: RSI bands (flat when overbought/oversold)
      - Vol context: ATR/Close to scale conviction
    Emits: {"side": "long|short|flat", "strength": 0..1}
    """
    def __init__(self, bus: EventBus):
        self.bus = bus

    def _decide(self, row: pd.Series) -> dict:
        c = float(row["c"])
        sma_fast = float(row["sma_fast"])
        sma_slow = float(row["sma_slow"])
        rsi = float(row["rsi"])
        atr = float(row["atr"])

        # Exit to flat on extreme RSI (overbought/oversold)
        if rsi >= 70 or rsi <= 30:
            return {"side": "flat", "strength": 0.0, "why": f"RSI={rsi:.1f} extreme"}

        # Trend direction via MA cross
        if sma_fast > sma_slow:
            base_side = "long"
        elif sma_fast < sma_slow:
            base_side = "short"
        else:
            return {"side": "flat", "strength": 0.0, "why": "MAs equal"}

        # Conviction from MA separation (normalized) and RSI’s distance to 50
        ma_sep = abs(sma_fast - sma_slow) / max(c, 1e-9)           # 0..~%
        rsi_pulse = abs(rsi - 50.0) / 50.0                          # 0..1
        vol_norm = min((atr / max(c,1e-9)) / 0.02, 1.0)             # ATR 2%+ caps

        raw_strength = 0.5 * min(ma_sep * 50.0, 1.0) + 0.5 * min(rsi_pulse, 1.0)
        strength = float(max(0.0, min(raw_strength * (0.75 + 0.25*vol_norm), 1.0)))

        return {"side": base_side, "strength": strength, "why": f"trend={base_side}, rsi={rsi:.1f}"}

    async def run(self):
        sub = self.bus.subscribe("market.features")
        async for e in sub:
            df: pd.DataFrame = e.payload["df"]
            latest = df.iloc[-1]
            sig = self._decide(latest)
            await self.bus.publish(Event(topic="strategy.log", payload={"note": f"TA decision: {sig}"}))
            await self.bus.publish(Event(topic="signals.target", payload={"side": sig["side"], "strength": sig["strength"]}))
            # For a live loop, you could sleep and re-emit on a schedule; for demo, one-shot is fine.