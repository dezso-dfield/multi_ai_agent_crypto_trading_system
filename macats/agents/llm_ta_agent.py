# macats/agents/llm_ta_agent.py
import asyncio
import pandas as pd
from typing import Dict
from macats.event_bus import Event, EventBus
from macats.llm.providers import get_llm

SYSTEM = (
    "You are a disciplined technical analyst. Return ONLY JSON.\n"
    'Schema: {"signal":"long|short|flat","confidence":0..1,"rationale":string,'
    '"stop_loss_bps":int,"take_profit_bps":int}'
)

def df_to_csv(df: pd.DataFrame) -> str:
    d = df[["c","sma_fast","sma_slow","rsi","atr"]].tail(60).copy()
    d.index = d.index.astype(str)
    return d.to_csv(index=True)

class LLMTAStrategyAgent:
    def __init__(self, bus: EventBus): 
        self.bus = bus

    async def run(self):
        sub = self.bus.subscribe("market.features")
        async for e in sub:
            df: pd.DataFrame = e.payload["df"]
            # --- robust scalar extraction from the latest bar ---
            last = df[["c","sma_fast","sma_slow","rsi","atr"]].iloc[-1]
            # convert all five to plain floats in one shot
            c, sma_fast, sma_slow, rsi, atr = (
                last.astype("float64").to_numpy().tolist()
            )
            # guard division by zero
            atr_ratio = float(atr) / float(c) if c else 0.0

            csv_block = df_to_csv(df)
            context = {
                "price": float(c),
                "sma_fast": float(sma_fast),
                "sma_slow": float(sma_slow),
                "rsi": float(rsi),
                "atr_ratio": float(atr_ratio),
            }

            user = (
                "Recent TA features (CSV with index timestamps):\n\n"
                + csv_block
                + f"\nLatest snapshot: {context}\nReturn JSON only."
            )

            llm = await get_llm()
            try:
                resp: Dict = await llm.chat_json(SYSTEM, user)
                signal = resp.get("signal", "flat")
                conf = resp.get("confidence", 0.0)
                try:
                    conf = float(conf)
                except Exception:
                    conf = 0.0
                conf = max(0.0, min(conf, 1.0))

                await self.bus.publish(Event(topic="strategy.log", payload={"note": "LLM TA", "resp": resp}))
                await self.bus.publish(Event(topic="signals.target", payload={"side": signal, "strength": conf}))
            except Exception as ex:
                await self.bus.publish(Event(topic="strategy.log", payload={"note": f"LLM TA error: {ex}"}))