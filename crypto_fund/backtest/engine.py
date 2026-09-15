"""Event-driven backtester with realistic frictions + walk-forward evaluation.

Bias controls:
- Signals computed on candles[:i+1]; fills at NEXT bar open (no look-ahead).
- Stop/target checked on bar high/low; if both hit in one bar, the STOP is assumed first (conservative).
- Fees + slippage on both legs; position sized by the same RiskEngine formula.
- Walk-forward: choose params in-sample by expectancy, evaluate out-of-sample only.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..config import RiskLimits
from ..models import Candle, Side
from ..strategies.base import Strategy
from .metrics import Metrics, compute_metrics


@dataclass
class BTTrade:
    entry_ts: float
    exit_ts: float
    entry: float
    exit: float
    qty: float
    stop: float
    target: float
    pnl: float
    r: float
    reason: str
    mfe: float
    mae: float


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    metrics: Metrics
    trades: List[BTTrade]
    equity: List[float]
    params: dict = field(default_factory=dict)


class Backtester:
    def __init__(self, limits: RiskLimits, risk_pct: float = 0.01, start_equity: float = 100.0,
                 warmup: int = 120, max_hold_bars: int = 60):
        self.L, self.risk_pct, self.start, self.warmup, self.max_hold = limits, risk_pct, start_equity, warmup, max_hold_bars

    def run(self, strategy: Strategy, candles: Sequence[Candle], symbol: str = "X",
            ctx: Optional[dict] = None) -> BacktestResult:
        L = self.L
        equity, cash = self.start, self.start
        curve = [equity]
        trades: List[BTTrade] = []
        pos = None
        i = self.warmup
        n = len(candles)
        while i < n - 1:
            c = candles[i]
            if pos:
                # manage on this bar
                pos["mfe"] = max(pos["mfe"], (c.high - pos["entry"]) / pos["risk"])
                pos["mae"] = min(pos["mae"], (c.low - pos["entry"]) / pos["risk"])
                stop = pos["trail"] or pos["stop"]
                exit_px = reason = None
                if c.low <= stop:
                    exit_px, reason = stop * (1 - L.default_slippage_pct), "STOP"
                elif c.high >= pos["target"]:
                    exit_px, reason = pos["target"] * (1 - L.default_slippage_pct), "TARGET"
                elif i - pos["i"] >= self.max_hold:
                    exit_px, reason = c.close * (1 - L.default_slippage_pct), "TIME"
                else:
                    if (c.high - pos["entry"]) / pos["risk"] >= 1.0:
                        pos["trail"] = max(pos["trail"] or 0.0, pos["entry"])
                if exit_px:
                    proceeds = exit_px * pos["qty"] * (1 - L.fee_pct)
                    pnl = proceeds - pos["cost"]
                    cash += proceeds
                    equity = cash
                    trades.append(BTTrade(pos["ts"], c.ts, pos["entry"], exit_px, pos["qty"], pos["stop"], pos["target"],
                                          pnl, pnl / pos["risk_usd"], reason, pos["mfe"], pos["mae"]))
                    pos = None
            else:
                sig = strategy.signal(candles[: i + 1], ctx)
                if sig and sig.side == Side.BUY:
                    nxt = candles[i + 1]
                    entry = nxt.open * (1 + L.default_slippage_pct)
                    stop = sig.stop
                    if stop < entry:
                        risk_unit = entry - stop
                        risk_usd = equity * self.risk_pct
                        cost_frac = 2 * L.fee_pct + 2 * L.default_slippage_pct
                        notional = min(risk_usd / (risk_unit / entry + cost_frac), cash * L.max_exposure_per_token_pct * 4, cash)
                        if notional >= L.min_notional_usd:
                            qty = notional / entry
                            cost = notional * (1 + L.fee_pct)
                            cash -= cost
                            target = sig.targets[0] if sig.targets else entry + 2 * risk_unit
                            pos = dict(i=i + 1, ts=nxt.ts, entry=entry, stop=stop, target=target, qty=qty, cost=cost,
                                       risk=risk_unit, risk_usd=risk_usd, trail=None, mfe=0.0, mae=0.0)
                            i += 1  # entry bar consumed
            curve.append(cash + (pos["qty"] * c.close if pos else 0.0))
            i += 1
        if pos:  # force close at end
            c = candles[-1]
            proceeds = c.close * pos["qty"] * (1 - L.fee_pct)
            pnl = proceeds - pos["cost"]
            cash += proceeds
            trades.append(BTTrade(pos["ts"], c.ts, pos["entry"], c.close, pos["qty"], pos["stop"], pos["target"],
                                  pnl, pnl / pos["risk_usd"], "END", pos["mfe"], pos["mae"]))
            curve.append(cash)
        years = max((candles[-1].ts - candles[self.warmup].ts) / (365 * 86400), 1e-6)
        m = compute_metrics([t.r for t in trades], [t.pnl for t in trades], curve, years)
        return BacktestResult(strategy.name, symbol, m, trades, curve, dict(strategy.params))

    # ---------------------------------------------------------------- walk-forward
    def walk_forward(self, strategy_cls, candles: Sequence[Candle], grid: Dict[str, list],
                     folds: int = 4, symbol: str = "X", ctx: Optional[dict] = None) -> dict:
        n = len(candles)
        fold_len = n // (folds + 1)
        oos_results, chosen = [], []
        keys = list(grid)
        combos = [dict(zip(keys, v)) for v in itertools.product(*grid.values())]
        for f in range(folds):
            ins = candles[: fold_len * (f + 1)]
            oos = candles[fold_len * (f + 1) - self.warmup: fold_len * (f + 2)]
            best, best_score = None, -1e9
            for params in combos:
                r = self.run(strategy_cls(**params), ins, symbol, ctx)
                score = r.metrics.expectancy_r * min(r.metrics.n_trades, 20) if r.metrics.n_trades >= 5 else -1e6
                if score > best_score:
                    best, best_score = params, score
            chosen.append(best)
            oos_results.append(self.run(strategy_cls(**(best or {})), oos, symbol, ctx))
        all_r = [t.r for r in oos_results for t in r.trades]
        all_pnl = [t.pnl for r in oos_results for t in r.trades]
        # chain equity curves multiplicatively
        eq, chain = self.start, [self.start]
        for r in oos_results:
            for a, b in zip(r.equity, r.equity[1:]):
                eq *= b / a if a else 1
                chain.append(eq)
        years = max((candles[-1].ts - candles[fold_len].ts) / (365 * 86400), 1e-6)
        return {"oos_metrics": compute_metrics(all_r, all_pnl, chain, years), "chosen_params": chosen,
                "folds": [r.metrics for r in oos_results]}
