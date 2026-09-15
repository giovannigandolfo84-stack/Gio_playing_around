"""EXECUTION ENGINE: 11-step pipeline. Any failed safety check -> DO NOT EXECUTE."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..config import Mode, RiskLimits
from ..models import Position, SizedTrade, Side, now
from ..risk.engine import PortfolioState, RiskEngine
from .brokers import Broker, Fill
from .wallet import TxProposal, WalletPolicy


@dataclass
class ExecutionResult:
    executed: bool
    steps: List[str] = field(default_factory=list)
    reason: str = ""
    fill: Optional[Fill] = None
    position: Optional[Position] = None
    tx: Optional[TxProposal] = None


class ExecutionEngine:
    def __init__(self, limits: RiskLimits, mode: Mode, broker: Broker, policy: WalletPolicy,
                 risk: RiskEngine, venue: str = "paper"):
        self.L, self.mode, self.broker, self.policy, self.risk, self.venue = limits, mode, broker, policy, risk, venue

    def execute(self, trade: SizedTrade, state: PortfolioState, volume_24h_usd: float) -> ExecutionResult:
        res = ExecutionResult(False)
        plan = trade.opportunity.plan
        # 1. receive approved trade
        if not trade.approved:
            return self._fail(res, "Trade not approved by risk engine: " + "; ".join(trade.rejections))
        res.steps.append("1 received approved trade")
        # 2. current price
        q = self.broker.quote(plan.symbol)
        price = q["ask"] if plan.side == Side.BUY else q["bid"]
        if price <= 0:
            return self._fail(res, "No price")
        res.steps.append(f"2 price {price:.6g}")
        drift = abs(price - plan.entry) / plan.entry
        if drift > 0.02:
            return self._fail(res, f"Price drifted {drift:.1%} from plan entry")
        # 3. liquidity
        if volume_24h_usd <= 0 or trade.notional_usd / volume_24h_usd > self.L.max_position_vs_24h_volume_pct:
            return self._fail(res, "Liquidity check failed")
        res.steps.append("3 liquidity ok")
        # 4. expected slippage
        spread = (q["ask"] - q["bid"]) / price if q["ask"] and q["bid"] else 0.0
        est_slip = spread / 2 + self.L.default_slippage_pct
        if est_slip > self.L.max_slippage_pct:
            return self._fail(res, f"Expected slippage {est_slip:.2%} too high")
        res.steps.append(f"4 slippage est {est_slip:.2%}")
        # 5. recalc position size at live price
        qty = trade.notional_usd / price
        res.steps.append(f"5 qty {qty:.6g}")
        # 6. risk limits again (state may have changed)
        gates = self.risk.portfolio_gates(state)
        if gates:
            return self._fail(res, "Risk gate: " + "; ".join(gates))
        if trade.notional_usd > state.cash:
            return self._fail(res, "Insufficient cash")
        res.steps.append("6 risk limits ok")
        # 7. simulate + policy
        tx = TxProposal(self.venue, plan.symbol, plan.side.value, qty, trade.notional_usd,
                        self.L.max_slippage_pct, plan.id)
        res.tx = tx
        violations = self.policy.authorize(tx)
        # In HUMAN_APPROVAL mode the only acceptable violation is the missing approval: the broker
        # queues the proposal (or executes it if a human already approved a matching one).
        pending_ok = self.mode == Mode.HUMAN_APPROVAL and violations == ["Awaiting human approval"]
        if violations and not pending_ok:
            return self._fail(res, "Wallet policy: " + "; ".join(violations))
        sim = self.broker.simulate(tx, price)
        if not sim.ok:
            return self._fail(res, "Simulation failed: " + sim.error)
        res.steps.append("7 simulated ok + policy ok")
        # 8. execute
        fill = self.broker.execute(tx, price)
        res.fill = fill
        if not fill.ok:
            return self._fail(res, fill.error or "Execution failed")
        if pending_ok and self.policy.authorize(tx):
            return self._fail(res, "Executed without approval - broker/policy mismatch")
        res.steps.append(f"8 executed {fill.tx_id}")
        # 9. confirm
        if fill.quantity <= 0 or fill.price <= 0:
            return self._fail(res, "Fill not confirmed")
        res.steps.append("9 confirmed")
        # 10. record / 11. update portfolio
        self.policy.record(tx)
        cost = fill.price * fill.quantity + fill.fee_usd
        state.cash -= cost
        if self.mode == Mode.AUTONOMOUS:
            state.autonomous_spent_today += trade.notional_usd
        pos = Position(plan.symbol, plan.strategy, plan.side, fill.price, fill.quantity, plan.stop,
                       list(plan.targets), now(), plan.id, plan.narrative)
        state.positions.append(pos)
        state.prices[plan.symbol] = fill.price
        res.position, res.executed = pos, True
        res.steps.append("10-11 recorded + portfolio updated")
        return res

    def close(self, pos: Position, state: PortfolioState, price: float, reason: str) -> Fill:
        tx = TxProposal(self.venue, pos.symbol, "SELL" if pos.side == Side.BUY else "BUY", pos.quantity,
                        pos.quantity * price, self.L.max_slippage_pct, pos.plan_id)
        fill = self.broker.execute(tx, price)
        if fill.ok:
            state.cash += fill.price * fill.quantity - fill.fee_usd
            state.positions = [p for p in state.positions if p.id != pos.id]
        return fill

    @staticmethod
    def _fail(res: ExecutionResult, reason: str) -> ExecutionResult:
        res.reason = reason
        res.steps.append("ABORT: " + reason)
        return res
