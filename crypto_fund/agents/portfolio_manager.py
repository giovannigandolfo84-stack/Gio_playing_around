"""PORTFOLIO MANAGER: composite scoring with regime-dependent weights -> decision."""
from __future__ import annotations

from typing import Dict

from ..config import RiskLimits
from ..models import AgentReport, Decision, Regime, ScoredOpportunity, TradePlan
from .red_team import RedTeamVerdict

BASE_WEIGHTS = {"technical": 0.20, "onchain": 0.20, "fundamental": 0.15, "sentiment": 0.15,
                "momentum": 0.15, "risk_quality": 0.15}

REGIME_WEIGHTS: Dict[Regime, Dict[str, float]] = {
    Regime.BULL: {"technical": 0.25, "onchain": 0.15, "fundamental": 0.10, "sentiment": 0.15, "momentum": 0.20, "risk_quality": 0.15},
    Regime.BEAR: {"technical": 0.15, "onchain": 0.20, "fundamental": 0.20, "sentiment": 0.05, "momentum": 0.10, "risk_quality": 0.30},
    Regime.SIDEWAYS: BASE_WEIGHTS,
    Regime.HIGH_VOL: {"technical": 0.20, "onchain": 0.15, "fundamental": 0.15, "sentiment": 0.05, "momentum": 0.15, "risk_quality": 0.30},
    Regime.EXTREME_VOL: {"technical": 0.15, "onchain": 0.15, "fundamental": 0.15, "sentiment": 0.05, "momentum": 0.10, "risk_quality": 0.40},
}


def trade_quality_label(score: float) -> str:
    if score >= 90: return "exceptional"
    if score >= 80: return "strong"
    if score >= 70: return "acceptable"
    if score >= 60: return "watchlist"
    return "reject"


class PortfolioManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def weights_for(self, regime: Regime) -> Dict[str, float]:
        return REGIME_WEIGHTS.get(regime, BASE_WEIGHTS)

    def evaluate(self, plan: TradePlan, reports: Dict[str, AgentReport], momentum_score: float,
                 verdict: RedTeamVerdict, regime: Regime, risk_on: bool) -> ScoredOpportunity:
        w = self.weights_for(regime)
        parts = {
            "technical": reports["technical"].score if "technical" in reports else 50,
            "onchain": reports["onchain"].score if "onchain" in reports else 50,
            "fundamental": reports["fundamental"].score if "fundamental" in reports else 50,
            "sentiment": reports["sentiment"].score if "sentiment" in reports else 50,
            "momentum": momentum_score,
            "risk_quality": verdict.risk_quality,
        }
        composite = sum(parts[k] * w[k] for k in w)
        # confidence haircut: up to -10 points when agents had little data to work with
        conf = sum(r.confidence for r in reports.values()) / max(len(reports), 1)
        quality = composite - (1.0 - conf) * 10.0
        # regime gate: in EXTREME_VOL or bear + risk-off, require more
        if regime == Regime.EXTREME_VOL:
            quality -= 10
        elif regime == Regime.BEAR and not risk_on:
            quality -= 5
        quality = max(0.0, min(100.0, quality))

        if verdict.veto:
            decision = Decision.AVOID
        elif quality >= self.limits.min_trade_quality_score and plan.reward_risk >= self.limits.min_reward_risk:
            decision = Decision.BUY if plan.side.value == "BUY" else Decision.SELL
        elif quality >= 60:
            decision = Decision.WAIT
        else:
            decision = Decision.AVOID
        return ScoredOpportunity(plan=plan, reports=reports, composite_score=composite, trade_quality=quality,
                                 regime=regime, decision=decision, red_team_veto=verdict.veto,
                                 red_team_reasons=verdict.hard_fails + verdict.concerns, weights=w, confidence=conf)
