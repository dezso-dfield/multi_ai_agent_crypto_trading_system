# macats/orchestrator.py
import asyncio
from macats.event_bus import EventBus
from macats.agents.sentiment_agent import SentimentAgent
from macats.agents.tech_agent import TechAgent
from macats.agents.regime_agent import RegimeAgent
from macats.agents.strategy_agent import StrategyAgent   # <-- keep this for quick output
from macats.agents.risk_agent import RiskAgent
from macats.agents.execution_agent import ExecutionAgent

async def main():
    bus = EventBus()
    agents = [
        SentimentAgent(bus),
        TechAgent(bus, yf_symbol="BTC-USD", interval="1h", lookback="60d"),
        RegimeAgent(bus),
        StrategyAgent(bus),
        RiskAgent(bus, balance=10000),
        ExecutionAgent(bus),
    ]
    tasks = [asyncio.create_task(a.run()) for a in agents]

    # Simple log subscribers so you see output
    async def log(topic):
        async for e in bus.subscribe(topic):
            print(f"[{topic}] {e.payload}")

    log_tasks = [asyncio.create_task(log(t)) for t in ["strategy.log", "orders.planned", "exec.fills"]]

    # ✅ Keep running (don't exit after the first task completes)
    await asyncio.gather(*tasks, *log_tasks)