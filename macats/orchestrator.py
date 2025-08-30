# macats/orchestrator.py
import asyncio
from macats.event_bus import EventBus
from macats.agents.tech_agent import TechAgent
from macats.agents.regime_agent import RegimeAgent
from macats.agents.llm_ta_agent import LLMTAStrategyAgent
from macats.agents.risk_agent import RiskAgent
from macats.agents.execution_agent import ExecutionAgent
from macats.agents.portfolio_agent import PortfolioAgent
from macats.config import SETTINGS

async def main():
    bus = EventBus()
    agents = [
        TechAgent(bus, yf_symbol=SETTINGS.symbol, interval=SETTINGS.timeframe, lookback="60d"),
        RegimeAgent(bus),
        LLMTAStrategyAgent(bus),  # or TAStrategyAgent for pure rules
        RiskAgent(bus, balance=SETTINGS.paper_start_balance),
        ExecutionAgent(bus),
        PortfolioAgent(bus, start_balance=SETTINGS.paper_start_balance),
    ]
    tasks = [asyncio.create_task(a.run()) for a in agents]

    async def log(topic):
        async for e in bus.subscribe(topic):
            print(f"[{topic}] {e.payload}")

    log_topics = ["strategy.log", "orders.planned", "exec.fills"]
    log_tasks = [asyncio.create_task(log(t)) for t in log_topics]

    # keep running until Ctrl+C
    await asyncio.gather(*tasks, *log_tasks)