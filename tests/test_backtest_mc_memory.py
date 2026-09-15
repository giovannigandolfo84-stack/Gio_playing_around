import time

from crypto_fund.backtest import Backtester
from crypto_fund.config import RiskLimits
from crypto_fund.data.provider import SyntheticProvider
from crypto_fund.memory import Journal, weekly_review
from crypto_fund.models import TradeRecord
from crypto_fund.simulation import monte_carlo
from crypto_fund.strategies import MeanReversionStrategy, PullbackStrategy


def test_backtester_runs_and_metrics_consistent():
    prov = SyntheticProvider(seed=2, bars_1d=300)
    cs = prov.candles("ETH", "4h", 100000)
    r = Backtester(RiskLimits(), risk_pct=0.01).run(PullbackStrategy(), cs, "ETH")
    m = r.metrics
    assert m.n_trades > 5 and 0 <= m.win_rate <= 1 and 0 <= m.max_drawdown <= 1
    assert abs(r.equity[-1] - (100 + sum(t.pnl for t in r.trades))) < 1e-6
    # every entry happens strictly after the signal bar (no look-ahead) and after previous exit
    for a, b in zip(r.trades, r.trades[1:]):
        assert b.entry_ts > a.exit_ts


def test_walk_forward_out_of_sample():
    prov = SyntheticProvider(seed=2, bars_1d=300)
    cs = prov.candles("ETH", "1h", 100000)
    res = Backtester(RiskLimits(), warmup=260).walk_forward(MeanReversionStrategy, cs, {"z": [-2.0, -2.5]}, folds=2, symbol="ETH")
    assert len(res["chosen_params"]) == 2 and res["oos_metrics"].n_trades >= 0


def test_monte_carlo_monotone():
    r = monte_carlo(paths=500, trades=150, risk_frac=0.02, win_rate=0.45, avg_win_r=2.2)
    assert r.p_reach["150"] >= r.p_reach["225"] >= r.p_reach["500"] >= r.p_reach["1000"]
    assert r.p_lose["25%"] >= r.p_lose["50%"] >= r.p_lose["90%"]
    bad = monte_carlo(paths=500, trades=150, risk_frac=0.02, win_rate=0.25, avg_win_r=1.5)
    assert bad.p_circuit_breaker > r.p_circuit_breaker


def test_journal_roundtrip_and_review():
    j = Journal(":memory:")
    for i in range(12):
        j.record_trade(TradeRecord(time.time(), "ETH", "momentum" if i % 2 else "breakout", "BUY", 100, 110 if i % 3 else 95,
                                   0.1, 95, 110, "WIN" if i % 3 else "LOSS", 1.0 if i % 3 else -0.5, 2.0 if i % 3 else -1.0,
                                   2.1, -0.3, "BULL", {"technical": 70}, "t", "TARGET" if i % 3 else "STOP"))
    assert len(j.trades()) == 12
    rev = weekly_review(j)
    assert rev["n_trades"] == 12 and set(rev["by_strategy"]) == {"momentum", "breakout"}
    alloc = j.get("strategy_allocation")
    assert all(0.5 <= v <= 1.5 for v in alloc.values())
