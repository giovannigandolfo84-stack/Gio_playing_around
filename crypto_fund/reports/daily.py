"""DAILY AI REPORT (plain text, Telegram/Discord-friendly)."""
from __future__ import annotations

from typing import Dict, List

from ..models import ScoredOpportunity
from ..risk.engine import PortfolioState


def daily_report(state: PortfolioState, regime: str, btc: float, eth: float, opps: List[ScoredOpportunity],
                 sizing: Dict[str, dict], red_flags: List[str], action: str, start: float = 100.0) -> str:
    L = []
    L.append("=== DAILY AI REPORT ===")
    L.append("MARKET")
    L.append(f"BTC: {btc:,.0f}   ETH: {eth:,.0f}   Regime: {regime}")
    L.append("")
    L.append("PORTFOLIO")
    L.append(f"Value: ${state.equity:.2f}  (start ${start:.0f}, {state.equity / start - 1:+.1%})")
    L.append(f"Cash: ${state.cash:.2f} ({state.cash / state.equity:.0%})   Drawdown: {state.drawdown:.1%}")
    L.append("")
    L.append("POSITIONS")
    if not state.positions:
        L.append("(none)")
    for p in state.positions:
        px = state.price_of(p.symbol, p.entry)
        L.append(f"{p.symbol:6} entry {p.entry:.4g} now {px:.4g} P&L {p.unrealized(px):+.2f} ({p.r_multiple(px):+.2f}R) "
                 f"stop {p.trailing_stop or p.stop:.4g} target {p.targets[-1]:.4g} [{p.strategy}]")
    L.append("")
    L.append("OPPORTUNITIES (top 5)")
    for o in opps[:5]:
        s = sizing.get(o.plan.id, {})
        L.append(f"- {o.plan.symbol} @ {o.plan.entry:.4g} | {o.plan.strategy} | score {o.trade_quality:.0f} | "
                 f"risk {o.plan.stop_distance_pct:.1%} to {o.plan.stop:.4g} | reward {o.plan.reward_risk:.1f}R to {o.plan.targets[0]:.4g}")
        L.append(f"    invalidation: {o.plan.invalidation}")
        L.append(f"    allocation: ${s.get('notional_usd', 0):.2f} ({s.get('tier', '-')}) decision {o.decision.value}")
    if not opps:
        L.append("(none met the bar)")
    L.append("")
    L.append("RED FLAGS")
    L.extend(f"- {f}" for f in red_flags[:10]) if red_flags else L.append("(none)")
    L.append("")
    L.append(f"ACTION: {action}")
    return "\n".join(L)
