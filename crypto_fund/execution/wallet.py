"""WALLET / EXECUTION POLICY LAYER.

The AI proposes a TxProposal. This layer (not the AI) decides whether it may be
broadcast. It never sees or stores a seed phrase or private key: for CEX it uses
trade-only API keys (withdrawals disabled at the exchange), for DEX it hands a
prepared transaction to an external signer (hardware wallet / smart-account
session key with spend limits).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Set

from ..config import Mode, RiskLimits, kill_switch_active


@dataclass
class TxProposal:
    venue: str
    symbol: str
    side: str
    quantity: float
    notional_usd: float
    max_slippage_pct: float
    plan_id: str
    contract: Optional[str] = None   # DEX router / token contract (must be whitelisted)
    created_at: float = field(default_factory=time.time)
    approved_by: Optional[str] = None


class WalletPolicy:
    def __init__(self, limits: RiskLimits, mode: Mode, token_whitelist: Set[str],
                 venue_whitelist: Set[str], contract_whitelist: Optional[Set[str]] = None):
        self.L, self.mode = limits, mode
        self.tokens, self.venues = token_whitelist, venue_whitelist
        self.contracts = contract_whitelist or set()
        self.spent_today = 0.0
        self.day = time.strftime("%Y-%m-%d")

    def _roll_day(self):
        d = time.strftime("%Y-%m-%d")
        if d != self.day:
            self.day, self.spent_today = d, 0.0

    def authorize(self, tx: TxProposal) -> List[str]:
        """Return list of violations. Empty -> may be broadcast."""
        self._roll_day()
        v = []
        if kill_switch_active():
            v.append("KILL SWITCH active")
        if tx.venue not in self.venues:
            v.append(f"Venue '{tx.venue}' not whitelisted")
        if tx.symbol not in self.tokens:
            v.append(f"Token '{tx.symbol}' not whitelisted")
        if tx.contract and tx.contract not in self.contracts:
            v.append(f"Contract {tx.contract} not whitelisted")
        if tx.max_slippage_pct > self.L.max_slippage_pct:
            v.append("Slippage above policy max")
        if tx.side not in ("BUY", "SELL"):
            v.append("Only spot BUY/SELL allowed (no withdrawals, no transfers)")
        if self.mode == Mode.PAPER:
            pass  # simulation; nothing broadcast
        elif self.mode == Mode.HUMAN_APPROVAL:
            if not tx.approved_by:
                v.append("Awaiting human approval")
        elif self.mode == Mode.AUTONOMOUS:
            if tx.notional_usd > self.L.autonomous_max_per_tx_usd:
                v.append(f"Notional ${tx.notional_usd:.2f} > autonomous per-tx cap ${self.L.autonomous_max_per_tx_usd}")
            if self.spent_today + tx.notional_usd > self.L.autonomous_max_daily_usd:
                v.append("Autonomous daily cap exceeded")
        return v

    def record(self, tx: TxProposal) -> None:
        if tx.side == "BUY":
            self.spent_today += tx.notional_usd
