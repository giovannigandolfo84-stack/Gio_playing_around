"""AGENT 4 - SENTIMENT / NEWS -> SENTIMENT_SCORE. Separates information from hype."""
from __future__ import annotations

import re

from ..models import MarketSnapshot
from .base import Agent, AgentReport, clamp

HYPE = re.compile(r"\b(100x|moon|guaranteed|rumou?r|airdrop soon|last chance|pump|don'?t miss)\b", re.I)
SUBSTANCE = re.compile(r"\b(mainnet|upgrade|listing|partnership announced|audit|revenue|integration|launch(ed)?)\b", re.I)


class SentimentAgent(Agent):
    name = "sentiment"
    llm_prompt_key = "sentiment"

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:
        score, why, flags, data, conf = 50.0, [], [], {}, 0.3
        hype = sum(1 for n in snap.news if HYPE.search(n))
        real = sum(1 for n in snap.news if SUBSTANCE.search(n))
        data["hype_items"], data["substance_items"] = hype, real
        if real:
            score += min(15, real * 7); why.append(f"{real} substantive item(s)")
            conf += 0.2
        if hype:
            score -= min(20, hype * 10); flags.append(f"{hype} hype/manipulation-style item(s)")
            conf += 0.1
        if snap.social_mentions_24h and snap.social_mentions_7d_avg:
            acc = snap.social_mentions_24h / max(snap.social_mentions_7d_avg, 1)
            data["social_accel"] = acc
            conf += 0.2
            if 1.3 < acc <= 3 and real:
                score += 10; why.append("Rising attention backed by news")
            elif acc > 3 and not real:
                score -= 10; flags.append("Attention spike with no substance (possible manipulation)")
            elif acc > 5:
                score -= 15; flags.append("Extreme social spike: crowded / late")
        return AgentReport(self.name, snap.symbol, clamp(score), min(conf, 0.8), why, flags, data)
