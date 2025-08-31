# macats/agents/portfolio_agent.py
import asyncio
import csv
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from macats.event_bus import Event, EventBus
from macats.config import SETTINGS

LOG_DIR = "logs"
TRADES_CSV = os.path.join(LOG_DIR, "trades.csv")
EQUITY_CSV = os.path.join(LOG_DIR, "equity.csv")


def _allow_shorts() -> bool:
    """Spot-mode toggle for shorting (paper)."""
    return bool(getattr(SETTINGS, "allow_shorts", False))


@dataclass
class Position:
    qty: float = 0.0            # signed: + long, - short
    avg_px: float = 0.0         # VWAP entry
    realized: float = 0.0       # cumulative realized PnL for this symbol


@dataclass
class AccountState:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    last_price: Dict[str, float] = field(default_factory=dict)  # symbol -> last price


class PortfolioAgent:
    """
    Multi-symbol, cash-aware paper ledger.

    Listens:
      - market.last : {"symbol": str, "price": float}
      - exec.fills  : {"status":"filled","symbol": str,"side":"long|short|flat","qty": float,"price"?: float}

    Writes CSV:
      - logs/trades.csv  : one row per fill
      - logs/equity.csv  : equity snapshots on each price + after fills
    """

    def __init__(self, bus: EventBus, start_balance: Optional[float] = None) -> None:
        self.bus = bus
        self.state = AccountState(cash=start_balance or SETTINGS.paper_start_balance)
        os.makedirs(LOG_DIR, exist_ok=True)
        self._ensure_csv_headers()

    # --------------------------- CSV ---------------------------

    def _ensure_csv_headers(self) -> None:
        if not os.path.exists(TRADES_CSV):
            with open(TRADES_CSV, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "ts",
                        "symbol",
                        "side",
                        "qty",
                        "price",
                        "realized_delta",
                        "realized_total",
                        "cash_after",
                        "pos_qty",
                        "pos_avg_px",
                    ],
                )
                writer.writeheader()
        if not os.path.exists(EQUITY_CSV):
            with open(EQUITY_CSV, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "ts",
                        "equity",
                        "cash",
                        "unrealized",
                        "realized_total",
                        "gross_exposure",
                        "num_positions",
                    ],
                )
                writer.writeheader()

    def _write_trade_row(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        realized_delta: float,
        realized_total: float,
        cash_after: float,
        pos: Position,
    ) -> None:
        row = {
            "ts": int(time.time()),
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "price": float(price),
            "realized_delta": float(realized_delta),
            "realized_total": float(realized_total),
            "cash_after": float(cash_after),
            "pos_qty": float(pos.qty),
            "pos_avg_px": float(pos.avg_px),
        }
        with open(TRADES_CSV, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=row.keys()).writerow(row)

    def _write_equity_row(self) -> None:
        equity, unrealized, realized_total, gross = self._mark_to_market()
        row = {
            "ts": int(time.time()),
            "equity": float(equity),
            "cash": float(self.state.cash),
            "unrealized": float(unrealized),
            "realized_total": float(realized_total),
            "gross_exposure": float(gross),
            "num_positions": int(sum(1 for p in self.state.positions.values() if abs(p.qty) > 0)),
        }
        with open(EQUITY_CSV, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=row.keys()).writerow(row)

    # --------------------------- Helpers ---------------------------

    def _get_or_create_pos(self, symbol: str) -> Position:
        if symbol not in self.state.positions:
            self.state.positions[symbol] = Position()
        return self.state.positions[symbol]

    def _last_price(self, symbol: str) -> Optional[float]:
        return self.state.last_price.get(symbol)

    def _set_last_price(self, symbol: str, px: float) -> None:
        if px is None:
            return
        self.state.last_price[symbol] = float(px)

    # --------------------------- PnL & Cash ---------------------------

    def _realize_on_close(self, symbol: str, closing_qty_signed: float, fill_px: float) -> float:
        """
        closing_qty_signed has the SAME SIGN as the existing position.qty for the portion being closed.
        Return realized PnL delta and update cash accordingly.
        """
        pos = self._get_or_create_pos(symbol)
        if pos.qty == 0.0 or closing_qty_signed == 0.0:
            return 0.0

        if pos.qty > 0 and closing_qty_signed > 0:
            # reduce long: sell closing_qty
            realized_delta = closing_qty_signed * (fill_px - pos.avg_px)
            self.state.cash += closing_qty_signed * fill_px
        elif pos.qty < 0 and closing_qty_signed < 0:
            # reduce short: buy-to-cover | PnL = entry_px - exit_px
            realized_delta = abs(closing_qty_signed) * (pos.avg_px - fill_px)
            self.state.cash -= abs(closing_qty_signed) * fill_px
        else:
            return 0.0

        pos.realized += realized_delta
        return realized_delta

    def _apply_fill(self, symbol: str, side: str, qty: float, fill_px: float) -> Tuple[float, Position]:
        """
        Apply one fill. Returns (realized_delta, Position).
        Cash-aware (spot-like):
          - Long buy  : cash -= qty * px
          - Long sell : cash += qty * px
          - Short open: cash += qty * px         (synthetic; paper mode)
          - Cover     : cash -= qty * px
        """
        pos = self._get_or_create_pos(symbol)
        allow_shorts = _allow_shorts()

        if side == "flat":
            # Close full if qty==0; otherwise partial close
            if pos.qty == 0.0:
                return 0.0, pos
            closing_qty = abs(pos.qty) if qty <= 0 else min(qty, abs(pos.qty))
            signed_close = closing_qty if pos.qty > 0 else -closing_qty
            realized_delta = self._realize_on_close(symbol, signed_close, fill_px)
            pos.qty = pos.qty - signed_close  # reduce toward zero
            if abs(pos.qty) == 0.0:
                pos.avg_px = 0.0
            return realized_delta, pos

        trade_qty = float(qty) if side == "long" else -float(qty)

        if pos.qty == 0.0:
            # opening fresh
            if trade_qty > 0:
                # buy long
                notional = abs(trade_qty) * fill_px
                if self.state.cash < notional:
                    # not enough cash; ignore
                    return 0.0, pos
                self.state.cash -= notional
                pos.qty = trade_qty
                pos.avg_px = fill_px
                return 0.0, pos
            else:
                # open short
                if not allow_shorts:
                    return 0.0, pos
                self.state.cash += abs(trade_qty) * fill_px
                pos.qty = trade_qty
                pos.avg_px = fill_px
                return 0.0, pos

        # same-direction add
        if (pos.qty > 0 and trade_qty > 0) or (pos.qty < 0 and trade_qty < 0):
            if trade_qty > 0:
                # add long (spend cash)
                notional = abs(trade_qty) * fill_px
                if self.state.cash < notional:
                    return 0.0, pos
                self.state.cash -= notional
            else:
                # add short (receive cash)
                if not allow_shorts:
                    return 0.0, pos
                self.state.cash += abs(trade_qty) * fill_px

            new_abs = abs(pos.qty) + abs(trade_qty)
            notional_total = abs(pos.qty) * pos.avg_px + abs(trade_qty) * fill_px
            pos.avg_px = notional_total / new_abs if new_abs > 0 else 0.0
            pos.qty += trade_qty
            return 0.0, pos

        # opposite-direction: reduce or flip
        if abs(trade_qty) <= abs(pos.qty):
            # partial close
            closing_qty = abs(trade_qty)
            signed_close = closing_qty if pos.qty > 0 else -closing_qty
            realized_delta = self._realize_on_close(symbol, signed_close, fill_px)
            pos.qty += trade_qty  # reduce magnitude
            if abs(pos.qty) == 0.0:
                pos.avg_px = 0.0
            return realized_delta, pos
        else:
            # over-close then flip
            closing_qty = abs(pos.qty)
            remainder = abs(trade_qty) - abs(pos.qty)
            signed_close = closing_qty if pos.qty > 0 else -closing_qty
            realized_delta = self._realize_on_close(symbol, signed_close, fill_px)
            if pos.qty > 0 and trade_qty < 0:
                # open new short remainder
                if not allow_shorts:
                    pos.qty = 0.0
                    pos.avg_px = 0.0
                    return realized_delta, pos
                self.state.cash += remainder * fill_px
                pos.qty = -remainder
                pos.avg_px = fill_px
                return realized_delta, pos
            elif pos.qty < 0 and trade_qty > 0:
                # open new long remainder
                notional = remainder * fill_px
                if self.state.cash < notional:
                    # insufficient cash to flip → just closed
                    pos.qty = 0.0
                    pos.avg_px = 0.0
                    return realized_delta, pos
                self.state.cash -= notional
                pos.qty = remainder
                pos.avg_px = fill_px
                return realized_delta, pos

        return 0.0, pos

    # --------------------------- MTM ---------------------------

    def _mark_to_market(self) -> Tuple[float, float, float, float]:
        realized_total = 0.0
        unrealized_total = 0.0
        gross_exposure = 0.0

        for sym, pos in self.state.positions.items():
            realized_total += pos.realized
            if abs(pos.qty) > 0:
                px = self._last_price(sym)
                if px is not None:
                    unrealized_total += pos.qty * (px - pos.avg_px)
                    gross_exposure += abs(pos.qty * px)

        equity = self.state.cash + realized_total + unrealized_total
        return float(equity), float(unrealized_total), float(realized_total), float(gross_exposure)

    # --------------------------- Listeners ---------------------------

    async def _listen_prices(self) -> None:
        sub = self.bus.subscribe("market.last")
        async for e in sub:
            sym = str(e.payload.get("symbol", getattr(SETTINGS, "symbol", "BTC/USDT")))
            try:
                px = float(e.payload["price"])
            except Exception:
                continue
            self._set_last_price(sym, px)
            self._write_equity_row()  # snapshot each tick

    async def _listen_fills(self) -> None:
        sub = self.bus.subscribe("exec.fills")
        async for e in sub:
            p = e.payload
            if p.get("status") != "filled":
                continue

            sym = str(p.get("symbol", getattr(SETTINGS, "symbol", "BTC/USDT")))
            side = str(p.get("side", "flat")).lower()
            qty = float(p.get("qty", 0.0))

            # prefer explicit price on fill, else last price
            fill_px = p.get("price")
            if fill_px is None:
                lp = self._last_price(sym)
                if lp is None:
                    await self.bus.publish(Event(topic="strategy.log", payload={"note": f"PortfolioAgent: missing price for {sym}, skipping fill"}))
                    continue
                fill_px = lp
            fill_px = float(fill_px)

            realized_delta, pos = self._apply_fill(sym, side, qty, fill_px)
            self._write_trade_row(
                symbol=sym,
                side=side,
                qty=qty,
                price=fill_px,
                realized_delta=realized_delta,
                realized_total=pos.realized,
                cash_after=self.state.cash,
                pos=pos,
            )
            self._write_equity_row()

    # --------------------------- Main ---------------------------

    async def run(self) -> None:
        await asyncio.gather(self._listen_prices(), self._listen_fills())