"""Optional LLM client (Anthropic SDK). Disabled unless FUND_USE_LLM=1 and ANTHROPIC_API_KEY set.

Security properties:
- Structured JSON output with a strict schema; no free-form tool use.
- Market text goes inside <untrusted_market_data> tags.
- Output only adjusts a score within a bounded band (enforced in base.Agent).
- A failure/refusal -> None (heuristic score stands).
- Per-cycle call cap to bound cost.
"""
from __future__ import annotations

import json
from typing import Optional

from ..models import AgentReport, MarketSnapshot
from .prompts import PROMPTS, SYSTEM_COMMON

SCHEMA = {
    "type": "object",
    "properties": {
        "delta": {"type": "number"},
        "rationale": {"type": "array", "items": {"type": "string"}},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["delta", "rationale", "flags"],
    "additionalProperties": False,
}


class LLMClient:
    def __init__(self, model: str = "claude-opus-5", max_calls: int = 30):
        self.model = model
        self.max_calls = max_calls
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        try:
            import anthropic  # type: ignore
            self._client = anthropic.Anthropic()
        except Exception:  # SDK missing or no credentials
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    @staticmethod
    def _sanitize(snap: MarketSnapshot, rep: AgentReport) -> str:
        payload = {
            "symbol": snap.symbol, "price": snap.price, "volume_24h_usd": snap.volume_24h_usd,
            "spread_pct": snap.spread_pct, "market_cap_usd": snap.market_cap_usd, "fdv_usd": snap.fdv_usd,
            "days_to_next_unlock": snap.days_to_next_unlock, "holder_top10_pct": snap.holder_top10_pct,
            "dex_liquidity_usd": snap.dex_liquidity_usd, "token_age_days": snap.token_age_days,
            "news": [n[:300] for n in snap.news[:10]],
            "heuristic_score": rep.score, "heuristic_rationale": rep.rationale, "heuristic_flags": rep.flags,
            "indicators": rep.data,
        }
        return json.dumps(payload, default=str)

    def score_adjustment(self, key: str, snap: MarketSnapshot, rep: AgentReport) -> Optional[dict]:
        if not self._client or self.calls >= self.max_calls:
            return None
        self.calls += 1
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_COMMON + "\n\n" + PROMPTS[key],
                messages=[{"role": "user", "content":
                           "<untrusted_market_data>\n" + self._sanitize(snap, rep) + "\n</untrusted_market_data>"}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            )
            if resp.stop_reason == "refusal":
                return None
            self.tokens_in += getattr(resp.usage, "input_tokens", 0)
            self.tokens_out += getattr(resp.usage, "output_tokens", 0)
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            if not isinstance(data.get("delta"), (int, float)):
                return None
            return data
        except Exception:
            return None
