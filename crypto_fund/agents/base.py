"""Agent base: deterministic heuristics with optional LLM augmentation.

Design rule: LLM output is advisory only. It may adjust a score within a bounded
band and add rationale; it can never bypass the risk engine or execution checks.
"""
from __future__ import annotations

from typing import Optional

from ..models import AgentReport, MarketSnapshot
from .llm import LLMClient


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


class Agent:
    name = "base"
    llm_prompt_key: Optional[str] = None
    llm_band = 15.0  # max +/- adjustment an LLM may apply to the heuristic score

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:  # pragma: no cover - abstract
        raise NotImplementedError

    def analyze(self, snap: MarketSnapshot, ctx: dict | None = None) -> AgentReport:
        ctx = ctx or {}
        rep = self.heuristic(snap, ctx)
        if self.llm and self.llm_prompt_key:
            adj = self.llm.score_adjustment(self.llm_prompt_key, snap, rep)
            if adj is not None:
                delta = max(-self.llm_band, min(self.llm_band, adj.get("delta", 0.0)))
                rep.score = clamp(rep.score + delta)
                rep.rationale.extend(f"[llm] {r}" for r in adj.get("rationale", [])[:5])
                rep.flags.extend(f"[llm] {f}" for f in adj.get("flags", [])[:5])
        return rep
