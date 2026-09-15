"""Performance metrics on a list of closed-trade R multiples / pnl and an equity curve."""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import List, Sequence


@dataclass
class Metrics:
    n_trades: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    avg_win_r: float
    avg_loss_r: float
    avg_trade_usd: float
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe_like: float
    worst_streak: int
    final_equity: float

    def to_dict(self):
        return asdict(self)


def max_drawdown(equity: Sequence[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            mdd = max(mdd, 1 - e / peak)
    return mdd


def worst_losing_streak(results: Sequence[float]) -> int:
    worst = cur = 0
    for r in results:
        cur = cur + 1 if r < 0 else 0
        worst = max(worst, cur)
    return worst


def compute_metrics(r_multiples: List[float], pnl_usd: List[float], equity: List[float],
                    years: float) -> Metrics:
    n = len(r_multiples)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, max_drawdown(equity) if equity else 0, 0, 0, equity[-1] if equity else 0)
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    gross_win = sum(p for p in pnl_usd if p > 0)
    gross_loss = -sum(p for p in pnl_usd if p < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    start, end = equity[0], equity[-1]
    total_ret = end / start - 1 if start else 0.0
    cagr = (end / start) ** (1 / years) - 1 if years > 0 and start > 0 and end > 0 else 0.0
    # Sharpe-like on per-trade R
    mean_r = sum(r_multiples) / n
    sd = math.sqrt(sum((r - mean_r) ** 2 for r in r_multiples) / (n - 1)) if n > 1 else 0.0
    sharpe = mean_r / sd * math.sqrt(n / max(years, 1e-9)) if sd > 0 else 0.0
    return Metrics(
        n_trades=n, win_rate=len(wins) / n, profit_factor=pf, expectancy_r=mean_r,
        avg_win_r=sum(wins) / len(wins) if wins else 0.0, avg_loss_r=sum(losses) / len(losses) if losses else 0.0,
        avg_trade_usd=sum(pnl_usd) / n, total_return=total_ret, cagr=cagr, max_drawdown=max_drawdown(equity),
        sharpe_like=sharpe, worst_streak=worst_losing_streak(r_multiples), final_equity=end,
    )
