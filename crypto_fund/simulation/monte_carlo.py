"""10X ENGINE probability model: Monte Carlo over trade outcomes.

Two modes:
- parametric: win_rate, avg_win_r, avg_loss_r, risk fraction per trade
- bootstrap: resample observed R multiples (from backtests/journal)
Applies the same milestone risk scaling and drawdown circuit breaker as the live risk engine.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

MILESTONES = (150, 225, 250, 337, 500, 750, 1000)
LOSS_LEVELS = (0.25, 0.50, 0.75, 0.90)


@dataclass
class MCResult:
    paths: int
    trades_per_path: int
    p_reach: Dict[str, float]
    p_lose: Dict[str, float]
    p_circuit_breaker: float
    median_final: float
    p5_final: float
    p95_final: float
    mean_max_drawdown: float
    expectancy_r: float

    def to_dict(self):
        return asdict(self)


def _milestone_scale(equity: float, start: float) -> float:
    ratio = equity / start
    if ratio >= 5.0: return 0.6
    if ratio >= 2.25: return 0.75
    if ratio >= 1.5: return 0.9
    if ratio < 0.75: return 0.5
    if ratio < 0.9: return 0.75
    return 1.0


def monte_carlo(start: float = 100.0, trades: int = 200, paths: int = 5000, risk_frac: float = 0.02,
                win_rate: float = 0.42, avg_win_r: float = 2.2, avg_loss_r: float = -1.0,
                r_samples: Optional[Sequence[float]] = None, circuit_breaker_dd: float = 0.20,
                cost_r: float = 0.08, seed: int = 7) -> MCResult:
    rng = random.Random(seed)
    reach = {str(m): 0 for m in MILESTONES}
    lose = {f"{int(l * 100)}%": 0 for l in LOSS_LEVELS}
    cb = 0
    finals: List[float] = []
    mdds: List[float] = []
    r_all: List[float] = []
    for _ in range(paths):
        eq, peak, mdd, tripped = start, start, 0.0, False
        hit_m = set()
        hit_l = set()
        for _ in range(trades):
            if tripped:
                break
            if r_samples:
                r = rng.choice(r_samples)
            else:
                r = (rng.expovariate(1 / avg_win_r) if rng.random() < win_rate else avg_loss_r * rng.uniform(0.7, 1.2))
            r -= cost_r
            r_all.append(r)
            eq += eq * risk_frac * _milestone_scale(eq, start) * r
            eq = max(eq, 0.0)
            peak = max(peak, eq)
            dd = 1 - eq / peak if peak else 0.0
            mdd = max(mdd, dd)
            for m in MILESTONES:
                if eq >= m:
                    hit_m.add(m)
            for l in LOSS_LEVELS:
                if eq <= start * (1 - l):
                    hit_l.add(l)
            if dd >= circuit_breaker_dd:
                tripped = True
        for m in hit_m:
            reach[str(m)] += 1
        for l in hit_l:
            lose[f"{int(l * 100)}%"] += 1
        cb += tripped
        finals.append(eq)
        mdds.append(mdd)
    finals.sort()
    return MCResult(paths, trades, {k: v / paths for k, v in reach.items()}, {k: v / paths for k, v in lose.items()},
                    cb / paths, finals[len(finals) // 2], finals[int(0.05 * paths)], finals[int(0.95 * paths) - 1],
                    sum(mdds) / paths, sum(r_all) / len(r_all) if r_all else 0.0)
