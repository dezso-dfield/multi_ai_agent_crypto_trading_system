# macats/agents/stop_agent.py
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
from macats.event_bus import Event, EventBus

@dataclass
class PosState:
    qty: float = 0.0          # +long, -short
    avg_px: float = 0.0
    sl: Optional[float] = None
    tp: Optional[float] = None

class StopAgent:
    """
    Auto-close on SL/TP breaches.
    Listens:
      - market.last: {"symbol","price"}
      - exec.fills : {"status":"filled","symbol","side","qty","price", "sl_price"?, "tp_price"?}
    Emits:
      - orders.planned (flat)
      - exec.fills    (simulated by ExecutionAgent)
    """
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.pos: Dict[str, PosState] = {}
        self.last_px: Dict[str, float] = {}

    def _ps(self, sym: str) -> PosState:
        if sym not in self.pos:
            self.pos[sym] = PosState()
        return self.pos[sym]

    async def _on_price(self):
        sub = self.bus.subscribe("market.last")
        async for e in sub:
            sym = str(e.payload["symbol"])
            px = float(e.payload["price"])
            self.last_px[sym] = px

            ps = self._ps(sym)
            if ps.qty == 0.0:
                continue

            # Check SL/TP
            if ps.qty > 0:
                hit_sl = (ps.sl is not None) and (px <= ps.sl)
                hit_tp = (ps.tp is not None) and (px >= ps.tp)
            else:  # short
                hit_sl = (ps.sl is not None) and (px >= ps.sl)
                hit_tp = (ps.tp is not None) and (px <= ps.tp)

            if hit_sl or hit_tp:
                qty_to_close = abs(ps.qty)
                # Fire a flatten order
                await self.bus.publish(Event(topic="orders.planned", payload={
                    "symbol": sym, "side": "flat", "qty": qty_to_close, "reason": "SL" if hit_sl else "TP"
                }))
                # Let ExecutionAgent fill it; we do not modify position state here. PortfolioAgent updates after fill.

    async def _on_fills(self):
        sub = self.bus.subscribe("exec.fills")
        async for e in sub:
            p = e.payload
            if p.get("status") != "filled":
                continue
            sym = str(p["symbol"])
            side = str(p["side"])
            qty = float(p.get("qty", 0.0))
            px = float(p.get("price", self.last_px.get(sym, 0.0)))
            sl = p.get("sl_price")
            tp = p.get("tp_price")

            ps = self._ps(sym)

            # Update state on fills
            if side == "flat":
                # Position is closed (or reduced) — rely on PortfolioAgent to handle exact avg.
                # We only zero SL/TP if fully flat afterwards; we infer via qty in pos (StopAgent doesn't know post-trade pos immediately).
                # To keep it simple, if a flatten is requested, clear SL/TP.
                ps.sl, ps.tp = None, None
                continue

            trade_qty = qty if side == "long" else -qty
            new_qty = ps.qty + trade_qty

            # Update avg price (VWAP) locally for reference (PortfolioAgent is the source of truth)
            if ps.qty == 0.0 or (ps.qty > 0 and new_qty > 0) or (ps.qty < 0 and new_qty < 0):
                total_notional = abs(ps.qty) * ps.avg_px + abs(trade_qty) * px
                total_qty = abs(ps.qty) + abs(trade_qty)
                ps.avg_px = (total_notional / total_qty) if total_qty > 0 else 0.0
            else:
                # crossing through zero
                if new_qty == 0.0:
                    ps.avg_px = 0.0
                else:
                    ps.avg_px = px

            ps.qty = new_qty

            # Update SL/TP if provided by the order/fill
            if sl is not None:
                ps.sl = float(sl)
            if tp is not None:
                ps.tp = float(tp)

    async def run(self):
        await asyncio.gather(self._on_price(), self._on_fills())