# Roadmap, deployment and costs

## Phases (do not skip)
| Phase | Goal | Exit criterion | Status |
|---|---|---|---|
| 1 Research + architecture | this repo: architecture, agents, risk engine, execution, journal | code + docs + tests | **done (MVP)** |
| 2 Paper trading | `crypto-fund loop` on synthetic; `cycle --source binance` on live public data, PAPER mode | 100+ cycles without errors; every decision journaled | **runnable now** |
| 3 Backtesting | real OHLCV (CSV from exchange) for every strategy; walk-forward | ≥ 2 strategies with positive OOS expectancy after costs, ≥ 50 trades | framework done; needs real data |
| 4 Real-time simulation | hourly cron on live data, 4+ weeks, Telegram daily report | ≥ 30 closed paper trades, PF > 1.2, max DD < 15% | next |
| 5 Human-approved live | CEX sub-account, trade-only key, HUMAN_APPROVAL | 2+ weeks, no policy violations, fills match simulation within slippage budget | blocked on 4 |
| 6 Controlled autonomous | AUTONOMOUS with $25/tx, $60/day caps | 4+ weeks, no circuit breaker trips caused by bugs | blocked on 5 |
| 7 Optimization | weekly review drives allocation; regime weights tuned on evidence | continuous | — |

## The 10x experiment, honestly
Monte Carlo (`crypto-fund montecarlo`) at 1% risk per trade over 200 trades:

| scenario | P($150) | P($250) | P($500) | P($1000) | P(circuit breaker) |
|---|---|---|---|---|---|
| 35% win, 1.8R avg win | 2% | 0% | 0% | 0% | 81% |
| 42% win, 2.2R | 73% | 9% | 0% | 0% | 13% |
| 50% win, 2.5R | 100% | 86% | 5% | 0% | 0% |

Even a genuinely good discretionary edge does not reach 10x on 200 trades at survivable risk. 10x requires
either far more trades (compounding over years) or ~3% risk with a strong edge, which raises the 25%+
drawdown probability sharply. The system therefore treats $150 → $225 → $337 as the real milestones and
re-scales risk at each one; $1,000 stays aspirational.

## Deployment (MVP)
```
git clone … && cd Gio_playing_around
python3 -m pytest -q                         # 26 tests
python3 -m crypto_fund montecarlo            # probabilities
python3 -m crypto_fund backtest              # synthetic backtests (plumbing check)
python3 -m crypto_fund loop 60               # 60-day paper simulation
python3 -m crypto_fund cycle --source binance   # live public data, PAPER
python3 -m crypto_fund dashboard             # http://127.0.0.1:8080
```
Cron for Phase 4 (any $5 VPS, or a free-tier container):
```
0 * * * *  cd /opt/fund && FUND_MODE=PAPER python3 -m crypto_fund cycle --source binance >> logs/cycle.log 2>&1
0 8 * * *  cd /opt/fund && python3 -m crypto_fund report | telegram-send
0 8 * * 1  cd /opt/fund && python3 -m crypto_fund review | telegram-send
```
Docker: `python:3.11-slim`, copy repo, `pip install .`, mount `data/` as a volume. Redis/Postgres/FastAPI are
intentionally deferred: nothing in a $100 book needs them.

## Estimated monthly costs
| Item | MVP (Phases 2–4) | Live (Phases 5–6) |
|---|---|---|
| Infrastructure | $0 (laptop/cron) – $5 (VPS) | $5 |
| Market data | $0 (public endpoints) | $0 |
| On-chain / social data | $0 (heuristics on free fields) | $0–10 (one free-tier API) |
| LLM (optional) | $0 with heuristics; ≈ $2–6/month at 24 cycles/day × 5 assets × 5 agents on `claude-haiku-4-5`, or use `claude-opus-5` only for the red team / daily report | same |
| Trading fees | $0 | ~0.1% × turnover ≈ $1–3 |
| Gas | $0 | $0 on CEX |
| Slippage | $0 | ~0.3% × turnover ≈ $1–3 |
| **Total** | **$0–11** | **$8–25** |

Rule from the brief: never spend more than a small fraction of the book per month. The heuristic-only MVP
runs for ≈ $0. Turn on the LLM only where it adds information (red team, sentiment), with the per-cycle
call cap in `agents/llm.py`.
