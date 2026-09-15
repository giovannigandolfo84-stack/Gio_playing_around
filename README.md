# Crypto AI Fund — disciplined multi-agent research & paper-trading system

A $100 experimental book run like a small AI hedge fund: scout → analysts → strategies → red team →
portfolio manager → risk engine → execution policy → journal. Capital preservation first; the 10x target is
aspirational and modelled honestly (`docs/ROADMAP.md`).

**Status: Phase 1 done, Phase 2 (paper trading) runnable. No real keys, no real money.**

```
pip install -e ".[dev]"            # zero runtime deps; pytest for tests
python3 -m pytest -q               # 26 tests
python3 -m crypto_fund cycle       # one PAPER cycle on synthetic data
python3 -m crypto_fund loop 60     # 60-day paper simulation
python3 -m crypto_fund cycle --source binance   # live public market data (still PAPER)
python3 -m crypto_fund backtest    # every strategy × every symbol
python3 -m crypto_fund walkforward --strategy pullback --symbol ETH
python3 -m crypto_fund montecarlo  # $100→$1000 probabilities
python3 -m crypto_fund review      # weekly performance review
python3 -m crypto_fund dashboard   # http://127.0.0.1:8080
python3 -m crypto_fund --mode HUMAN_APPROVAL cycle ; python3 -m crypto_fund pending ; python3 -m crypto_fund approve <plan_id>
python3 -m crypto_fund kill / unkill
```

Environment: `FUND_MODE` (PAPER | HUMAN_APPROVAL | AUTONOMOUS), `FUND_DB`, `FUND_LIMITS`, `FUND_USE_LLM=1`
+ `ANTHROPIC_API_KEY` (optional, bounded advisory LLM), `FUND_KILL=1` (kill switch).

Docs: `docs/ARCHITECTURE.md` · `docs/SECURITY.md` · `docs/EXECUTION_VENUES.md` · `docs/ROADMAP.md` · `docs/AGENT_PROMPTS.md`.
Hard limits: `config/risk_limits.json` (human-edited only; hash journaled).

The synthetic data provider is a seeded random walk: it validates plumbing, not edge. Strategy backtests on it
show ≈ zero/negative expectancy by construction. Phase 3 requires real OHLCV (`--source csv`).
