"""AGENT 3 - ON-CHAIN ANALYST -> ONCHAIN_SCORE. Uses whatever fields the snapshot has."""
from __future__ import annotations

from ..models import MarketSnapshot
from .base import Agent, AgentReport, clamp


class OnChainAnalyst(Agent):
    name = "onchain"
    llm_prompt_key = "onchain"

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:
        score, why, flags, data, conf = 50.0, [], [], {}, 0.3
        if snap.exchange_netflow_usd_24h is not None and snap.volume_24h_usd:
            nf = snap.exchange_netflow_usd_24h / snap.volume_24h_usd
            data["netflow_ratio"] = nf
            conf += 0.15
            if nf < -0.02:
                score += 12; why.append("Net exchange outflows (accumulation)")
            elif nf > 0.02:
                score -= 12; flags.append("Net exchange inflows (distribution risk)")
        if snap.holder_top10_pct is not None:
            conf += 0.15
            data["top10_pct"] = snap.holder_top10_pct
            if snap.holder_top10_pct > 0.6:
                score -= 25; flags.append(f"Top-10 holders own {snap.holder_top10_pct:.0%}")
            elif snap.holder_top10_pct < 0.3:
                score += 8; why.append("Distributed holder base")
        if snap.dex_liquidity_usd is not None:
            conf += 0.1
            data["dex_liq_usd"] = snap.dex_liquidity_usd
            if snap.dex_liquidity_usd < 250_000:
                score -= 20; flags.append("DEX liquidity < $250k: exit liquidity risk")
        if not snap.contract_verified:
            score -= 30; flags.append("Contract not verified")
        if snap.token_age_days < 30:
            score -= 15; flags.append(f"Token is only {snap.token_age_days}d old")
        if snap.circulating_ratio is not None and snap.circulating_ratio < 0.3:
            score -= 10; flags.append(f"Only {snap.circulating_ratio:.0%} of supply circulating")
        return AgentReport(self.name, snap.symbol, clamp(score), min(conf, 0.9), why, flags, data)
