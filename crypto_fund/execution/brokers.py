"""Brokers: PaperBroker (simulated fills), HumanApprovalBroker (queue), CcxtBroker (guarded live)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from .wallet import TxProposal


@dataclass
class Fill:
    ok: bool
    price: float = 0.0
    quantity: float = 0.0
    fee_usd: float = 0.0
    tx_id: str = ""
    error: str = ""
    simulated: bool = True


class Broker(Protocol):
    def quote(self, symbol: str) -> Dict[str, float]: ...
    def simulate(self, tx: TxProposal, price: float) -> Fill: ...
    def execute(self, tx: TxProposal, price: float) -> Fill: ...


class PaperBroker:
    """Fills at price * (1 +/- slippage) and charges fees. Deterministic."""

    def __init__(self, fee_pct: float = 0.001, slippage_pct: float = 0.003, price_source=None):
        self.fee_pct, self.slippage_pct, self.price_source = fee_pct, slippage_pct, price_source
        self.fills: List[Fill] = []

    def quote(self, symbol: str) -> Dict[str, float]:
        p = self.price_source(symbol) if self.price_source else 0.0
        return {"bid": p * (1 - 0.0003), "ask": p * (1 + 0.0003), "last": p}

    def simulate(self, tx: TxProposal, price: float) -> Fill:
        px = price * (1 + self.slippage_pct) if tx.side == "BUY" else price * (1 - self.slippage_pct)
        return Fill(True, px, tx.quantity, px * tx.quantity * self.fee_pct, "sim", simulated=True)

    def execute(self, tx: TxProposal, price: float) -> Fill:
        f = self.simulate(tx, price)
        f.tx_id = f"paper-{int(time.time() * 1000)}"
        self.fills.append(f)
        return f


class HumanApprovalBroker:
    """MODE 2: writes proposals to a queue file; a human approves via CLI, then the inner broker executes."""

    def __init__(self, inner: Broker, queue_path: Path | str):
        self.inner, self.queue_path = inner, Path(queue_path)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.queue_path.exists():
            self.queue_path.write_text("[]")

    def _load(self) -> List[dict]:
        return json.loads(self.queue_path.read_text() or "[]")

    def _save(self, items: List[dict]) -> None:
        self.queue_path.write_text(json.dumps(items, indent=2))

    def quote(self, symbol: str):
        return self.inner.quote(symbol)

    def simulate(self, tx: TxProposal, price: float) -> Fill:
        return self.inner.simulate(tx, price)

    def execute(self, tx: TxProposal, price: float) -> Fill:
        """Queue the proposal, or execute it if a matching approval exists.

        Plans are regenerated every cycle, so approvals match on symbol + side within
        a 24h window and a 2% price band, not on plan_id.
        """
        items = self._load()
        now = time.time()
        for it in items:
            same = it["symbol"] == tx.symbol and it["side"] == tx.side
            fresh = now - it["created_at"] < 86400
            close = abs(price - it["price"]) / it["price"] <= 0.02 if it["price"] else False
            if same and it.get("status") == "APPROVED" and fresh and close:
                it["status"], it["executed_plan_id"], it["executed_at"] = "EXECUTED", tx.plan_id, now
                self._save(items)
                tx.approved_by = it.get("approved_by", "human")
                return self.inner.execute(tx, price)
        for it in items:
            if it["symbol"] == tx.symbol and it["side"] == tx.side and it.get("status") == "PENDING":
                it.update({"plan_id": tx.plan_id, "quantity": tx.quantity, "notional_usd": tx.notional_usd,
                           "price": price, "created_at": tx.created_at})
                self._save(items)
                return Fill(False, error="PENDING_HUMAN_APPROVAL", simulated=True)
        items.append({"plan_id": tx.plan_id, "symbol": tx.symbol, "side": tx.side, "quantity": tx.quantity,
                      "notional_usd": tx.notional_usd, "price": price, "status": "PENDING", "created_at": tx.created_at})
        self._save(items)
        return Fill(False, error="PENDING_HUMAN_APPROVAL", simulated=True)

    def approve(self, plan_id: str, who: str = "human") -> bool:
        items = self._load()
        for it in items:
            if it["plan_id"] == plan_id and it["status"] == "PENDING":
                it["status"], it["approved_by"] = "APPROVED", who
                self._save(items)
                return True
        return False

    def pending(self) -> List[dict]:
        return [i for i in self._load() if i["status"] == "PENDING"]


class CcxtBroker:
    """Guarded live CEX broker. Requires `ccxt`. Only spot market/limit orders; the API key
    MUST be created with trading-only permission and withdrawals disabled at the exchange.

    Never instantiated in PAPER mode. Keys come from env (CEX_API_KEY / CEX_API_SECRET),
    never from config files or the LLM.
    """

    def __init__(self, exchange_id: str, quote: str = "USDT", fee_pct: float = 0.001):
        import os
        import ccxt  # type: ignore
        key, secret = os.environ.get("CEX_API_KEY"), os.environ.get("CEX_API_SECRET")
        if not key or not secret:
            raise RuntimeError("CEX_API_KEY / CEX_API_SECRET not set")
        self.ex = getattr(ccxt, exchange_id)({"apiKey": key, "secret": secret, "enableRateLimit": True})
        self.quote, self.fee_pct = quote, fee_pct
        # hard guarantee: this object never exposes withdraw
        self.ex.has["withdraw"] = False

    def _market(self, symbol: str) -> str:
        return f"{symbol}/{self.quote}"

    def quote(self, symbol: str) -> Dict[str, float]:
        t = self.ex.fetch_ticker(self._market(symbol))
        return {"bid": t["bid"], "ask": t["ask"], "last": t["last"]}

    def simulate(self, tx: TxProposal, price: float) -> Fill:
        ob = self.ex.fetch_order_book(self._market(tx.symbol), 50)
        side = ob["asks"] if tx.side == "BUY" else ob["bids"]
        remaining, cost = tx.quantity, 0.0
        for px, qty in side:
            take = min(qty, remaining)
            cost += take * px
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            return Fill(False, error="Insufficient book depth")
        avg = cost / tx.quantity
        slip = abs(avg - price) / price
        if slip > tx.max_slippage_pct:
            return Fill(False, error=f"Simulated slippage {slip:.2%} > max")
        return Fill(True, avg, tx.quantity, cost * self.fee_pct, "sim", simulated=True)

    def execute(self, tx: TxProposal, price: float) -> Fill:
        limit = price * (1 + tx.max_slippage_pct) if tx.side == "BUY" else price * (1 - tx.max_slippage_pct)
        o = self.ex.create_order(self._market(tx.symbol), "limit", tx.side.lower(), tx.quantity, limit)
        return Fill(True, float(o.get("average") or limit), float(o.get("filled") or tx.quantity),
                    float((o.get("fee") or {}).get("cost") or 0.0), str(o.get("id")), simulated=False)
