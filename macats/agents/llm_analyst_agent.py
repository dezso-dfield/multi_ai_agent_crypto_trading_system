# macats/agents/llm_analyst_agent.py
import asyncio, math
import pandas as pd
from typing import List, Dict, Any
from macats.event_bus import Event, EventBus
from macats.llm.providers import get_llm
from macats.data.macro import toy_calendar

TAKE_COLS = ["c","sma_fast","sma_slow","rsi","atr"]

TECH_SYSTEM = (
    "You are a rigorous technical analyst. Return ONLY JSON. "
    "Use the schema: {\"role\":\"technical\",\"signal\":\"long|short|flat\","
    "\"confidence\":0..1,\"rationale\":string,"
    "\"stop_loss_bps\":int,\"take_profit_bps\":int}"
)
SENT_SYSTEM = (
    "You are a rigorous sentiment analyst. Return ONLY JSON. "
    "Schema: {\"role\":\"sentiment\",\"signal\":\"long|short|flat\","
    "\"confidence\":0..1,\"rationale\":string}"
)
MACRO_SYSTEM = (
    "You are a macro/regime analyst. Return ONLY JSON. "
    "Schema: {\"role\":\"macro\",\"signal\":\"long|short|flat\","
    "\"confidence\":0..1,\"rationale\":string}"
)

def df_to_short_csv(df: pd.DataFrame, cols: List[str], limit: int = 60) -> str:
    d = df[cols].tail(limit).copy()
    d.index = d.index.astype(str)
    return d.to_csv(index=True)

class LLMAnalystAgent:
    """
    Waits for market features + collects a rolling sentiment window.
    Calls 3 LLM 'characters' and publishes a combined analysis payload.
    """
    def __init__(self, bus: EventBus, sentiment_window: int = 32):
        self.bus = bus
        self.sent_scores: List[float] = []
        self.sentiment_window = sentiment_window

    async def _call(self, system: str, user: str) -> Dict[str, Any]:
        llm = await get_llm()
        return await llm.chat_json(system, user)

    async def run(self):
        sub_feat = self.bus.subscribe("market.features")
        sub_sent = self.bus.subscribe("sentiment.raw")

        latest_df = None

        async def collect_features():
            nonlocal latest_df
            async for e in sub_feat:
                latest_df = e.payload["df"]
                # kick LLM once we have at least a few sentiment points
                if len(self.sent_scores) >= max(8, self.sentiment_window//2):
                    await self._analyze(latest_df)
                    break

        async def collect_sentiment():
            async for e in sub_sent:
                self.sent_scores.append(float(e.payload.get("score", 0.0)))
                self.sent_scores = self.sent_scores[-self.sentiment_window:]

        await asyncio.gather(collect_features(), collect_sentiment())

    async def _analyze(self, df: pd.DataFrame):
        # Build compact context
        csv_block = df_to_short_csv(df, TAKE_COLS, limit=48)
        last = df.iloc[-1]
        features = {
            "price": float(last["c"]),
            "sma_fast": float(last["sma_fast"]),
            "sma_slow": float(last["sma_slow"]),
            "rsi": float(last["rsi"]),
            "atr_ratio": float(last["atr"]/last["c"]) if last["c"] else 0.0,
        }
        sent_stats = {
            "count": len(self.sent_scores),
            "sum": float(sum(self.sent_scores)),
            "avg": float(sum(self.sent_scores)/len(self.sent_scores)) if self.sent_scores else 0.0,
            "pos_frac": float(sum(1 for x in self.sent_scores if x>0)/len(self.sent_scores)) if self.sent_scores else 0.0
        }
        macro_events = toy_calendar()

        # USER prompts
        tech_user = (
            "Recent OHLCV-derived features (CSV with index is timestamp):\n\n"
            f"{csv_block}\n"
            f"Latest snapshot: {features}\n"
            "Provide a JSON decision per schema."
        )
        sent_user = (
            f"Rolling sentiment scores (last {len(self.sent_scores)}): {self.sent_scores}\n"
            f"Stats: {sent_stats}\n"
            "Provide a JSON decision per schema."
        )
        macro_user = (
            f"Upcoming macro events (toy): {macro_events}\n"
            "Assume BTC risk asset exposure typical. Provide JSON decision per schema."
        )

        # Call 3 LLMs concurrently
        tech_fut = asyncio.create_task(self._call(TECH_SYSTEM, tech_user))
        sent_fut = asyncio.create_task(self._call(SENT_SYSTEM, sent_user))
        macro_fut = asyncio.create_task(self._call(MACRO_SYSTEM, macro_user))
        tech, sent, macro = await asyncio.gather(tech_fut, sent_fut, macro_fut)

        payload = {"technical": tech, "sentiment": sent, "macro": macro, "latest": features, "sent_stats": sent_stats}
        await self.bus.publish(Event(topic="analysis.result", payload=payload))