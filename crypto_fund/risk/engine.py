"""RISK ENGINE: position sizing + hard limits + circuit breakers.

POSITION SIZE = MAX ACCEPTABLE LOSS / (STOP DISTANCE + FEES + SLIPPAGE)
then capped by: token exposure, narrative exposure, total exposure, open-position
count, liquidity share, autonomous per-tx cap. Any failed hard check -> reject.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import Mode, RiskLimits, kill_switch_active
from ..models import Position, Regime, ScoredOpportunity, SizedTrade


@dataclass
class PortfolioState:
    cash: float
    positions: List[Position] = field(default_factory=list)
    prices: Dict[str, float] = field(default_factory=dict)
    starting_capital: float = 100.0
    peak_equity: float = 100.0
    realized_pnl_today: float = 0.0
    realized_pnl_week: float = 0.0
    autonomous_spent_today: float = 0.0
    circuit_breaker_tripped: bool = False

    def price_of(self, symbol: str, fallback: Optional[float] = None) -> float:
        return self.prices.get(symbol, fallback if fallback is not None else 0.0)

    @property
    def positions_value(self) -> float:
        return sum(p.quantity * self.price_of(p.symbol, p.entry) for p in self.positions)

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value

    @property
    def drawdown(self) -> float:
        return 0.0 if self.peak_equity <= 0 else max(0.0, 1 - self.equity / self.peak_equity)

    def exposure(self, symbol: Optional[str] = None, narrative: Optional[str] = None) -> float:
        tot = 0.0
        for p in self.positions:
            if symbol and p.symbol != symbol:
                continue
            if narrative and p.narrative != narrative:
                continue
            tot += p.quantity * self.price_of(p.symbol, p.entry)
        return tot

    def update_peak(self) -> None:
        self.peak_equity = max(self.peak_equity, self.equity)


class RiskEngine:
    def __init__(self, limits: RiskLimits, mode: Mode = Mode.PAPER):
        self.L, self.mode = limits, mode

    # ------------------------------------------------------------------ tiers
    def risk_tier(self, opp: ScoredOpportunity) -> str:
        """Higher quality + calm regime -> larger risk fraction. Never above 'speculative'."""
        if opp.regime in (Regime.EXTREME_VOL,):
            return "conservative"
        if opp.trade_quality >= 88 and opp.regime == Regime.BULL:
            return "speculative"
        if opp.trade_quality >= 80:
            return "aggressive"
        return "conservative"

    def milestone_scale(self, equity: float, start: float) -> float:
        """10X ENGINE: recompute risk at milestones. Risk fraction shrinks as equity compounds
        (protect gains) and after drawdowns."""
        ratio = equity / start if start else 1.0
        if ratio >= 5.0: return 0.6
        if ratio >= 2.25: return 0.75
        if ratio >= 1.5: return 0.9
        if ratio < 0.75: return 0.5
        if ratio < 0.9: return 0.75
        return 1.0

    # ------------------------------------------------------------------ gates
    def portfolio_gates(self, state: PortfolioState) -> List[str]:
        L, rej = self.L, []
        if kill_switch_active():
            rej.append("KILL SWITCH active")
        if state.circuit_breaker_tripped:
            rej.append("Circuit breaker tripped")
        if state.drawdown >= L.max_drawdown_circuit_breaker_pct:
            state.circuit_breaker_tripped = True
            rej.append(f"Drawdown {state.drawdown:.1%} >= circuit breaker {L.max_drawdown_circuit_breaker_pct:.0%}")
        if -state.realized_pnl_today >= L.max_daily_loss_pct * state.equity:
            rej.append("Daily loss limit reached")
        if -state.realized_pnl_week >= L.max_weekly_loss_pct * state.equity:
            rej.append("Weekly loss limit reached")
        if len(state.positions) >= L.max_open_positions:
            rej.append(f"Max open positions ({L.max_open_positions})")
        return rej

    # ------------------------------------------------------------------ sizing
    def size(self, opp: ScoredOpportunity, state: PortfolioState, volume_24h_usd: float,
             spread_pct: float = 0.0005, est_slippage_pct: Optional[float] = None) -> SizedTrade:
        L, plan = self.L, opp.plan
        checks, rej = [], list(self.portfolio_gates(state))
        equity = state.equity
        tier = self.risk_tier(opp)
        risk_pct = L.risk_per_trade_pct[tier] * self.milestone_scale(equity, state.starting_capital)
        risk_pct = min(risk_pct, L.max_loss_per_trade_pct)
        risk_usd = equity * risk_pct
        slip = est_slippage_pct if est_slippage_pct is not None else L.default_slippage_pct
        # round trip cost as fraction of notional
        cost_frac = 2 * L.fee_pct + slip + spread_pct / 2
        stop_dist = plan.stop_distance_pct
        if stop_dist <= 0:
            rej.append("Zero stop distance")
            stop_dist = 1e-9
        loss_frac = stop_dist + cost_frac              # fraction of notional lost if stopped
        notional = risk_usd / loss_frac
        checks.append(f"risk {risk_pct:.2%} of equity = ${risk_usd:.2f}, tier={tier}")

        caps = {
            "token exposure cap": equity * L.max_exposure_per_token_pct - state.exposure(symbol=plan.symbol),
            "narrative exposure cap": equity * L.max_exposure_per_narrative_pct - state.exposure(narrative=plan.narrative),
            "total exposure cap": equity * L.max_total_exposure_pct - state.exposure(),
            "cash available": state.cash,
            "liquidity cap (share of 24h vol)": volume_24h_usd * L.max_position_vs_24h_volume_pct,
        }
        if self.mode == Mode.AUTONOMOUS:
            caps["autonomous per-tx cap"] = L.autonomous_max_per_tx_usd
            caps["autonomous daily cap"] = L.autonomous_max_daily_usd - state.autonomous_spent_today
        for name, cap in caps.items():
            if cap <= 0:
                rej.append(f"{name} exhausted")
            elif notional > cap:
                checks.append(f"capped by {name}: ${cap:.2f}")
                notional = cap
        if notional < L.min_notional_usd:
            rej.append(f"Notional ${notional:.2f} below minimum ${L.min_notional_usd}")
        if slip > L.max_slippage_pct:
            rej.append(f"Expected slippage {slip:.2%} > max {L.max_slippage_pct:.2%}")
        if plan.reward_risk < L.min_reward_risk:
            rej.append(f"R:R {plan.reward_risk:.2f} < {L.min_reward_risk}")
        if opp.red_team_veto:
            rej.append("Red-team veto")
        if opp.trade_quality < L.min_trade_quality_score:
            rej.append(f"Trade quality {opp.trade_quality:.0f} < {L.min_trade_quality_score}")
        if L.max_leverage <= 1.0 and notional > state.cash:
            notional = state.cash
        qty = notional / plan.entry if plan.entry > 0 else 0.0
        max_loss = notional * loss_frac
        fees = notional * 2 * L.fee_pct
        slippage_usd = notional * slip
        if rej:
            qty = 0.0
        return SizedTrade(opp, qty, notional if qty else 0.0, risk_usd, max_loss, fees, slippage_usd, tier, checks, rej)

    # ------------------------------------------------------------------ exits
    def manage_exits(self, pos: Position, price: float, high: float, low: float, regime: Regime) -> Optional[str]:
        """Return exit reason if the position must be closed."""
        r_hi, r_lo = pos.r_multiple(high), pos.r_multiple(low)
        pos.mfe, pos.mae = max(pos.mfe, r_hi), min(pos.mae, r_lo)
        stop = pos.trailing_stop or pos.stop
        if low <= stop:
            return "STOP" if not pos.trailing_stop else "TRAILING_STOP"
        if pos.targets and high >= pos.targets[-1]:
            return "TARGET"
        # after +1R move stop to breakeven; after first target trail below it
        if pos.targets and high >= pos.targets[0] and len(pos.targets) > 1:
            pos.trailing_stop = max(pos.trailing_stop or 0.0, pos.entry + 0.5 * pos.risk_per_unit)
        elif r_hi >= 1.0:
            pos.trailing_stop = max(pos.trailing_stop or 0.0, pos.entry)
        if regime == Regime.EXTREME_VOL and pos.r_multiple(price) < 0:
            return "PANIC_MODE_DERISK"
        return None
