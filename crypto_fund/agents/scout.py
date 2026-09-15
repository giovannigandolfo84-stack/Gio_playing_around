"""AGENT 1 - MARKET SCOUT: screens the universe and emits OPPORTUNITY_REPORT."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..indicators import ema, last, realized_vol, relative_strength, support_resistance
from ..models import MarketSnapshot
from .base import Agent, AgentReport, clamp


@dataclass
class OpportunityReport:
    ranked: List[AgentReport]
    market_notes: List[str] = field(default_factory=list)

    def top(self, n: int) -> List[AgentReport]:
        return self.ranked[:n]


class MarketScout(Agent):
    name = "scout"
    llm_prompt_key = "scout"
    llm_band = 10.0

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:
        c1h, c4h, c1d = snap.candles["1h"], snap.candles["4h"], snap.candles["1d"]
        closes_d = [c.close for c in c1d]
        btc = ctx.get("btc_1d_closes") or closes_d
        score, why, flags, data = 40.0, [], [], {}

        # relative strength vs BTC (20d)
        rs = relative_strength(closes_d, btc, 20)
        if rs is not None:
            data["rs_20d"] = rs
            score += clamp(rs * 150, -15, 20)
            if rs > 0.05:
                why.append(f"Outperforming BTC by {rs:.1%} over 20d")
        # volume expansion
        vols = [c.volume for c in c1h]
        v_recent, v_base = sum(vols[-24:]) / 24, sum(vols[-24 * 10:-24]) / (24 * 9)
        vr = v_recent / v_base if v_base else 1.0
        data["volume_ratio"] = vr
        if vr > 1.5:
            score += 10; why.append(f"Volume {vr:.1f}x 10d average")
        elif vr < 0.6:
            score -= 5
        # volatility expansion
        rv_now, rv_prev = realized_vol([c.close for c in c4h[-30:]], 20), realized_vol([c.close for c in c4h[-60:-30]], 20)
        if rv_now and rv_prev:
            data["vol_expansion"] = rv_now / rv_prev
            if rv_now / rv_prev > 1.3:
                score += 5; why.append("Volatility expanding")
        # proximity to breakout of 50-bar 4h range
        lo, hi = support_resistance(c4h[:-1], 50)
        dist = (hi - snap.price) / snap.price
        data["dist_to_high_pct"] = dist
        if 0 <= dist < 0.03:
            score += 10; why.append("Within 3% of 50-bar 4h high (breakout watch)")
        elif snap.price > hi:
            score += 12; why.append("Broke above 50-bar 4h range")
        # trend alignment
        e20, e50 = last(ema(closes_d, 20)), last(ema(closes_d, 50))
        if e20 and e50 and snap.price > e20 > e50:
            score += 8; why.append("Daily trend aligned (px > EMA20 > EMA50)")
        # narrative / social acceleration
        if snap.social_mentions_24h and snap.social_mentions_7d_avg:
            acc = snap.social_mentions_24h / max(snap.social_mentions_7d_avg, 1)
            data["social_accel"] = acc
            if acc > 3:
                flags.append("Social spike >3x average: verify substance")
        # liquidity sanity for a $100 book
        if snap.volume_24h_usd < 1_000_000:
            score -= 25; flags.append("Thin 24h volume (<$1M)")
        if snap.days_to_next_unlock is not None and snap.days_to_next_unlock <= 7:
            flags.append(f"Token unlock in {snap.days_to_next_unlock}d")
        return AgentReport(self.name, snap.symbol, clamp(score), 0.6, why, flags, data)

    def screen(self, snaps: Dict[str, MarketSnapshot], ctx: dict) -> OpportunityReport:
        reps = [self.analyze(s, ctx) for s in snaps.values()]
        reps.sort(key=lambda r: r.score, reverse=True)
        notes = [f"{r.symbol}: {r.score:.0f}" for r in reps[:5]]
        return OpportunityReport(reps, notes)
