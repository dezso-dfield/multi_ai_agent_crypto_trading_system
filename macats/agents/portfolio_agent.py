# macats/agents/portfolio_agent.py
import asyncio, os, csv, time
from dataclasses import dataclass, asdict
from typing import Optional
import pandas as pd
from macats.event_bus import Event, EventBus

LOG_DIR = "logs"
TRADES_CSV = os.path.join(LOG_DIR, "trades.csv")
EQUITY_CSV = os.path.join(LOG_DIR, "equity.csv")

@dataclass
class Position:
    qty: float = 0.0           # + long, - short
    avg_px: float = 0.0        # volume-weighted entry
    realized: float = 0.0      # realized PnL accumulated

class PortfolioAgent:
    """
    Paper ledger:
      - fill at latest close price
      - track position, realized/unrealized PnL, equity
      - log trades + equity to CSV for later reports
    """
    def __init__(self, bus: EventBus, start_balance: float = 10_000.0):
        self.bus = bus
        self.start_balance = start_balance
        self.cash = start_balance
        self.pos = Position()
        self.last_price: Optional[float] = None
        os.makedirs(LOG_DIR, exist_ok=True)
        # initialize CSVs if empty
        if not os.path.exists(TRADES_CSV):
            with open(TRADES_CSV, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "ts","side","qty","price","realized_after","cash_after","pos_qty","pos_avg_px"
                ])
                w.writeheader()
        if not os.path.exists(EQUITY_CSV):
            with open(EQUITY_CSV, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ts","price","equity","cash","pos_qty","pos_avg_px","unrealized","realized"])
                w.writeheader()

    def _mark_to_market(self) -> float:
        if self.last_price is None:
            return self.cash + self.pos.realized
        unreal = self.pos.qty * (self.last_price - self.pos.avg_px)
        return self.cash + self.pos.realized + unreal

    def _record_equity(self):
        if self.last_price is None:
            return
        ts = int(time.time())
        unreal = self.pos.qty * (self.last_price - self.pos.avg_px)
        row = {
            "ts": ts, "price": self.last_price, "equity": self._mark_to_market(), "cash": self.cash,
            "pos_qty": self.pos.qty, "pos_avg_px": self.pos.avg_px, "unrealized": unreal, "realized": self.pos.realized
        }
        with open(EQUITY_CSV, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=row.keys()).writerow(row)

    async def _listen_price(self):
        sub = self.bus.subscribe("market.features")
        async for e in sub:
            df = e.payload["df"]
            self.last_price = float(df.iloc[-1]["c"])
            self._record_equity()   # snapshot on each new feature packet

    async def _listen_fills(self):
        sub = self.bus.subscribe("exec.fills")
        async for e in sub:
            if self.last_price is None:
                continue
            status = e.payload.get("status")
            if status != "filled":
                continue
            side = e.payload.get("side","flat")
            qty = float(e.payload.get("qty",0.0))
            fill_px = self.last_price

            trade_qty = 0.0
            if side == "long":
                trade_qty = qty
            elif side == "short":
                trade_qty = -qty
            else:
                trade_qty = -self.pos.qty  # flatten if flat

            if trade_qty == 0.0:
                # still log equity
                self._record_equity()
                continue

            # If direction reduces/offsets existing position, realize PnL on the closed portion
            if self.pos.qty != 0 and (self.pos.qty > 0 > trade_qty or self.pos.qty < 0 < trade_qty):
                # Opposing trade
                closing = min(abs(trade_qty), abs(self.pos.qty)) * ( -1 if self.pos.qty > 0 else 1 )
                # realized PnL for 'closing' qty
                realized_pnl = closing * (fill_px - self.pos.avg_px) * (-1 if self.pos.qty < 0 else 1)
                self.pos.realized += realized_pnl
                self.cash += realized_pnl

            # Update position
            new_qty = self.pos.qty + trade_qty
            if self.pos.qty == 0 or (self.pos.qty > 0 and new_qty > 0) or (self.pos.qty < 0 and new_qty < 0):
                # Adding to same direction or opening new
                total_notional = abs(self.pos.qty)*self.pos.avg_px + abs(trade_qty)*fill_px
                total_qty = abs(self.pos.qty) + abs(trade_qty)
                new_avg = (total_notional / total_qty) if total_qty > 0 else 0.0
                # keep sign of new_qty
                self.pos.avg_px = new_avg
            else:
                # We flipped or reduced across zero -> if new_qty has opposite sign, avg_px resets to fill_px
                if new_qty == 0:
                    self.pos.avg_px = 0.0
                else:
                    self.pos.avg_px = fill_px
            self.pos.qty = new_qty

            # Write trade log
            ts = int(time.time())
            with open(TRADES_CSV, "a", newline="") as f:
                row = {
                    "ts": ts, "side": side, "qty": qty, "price": fill_px,
                    "realized_after": self.pos.realized, "cash_after": self.cash,
                    "pos_qty": self.pos.qty, "pos_avg_px": self.pos.avg_px
                }
                csv.DictWriter(f, fieldnames=row.keys()).writerow(row)

            # Equity snapshot after trade
            self._record_equity()

    async def run(self):
        await asyncio.gather(self._listen_price(), self._listen_fills())