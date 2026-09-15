"""WEEKLY PERFORMANCE REVIEW + evidence-based strategy allocation.

Allocation multipliers are bounded [0.5, 1.5] and only scale *which strategies get
capital*; they never touch RiskLimits.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from ..backtest.metrics import compute_metrics
from .journal import Journal


def _group_metrics(trades: List[dict], key: str) -> Dict[str, dict]:
    groups = defaultdict(list)
    for t in trades:
        groups[t[key]].append(t)
    out = {}
    for k, ts in groups.items():
        eq = [100.0]
        for t in ts:
            eq.append(eq[-1] + t["pnl_usd"])
        m = compute_metrics([t["r_multiple"] for t in ts], [t["pnl_usd"] for t in ts], eq, 1 / 52)
        out[k] = m.to_dict()
    return out


def weekly_review(journal: Journal, days: int = 7) -> dict:
    since = time.time() - days * 86400
    trades = journal.trades(since=since)
    all_trades = journal.trades()
    eq = [100.0]
    for t in trades:
        eq.append(eq[-1] + t["pnl_usd"])
    overall = compute_metrics([t["r_multiple"] for t in trades], [t["pnl_usd"] for t in trades], eq, days / 365)
    by_strategy = _group_metrics(trades, "strategy")
    by_regime = _group_metrics(trades, "market_regime")
    # agent performance: correlation of agent score with outcome sign
    agent_perf: Dict[str, dict] = {}
    for t in all_trades:
        for agent, score in (t["agent_scores"] or {}).items():
            a = agent_perf.setdefault(agent, {"hi_wins": 0, "hi_n": 0, "lo_wins": 0, "lo_n": 0})
            bucket = "hi" if score >= 65 else "lo"
            a[f"{bucket}_n"] += 1
            a[f"{bucket}_wins"] += int(t["pnl_usd"] > 0)
    for a in agent_perf.values():
        a["hi_win_rate"] = a["hi_wins"] / a["hi_n"] if a["hi_n"] else None
        a["lo_win_rate"] = a["lo_wins"] / a["lo_n"] if a["lo_n"] else None
        a["discrimination"] = (a["hi_win_rate"] or 0) - (a["lo_win_rate"] or 0) if a["hi_n"] and a["lo_n"] else None
    false_signals = [t for t in trades if t["exit_reason"] == "STOP" and t["mfe"] < 0.3]
    mistakes = defaultdict(int)
    for t in trades:
        if t.get("mistake_classification"):
            mistakes[t["mistake_classification"]] += 1
    # allocation: use all-history strategy expectancy with >= 10 trades; else neutral 1.0
    alloc = {}
    for s, m in _group_metrics(all_trades, "strategy").items():
        if m["n_trades"] >= 10:
            alloc[s] = max(0.5, min(1.5, 1.0 + m["expectancy_r"]))
        else:
            alloc[s] = 1.0
    journal.set("strategy_allocation", alloc)
    review = {
        "period_days": days, "n_trades": overall.n_trades, "overall": overall.to_dict(),
        "by_strategy": by_strategy, "by_regime": by_regime, "agent_performance": agent_perf,
        "false_signals": len(false_signals), "mistakes": dict(mistakes), "strategy_allocation": alloc,
        "winning_strategies": [s for s, m in by_strategy.items() if m["expectancy_r"] > 0],
        "losing_strategies": [s for s, m in by_strategy.items() if m["expectancy_r"] <= 0],
    }
    journal.set("last_weekly_review", review)
    return review


def classify_mistake(exit_reason: str, r: float, mfe: float, mae: float, quality: float) -> str:
    if exit_reason == "STOP" and mfe >= 1.5:
        return "gave_back_gains"      # should have taken partial / trailed tighter
    if exit_reason == "STOP" and mfe < 0.3:
        return "false_signal"
    if exit_reason == "TIME" and abs(r) < 0.3:
        return "dead_money"
    if exit_reason == "PANIC_MODE_DERISK":
        return "regime_shift"
    if r < 0 and quality < 75:
        return "low_quality_entry"
    return ""
