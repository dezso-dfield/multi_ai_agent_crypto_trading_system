# macats/orchestrator.py
import asyncio
from macats.event_bus import EventBus
from macats.agents.fsvzo_scanner_agent import FSVZOScannerAgent
from macats.agents.risk_agent import RiskAgent
from macats.agents.execution_agent import ExecutionAgent
from macats.agents.stop_agent import StopAgent
from macats.agents.portfolio_agent import PortfolioAgent
from macats.config import SETTINGS

async def main():
    bus = EventBus()
    agents = [
        FSVZOScannerAgent(bus),                         # emits signals.target with sl/tp/atr
        RiskAgent(bus, balance=SETTINGS.paper_start_balance),
        ExecutionAgent(bus),                            # fills paper orders
        StopAgent(bus),                                 # auto flat on SL/TP breaches
        PortfolioAgent(bus, start_balance=SETTINGS.paper_start_balance),
    ]

    tasks = [asyncio.create_task(a.run()) for a in agents]

    async def log(topic):
        async for e in bus.subscribe(topic):
            print(f"[{topic}] {e.payload}")

    # lightweight console logs
    for t in ["strategy.log", "orders.planned", "exec.fills"]:
        tasks.append(asyncio.create_task(log(t)))

    await asyncio.gather(*tasks)