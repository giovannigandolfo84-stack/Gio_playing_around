"""AGENT 5 - FUNDAMENTAL / TOKEN ANALYST -> FUNDAMENTAL_SCORE."""
from __future__ import annotations

from ..models import MarketSnapshot
from .base import Agent, AgentReport, clamp


class FundamentalAnalyst(Agent):
    name = "fundamental"
    llm_prompt_key = "fundamental"

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:
        score, why, flags, data, conf = 50.0, [], [], {}, 0.3
        if snap.market_cap_usd and snap.fdv_usd:
            ratio = snap.fdv_usd / snap.market_cap_usd
            data["fdv_mcap"] = ratio
            conf += 0.2
            if ratio > 3:
                score -= 25; flags.append(f"FDV/MCap {ratio:.1f}x: heavy future dilution")
            elif ratio > 1.8:
                score -= 10; flags.append(f"FDV/MCap {ratio:.1f}x")
            else:
                score += 10; why.append("Most supply already circulating")
        if snap.market_cap_usd:
            conf += 0.1
            if snap.market_cap_usd > 1e9:
                score += 10; why.append("Large-cap: lower rug/manipulation risk")
            elif snap.market_cap_usd < 5e7:
                score -= 15; flags.append("Micro-cap (<$50M)")
        if snap.days_to_next_unlock is not None and snap.unlock_pct_of_supply:
            conf += 0.2
            data["unlock_days"] = snap.days_to_next_unlock
            if snap.days_to_next_unlock <= 14 and snap.unlock_pct_of_supply >= 0.02:
                score -= 20; flags.append(f"Unlock of {snap.unlock_pct_of_supply:.1%} in {snap.days_to_next_unlock}d")
        if snap.token_age_days > 365:
            score += 5; why.append("Survived >1 year")
        return AgentReport(self.name, snap.symbol, clamp(score), min(conf, 0.8), why, flags, data)
