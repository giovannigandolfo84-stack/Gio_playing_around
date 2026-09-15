"""CLI: python -m crypto_fund <command>

  cycle        run one research/decision/execution cycle (PAPER by default)
  loop N       run N cycles advancing the synthetic clock (paper simulation)
  backtest     backtest every strategy on the synthetic universe (or CSV folder)
  walkforward  walk-forward test for one strategy
  montecarlo   10x engine probabilities
  review       weekly performance review
  report       print latest daily report
  dashboard    serve the dashboard on :8080
  approve ID   approve a pending trade (HUMAN_APPROVAL mode)
  pending      list pending approvals
  mode         show current mode / limits hash / kill switch
  kill / unkill  toggle the kill switch file
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import KILL_SWITCH_PATH, Mode, Settings, kill_switch_active
from .data.provider import BinancePublicProvider, CSVProvider, SyntheticProvider


def _provider(args, settings):
    if args.source == "binance":
        return BinancePublicProvider(settings.quote)
    if args.source == "csv":
        return CSVProvider(args.csv_dir)
    return SyntheticProvider(seed=args.seed, bars_1d=args.bars)


def cmd_cycle(args, settings):
    from .orchestrator import Orchestrator
    orch = Orchestrator(settings, _provider(args, settings))
    res = orch.run_cycle()
    print(res.report)
    if res.executed:
        print("\nEXECUTED:", *res.executed, sep="\n  ")
    if res.closed:
        print("\nCLOSED:", *res.closed, sep="\n  ")
    if res.llm_calls:
        print(f"\nLLM calls: {res.llm_calls}")


def cmd_loop(args, settings):
    """Paper simulation: replays the synthetic universe forward one day per cycle."""
    from .orchestrator import Orchestrator
    from .memory import Journal
    base = SyntheticProvider(seed=args.seed, bars_1d=args.bars)
    journal = Journal(settings.db_path)
    orch = Orchestrator(settings, base, journal)
    total_bars = args.bars * 24
    for k in range(args.n):
        cutoff = total_bars - (args.n - k - 1) * 24

        class Shifted:
            def __init__(self, inner, cut): self.inner, self.cut = inner, cut
            def candles(self, s, tf, n):
                from .data.provider import SyntheticProvider as SP
                return SP.resample(self.inner._base_1h(s)[: self.cut], tf)[-n:]
            def snapshot(self, s):
                snap = self.inner.snapshot(s)
                snap.candles = {tf: self.candles(s, tf, 300) for tf in snap.candles}
                snap.price = snap.candles["1h"][-1].close
                snap.volume_24h_usd = sum(c.volume for c in snap.candles["1h"][-24:]) * snap.price
                return snap
        orch.provider = Shifted(base, cutoff)
        res = orch.run_cycle()
        print(f"cycle {k + 1:3d} | regime {res.regime:12} | equity ${res.state.equity:7.2f} | dd {res.state.drawdown:5.1%} | "
              f"pos {len(res.state.positions)} | opened {len(res.executed)} closed {len(res.closed)}")
    print("\n" + res.report)


def cmd_backtest(args, settings):
    from .backtest import Backtester
    from .strategies import default_strategies
    prov = _provider(args, settings)
    bt = Backtester(settings.limits, risk_pct=args.risk)
    rows = []
    for strat in default_strategies():
        if strat.name in ("narrative", "event", "smart_money"):
            continue  # need external context; covered by paper mode
        for sym in settings.universe:
            cs = prov.candles(sym, strat.timeframe, 100000)
            r = bt.run(strat, cs, sym)
            m = r.metrics
            rows.append((strat.name, sym, m.n_trades, m.win_rate, m.profit_factor, m.expectancy_r, m.max_drawdown, m.total_return, m.worst_streak))
    print(f"{'strategy':15}{'sym':6}{'n':>5}{'win%':>7}{'PF':>7}{'exp R':>8}{'maxDD':>8}{'ret':>8}{'streak':>7}")
    for r in rows:
        pf = f"{r[4]:.2f}" if r[4] != float('inf') else "inf"
        print(f"{r[0]:15}{r[1]:6}{r[2]:5d}{r[3]:7.0%}{pf:>7}{r[5]:8.2f}{r[6]:8.1%}{r[7]:8.1%}{r[8]:7d}")
    # aggregate per strategy
    print("\nPer strategy (all symbols):")
    for name in sorted({r[0] for r in rows}):
        sub = [r for r in rows if r[0] == name and r[2] > 0]
        n = sum(r[2] for r in sub)
        exp = sum(r[5] * r[2] for r in sub) / n if n else 0
        print(f"  {name:15} trades {n:4d}  expectancy {exp:+.2f}R  avg maxDD {sum(r[6] for r in sub) / max(len(sub), 1):.1%}")


def cmd_walkforward(args, settings):
    from .backtest import Backtester
    from .strategies import ALL_STRATEGIES
    cls = next(c for c in ALL_STRATEGIES if c.name == args.strategy)
    prov = _provider(args, settings)
    cs = prov.candles(args.symbol, cls.timeframe, 100000)
    grids = {"momentum": {"lookback": [20, 30, 45], "min_ret": [0.05, 0.08, 0.12]},
             "breakout": {"lookback": [30, 50, 80], "vol_mult": [1.2, 1.5, 2.0]},
             "pullback": {"touch_atr": [0.5, 0.75, 1.0], "atr_stop": [1.0, 1.5]},
             "mean_reversion": {"z": [-2.0, -2.5, -3.0], "rsi_max": [25, 30]}}
    res = Backtester(settings.limits, risk_pct=args.risk).walk_forward(cls, cs, grids.get(args.strategy, {"atr_stop": [1.5, 2.0]}), symbol=args.symbol)
    print(json.dumps({"oos": res["oos_metrics"].to_dict(), "chosen_params": res["chosen_params"]}, indent=2))


def cmd_montecarlo(args, settings):
    from .simulation import monte_carlo
    scenarios = {
        "pessimistic (35% win, 1.8R)": dict(win_rate=0.35, avg_win_r=1.8),
        "base (42% win, 2.2R)": dict(win_rate=0.42, avg_win_r=2.2),
        "optimistic (50% win, 2.5R)": dict(win_rate=0.50, avg_win_r=2.5),
    }
    for label, kw in scenarios.items():
        r = monte_carlo(start=settings.limits.starting_capital_usd, trades=args.trades, paths=args.paths, risk_frac=args.risk, **kw)
        print(f"\n{label}  risk/trade {args.risk:.1%}  {args.trades} trades  expectancy {r.expectancy_r:+.2f}R")
        print("  P(reach):", "  ".join(f"${k}: {v:.0%}" for k, v in r.p_reach.items()))
        print("  P(lose): ", "  ".join(f"{k}: {v:.0%}" for k, v in r.p_lose.items()), f"  circuit-breaker: {r.p_circuit_breaker:.0%}")
        print(f"  final: p5 ${r.p5_final:.0f}  median ${r.median_final:.0f}  p95 ${r.p95_final:.0f}   mean maxDD {r.mean_max_drawdown:.0%}")


def cmd_review(args, settings):
    from .memory import Journal, weekly_review
    print(json.dumps(weekly_review(Journal(settings.db_path)), indent=2, default=str))


def cmd_report(args, settings):
    from .memory import Journal
    from .reports.dashboard import build_state
    print(json.dumps(build_state(Journal(settings.db_path))["summary"], indent=2))


def cmd_dashboard(args, settings):
    from .reports.dashboard import serve
    serve(settings.db_path, args.port)


def cmd_pending(args, settings):
    from .execution import HumanApprovalBroker, PaperBroker
    b = HumanApprovalBroker(PaperBroker(), str(settings.db_path) + ".approvals.json")
    print(json.dumps(b.pending(), indent=2))


def cmd_approve(args, settings):
    from .execution import HumanApprovalBroker, PaperBroker
    b = HumanApprovalBroker(PaperBroker(), str(settings.db_path) + ".approvals.json")
    print("approved" if b.approve(args.plan_id, "cli-user") else "not found / not pending")


def cmd_mode(args, settings):
    print(json.dumps({"mode": settings.mode.value, "limits_hash": settings.limits.source_hash, "kill_switch": kill_switch_active(),
                      "use_llm": settings.use_llm, "universe": settings.universe}, indent=2))


def cmd_kill(args, settings):
    KILL_SWITCH_PATH.write_text("halt")
    print("KILL SWITCH ENGAGED")


def cmd_unkill(args, settings):
    if KILL_SWITCH_PATH.exists():
        KILL_SWITCH_PATH.unlink()
    print("kill switch cleared")


def main(argv=None):
    p = argparse.ArgumentParser(prog="crypto-fund", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=[m.value for m in Mode])
    p.add_argument("--source", choices=["synthetic", "binance", "csv"], default="synthetic")
    p.add_argument("--csv-dir", default="data/csv")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--bars", type=int, default=400, help="synthetic history length in days")
    p.add_argument("--risk", type=float, default=0.01)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cycle")
    lp = sub.add_parser("loop"); lp.add_argument("n", type=int, nargs="?", default=30)
    sub.add_parser("backtest")
    wf = sub.add_parser("walkforward"); wf.add_argument("--strategy", default="momentum"); wf.add_argument("--symbol", default="ETH")
    mc = sub.add_parser("montecarlo"); mc.add_argument("--trades", type=int, default=200); mc.add_argument("--paths", type=int, default=5000)
    sub.add_parser("review"); sub.add_parser("report")
    d = sub.add_parser("dashboard"); d.add_argument("--port", type=int, default=8080)
    sub.add_parser("pending")
    ap = sub.add_parser("approve"); ap.add_argument("plan_id")
    sub.add_parser("mode"); sub.add_parser("kill"); sub.add_parser("unkill")
    args = p.parse_args(argv)
    settings = Settings.from_env()
    if args.mode:
        settings = Settings(mode=Mode(args.mode), limits=settings.limits, db_path=settings.db_path,
                            use_llm=settings.use_llm, llm_model=settings.llm_model)
    globals()[f"cmd_{args.cmd}"](args, settings)


if __name__ == "__main__":
    main()
