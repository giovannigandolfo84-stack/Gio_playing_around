"""RED-TEAM AGENT: tries to prove the trade is a bad idea. Has VETO power.

Veto = any hard fail. Soft concerns lower the risk-quality score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import RiskLimits
from ..indicators import correlation
from ..models import AgentReport, MarketSnapshot, TradePlan
from .llm import LLMClient


@dataclass
class RedTeamVerdict:
    veto: bool
    hard_fails: List[str]
    concerns: List[str]
    risk_quality: float  # 0-100 (100 = no concerns)
    report: AgentReport = field(default=None)  # type: ignore


class RedTeamAgent:
    name = "red_team"

    def __init__(self, limits: RiskLimits, llm: Optional[LLMClient] = None):
        self.limits, self.llm = limits, llm

    def review(self, plan: TradePlan, snap: MarketSnapshot, reports: Dict[str, AgentReport],
               ctx: dict, portfolio_value: float) -> RedTeamVerdict:
        hard, soft = [], []
        L = self.limits
        # liquidity / exit
        max_notional = portfolio_value * L.max_exposure_per_token_pct
        if snap.volume_24h_usd <= 0 or max_notional / snap.volume_24h_usd > L.max_position_vs_24h_volume_pct:
            hard.append("Position would exceed allowed share of 24h volume (exit liquidity)")
        if snap.dex_liquidity_usd is not None and snap.dex_liquidity_usd < 100_000 and snap.volume_24h_usd < 5e6:
            hard.append("Illiquid: DEX liquidity <$100k and volume <$5M")
        if snap.spread_pct > L.max_slippage_pct:
            hard.append(f"Spread {snap.spread_pct:.2%} exceeds max slippage {L.max_slippage_pct:.2%}")
        # rug / manipulation
        if not snap.contract_verified:
            hard.append("Unverified contract")
        if snap.holder_top10_pct is not None and snap.holder_top10_pct > 0.7:
            hard.append(f"Whale concentration {snap.holder_top10_pct:.0%}")
        elif snap.holder_top10_pct is not None and snap.holder_top10_pct > 0.5:
            soft.append("High holder concentration")
        if snap.token_age_days < 30:
            hard.append("Token younger than 30 days")
        # fake volume heuristic: volume/mcap absurdly high
        if snap.market_cap_usd and snap.volume_24h_usd / snap.market_cap_usd > 1.5:
            soft.append("Volume/MCap >150%: possible wash trading")
        # FDV / unlock
        if snap.market_cap_usd and snap.fdv_usd and snap.fdv_usd / snap.market_cap_usd > 4:
            hard.append("FDV > 4x market cap")
        if snap.days_to_next_unlock is not None and snap.days_to_next_unlock <= 7 and (snap.unlock_pct_of_supply or 0) >= 0.02:
            hard.append("Significant unlock within 7 days")
        # price / R:R
        if plan.reward_risk < L.min_reward_risk:
            hard.append(f"Reward/risk {plan.reward_risk:.2f} < {L.min_reward_risk}")
        if plan.stop_distance_pct > 0.15:
            soft.append("Stop wider than 15% - position will be tiny")
        if plan.stop_distance_pct < 0.005:
            hard.append("Stop inside noise (<0.5%): will be stopped by spread")
        tech = reports.get("technical")
        if tech and tech.data.get("atr_extension_4h", 0) > 3:
            soft.append("Overextended vs ATR")
        # correlation with BTC while BTC weak
        btc = ctx.get("btc_1d_closes")
        if btc and "1d" in snap.candles:
            corr = correlation([c.close for c in snap.candles["1d"]], btc, 30)
            if corr is not None and corr > 0.85 and not ctx.get("risk_on", True):
                soft.append(f"BTC correlation {corr:.2f} in risk-off regime")
        # news priced in
        sent = reports.get("sentiment")
        if sent and sent.data.get("social_accel", 0) > 3:
            soft.append("Attention already spiked: news may be priced in")
        for r in reports.values():
            for f in r.flags:
                if f not in soft and f not in hard:
                    soft.append(f)
        risk_quality = max(0.0, 100 - 100 * bool(hard) - 8 * len(soft))
        rep = AgentReport(self.name, plan.symbol, risk_quality, 0.7, [], hard + soft, {})
        if self.llm:
            adj = self.llm.score_adjustment("red_team", snap, rep)
            if adj:
                risk_quality = max(0.0, risk_quality + max(-30.0, min(0.0, adj.get("delta", 0))))
                soft.extend(f"[llm] {f}" for f in adj.get("flags", [])[:5])
                rep.score = risk_quality
        return RedTeamVerdict(bool(hard), hard, soft, risk_quality, rep)
