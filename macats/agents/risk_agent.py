# macats/agents/risk_agent.py
from collections import defaultdict
from macats.event_bus import Event, EventBus
from macats.config import SETTINGS

class RiskAgent:
    def __init__(self, bus: EventBus, balance: float | None = None):
        self.bus = bus
        self.start_balance = balance if balance is not None else SETTINGS.paper_start_balance

        self.max_open = int(getattr(SETTINGS, "max_open_trades", 3))
        self.risk_pct = float(getattr(SETTINGS, "risk_per_trade_pct", 2.0)) / 100.0
        self.per_trade_allocation_pct = float(getattr(SETTINGS, "per_trade_allocation_pct", 25.0)) / 100.0
        self.max_portfolio_allocation_pct = float(getattr(SETTINGS, "max_portfolio_allocation_pct", 100.0)) / 100.0

        self.open_positions: dict[str, float] = defaultdict(float)  # symbol -> qty (signed)
        self.last_price: dict[str, float] = {}
        self.gross_exposure: float = 0.0  # rough estimate from our own orders

    async def _listen_prices(self):
        sub = self.bus.subscribe("market.last")
        async for e in sub:
            sym = str(e.payload.get("symbol", getattr(SETTINGS, "symbol", "BTC/USDT")))
            try:
                px = float(e.payload["price"])
            except Exception:
                continue
            self.last_price[sym] = px

    async def run(self):
        import asyncio
        asyncio.create_task(self._listen_prices())

        sub = self.bus.subscribe("signals.target")
        async for e in sub:
            p = e.payload
            sym = str(p.get("symbol", getattr(SETTINGS, "symbol", "BTC/USDT")))
            side = str(p["side"]).lower()
            strength = float(p.get("strength", 0.0))
            atr = float(p.get("atr", 0.0))
            sl_price = p.get("sl_price")
            tp_price = p.get("tp_price")

            px = self.last_price.get(sym)
            if px is None:
                await self.bus.publish(Event(topic="strategy.log", payload={"note": f"Risk: missing price for {sym}"}))
                continue

            # Max concurrent trades
            live = sum(1 for q in self.open_positions.values() if abs(q) > 0)
            if live >= self.max_open and side != "flat":
                await self.bus.publish(Event(topic="strategy.log", payload={"note": "Risk gate: max open reached", "symbol": sym}))
                continue

            # Portfolio allocation cap (rough)
            max_port_total = self.start_balance * self.max_portfolio_allocation_pct
            if self.gross_exposure > max_port_total and side != "flat":
                await self.bus.publish(Event(topic="strategy.log", payload={"note": "Risk gate: portfolio allocation cap", "symbol": sym}))
                continue

            # Per-trade cap
            per_trade_cap = self.start_balance * self.per_trade_allocation_pct

            # ATR risk sizing
            qty_by_atr = 0.0
            if atr > 0:
                risk_dollars = max(0.0, self.start_balance * self.risk_pct)
                qty_by_atr = risk_dollars / atr

            # Scale by signal strength
            qty_target = max(0.0, qty_by_atr * max(0.2, min(strength, 1.0)))

            # Cap by per-trade notional
            max_qty_by_allocation = per_trade_cap / px
            qty = min(qty_target, max_qty_by_allocation)
            if qty <= 0:
                continue

            if side == "flat":
                order_qty = abs(self.open_positions.get(sym, 0.0))
                if order_qty > 0:
                    await self.bus.publish(Event(topic="orders.planned", payload={
                        "symbol": sym, "side": "flat", "qty": order_qty
                    }))
                    await self.bus.publish(Event(topic="exec.fills", payload={
                        "status": "filled", "symbol": sym, "side": "flat",
                        "qty": order_qty, "price": px
                    }))
                    self.gross_exposure -= min(self.gross_exposure, order_qty * px)
                    self.open_positions[sym] = 0.0
                continue

            if side == "long":
                order_qty = round(qty, 6)
                await self.bus.publish(Event(topic="orders.planned", payload={
                    "symbol": sym, "side": "long", "qty": order_qty, "sl_price": sl_price, "tp_price": tp_price
                }))
                await self.bus.publish(Event(topic="exec.fills", payload={
                    "status": "filled", "symbol": sym, "side": "long",
                    "qty": order_qty, "price": px, "sl_price": sl_price, "tp_price": tp_price
                }))
                self.open_positions[sym] += order_qty
                self.gross_exposure += order_qty * px
                continue

            if side == "short":
                allow_shorts = bool(getattr(SETTINGS, "allow_shorts", False))
                if not allow_shorts:
                    await self.bus.publish(Event(topic="strategy.log", payload={"note": "Risk: shorts disabled (spot mode)", "symbol": sym}))
                    continue
                order_qty = round(qty, 6)
                await self.bus.publish(Event(topic="orders.planned", payload={
                    "symbol": sym, "side": "short", "qty": order_qty, "sl_price": sl_price, "tp_price": tp_price
                }))
                await self.bus.publish(Event(topic="exec.fills", payload={
                    "status": "filled", "symbol": sym, "side": "short",
                    "qty": order_qty, "price": px, "sl_price": sl_price, "tp_price": tp_price
                }))
                self.open_positions[sym] -= order_qty
                self.gross_exposure += order_qty * px