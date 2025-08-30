import asyncio
from macats.event_bus import EventBus
from macats.agents.sentiment_agent import SentimentAgent
from macats.agents.tech_agent import TechAgent
from macats.agents.regime_agent import RegimeAgent
from macats.agents.strategy_agent import StrategyAgent
from macats.agents.risk_agent import RiskAgent
from macats.agents.execution_agent import ExecutionAgent

async def main():
    bus = EventBus()
    agents = [
        SentimentAgent(bus),
        TechAgent(bus),
        RegimeAgent(bus),
        StrategyAgent(bus),
        RiskAgent(bus),
        ExecutionAgent(bus),
    ]
    tasks = [asyncio.create_task(a.run()) for a in agents]

    # Simple logs for visibility
    async def log(topic):
        async for e in bus.subscribe(topic):
            print(f"[{topic}] {e.payload}")

    log_tasks = [asyncio.create_task(log(t)) for t in ["strategy.log","orders.planned","exec.fills"]]
    await asyncio.wait(tasks + log_tasks, return_when=asyncio.FIRST_COMPLETED)