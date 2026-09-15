# Architecture

## 1. System diagram

```
                        ┌──────────────────────────────────────────────────────────┐
                        │                    DATA LAYER (untrusted)                │
                        │  Binance public REST │ CoinGecko │ on-chain APIs │ news  │
                        │  SyntheticProvider (offline) │ CSVProvider (backtests)   │
                        └───────────────┬──────────────────────────────────────────┘
                                        │ MarketSnapshot (numbers + quoted text)
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ RESEARCH DESK (agents/)                                                            │
│                                                                                    │
│  MarketScout ──► top-N candidates                                                  │
│       │                                                                            │
│       ├─► TechnicalAnalyst  ─► TECHNICAL_SCORE   (5m/15m/1h/4h/1D structure)       │
│       ├─► OnChainAnalyst    ─► ONCHAIN_SCORE     (flows, holders, DEX liq, age)    │
│       ├─► SentimentAgent    ─► SENTIMENT_SCORE   (substance vs hype)               │
│       └─► FundamentalAnalyst─► FUNDAMENTAL_SCORE (FDV, unlocks, mcap)              │
│                                                                                    │
│  StrategyEngine (7 strategies) ─► TradePlan {thesis, entry, stop, targets, inval.} │
│                                                                                    │
│  RedTeamAgent ─► VETO | risk_quality  (tries to prove the trade loses money)       │
│                                                                                    │
│  PortfolioManager ─► composite (regime-weighted) ─► TRADE_QUALITY 0-100            │
│                   ─► BUY / WAIT / SELL / HOLD / AVOID                               │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │ ScoredOpportunity
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ RISK ENGINE (risk/engine.py)  ← config/risk_limits.json (human-edited, hashed)     │
│  kill switch · circuit breaker · daily/weekly loss · positions · exposure caps     │
│  size = (equity × risk%) / (stop% + fees + slippage)  → SizedTrade or rejection    │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │ SizedTrade (approved only)
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ EXECUTION ENGINE (execution/engine.py) — 11 steps, any failure ⇒ DO NOT EXECUTE    │
│  price → liquidity → slippage → resize → risk gates → WalletPolicy → simulate →   │
│  execute → confirm → record → update portfolio                                     │
│                                                                                    │
│  WalletPolicy: mode (PAPER / HUMAN_APPROVAL / AUTONOMOUS), token+venue+contract    │
│  whitelists, per-tx & daily caps, spot-only, kill switch                            │
│  Brokers: PaperBroker · HumanApprovalBroker(queue) · CcxtBroker (trade-only keys)  │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ MEMORY (memory/)  SQLite: trades · decisions · snapshots · events · positions      │
│  weekly_review() → strategy allocation multipliers (bounded 0.5–1.5, never limits) │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        ▼
        reports/daily.py (text)  ·  reports/dashboard.py (HTTP :8080)  ·  alerts (Telegram hook)
```

The **LLM is optional and advisory**: each agent computes a deterministic heuristic score; if `FUND_USE_LLM=1`
the model may shift that score by at most ±15 (red team: −30..0) and add rationale. No LLM output reaches the
execution layer directly.

## 2. Agent architecture

| Agent | Input | Output | Can block a trade? |
|---|---|---|---|
| MarketScout | all snapshots + BTC context | ranked OPPORTUNITY_REPORT | no (filters what gets analysed) |
| TechnicalAnalyst | 5 timeframes of candles | TECHNICAL_SCORE 0–100, structure, ATR extension | no |
| OnChainAnalyst | flows, holders, DEX liquidity, contract, age | ONCHAIN_SCORE | no |
| SentimentAgent | news items, social velocity | SENTIMENT_SCORE | no |
| FundamentalAnalyst | mcap, FDV, unlocks, age | FUNDAMENTAL_SCORE | no |
| RedTeamAgent | plan + snapshot + all reports | VETO + risk_quality | **yes (veto)** |
| PortfolioManager | reports + momentum + red team + regime | TRADE_QUALITY + decision | yes (AVOID/WAIT) |
| RiskEngine | decision + portfolio state | SizedTrade / rejections | **yes (hard limits)** |
| ExecutionEngine + WalletPolicy | SizedTrade + live quote | fill / abort | **yes (11 checks)** |

Three independent layers must all say yes. The prompts for the LLM-augmented versions are in
`crypto_fund/agents/prompts.py`.

## 3. Data flow per cycle (`orchestrator.run_cycle`)

1. Fetch snapshots for the universe (failures are logged, never traded around).
2. Detect regime from BTC/ETH daily (BULL / BEAR / SIDEWAYS / HIGH_VOL / EXTREME_VOL, risk-on flag).
3. Manage open positions first (stops, targets, breakeven/trailing, panic-mode de-risk).
4. Scout ranks the universe; top-N go to the four analysts.
5. Each strategy proposes a TradePlan (or nothing).
6. Red team reviews every plan → veto or risk_quality.
7. PM computes composite with regime weights → trade quality → decision.
8. Risk engine sizes; execution engine runs the 11-step pipeline.
9. Every decision (taken or not) and every fill is journaled; daily report generated; state persisted.

## 4. Database schema (SQLite, `memory/journal.py`)

- `trades`: timestamp, asset, strategy, side, entry, exit, position_size, stop, target, result, pnl_usd, r_multiple,
  mfe, mae, market_regime, agent_scores(JSON), thesis, exit_reason, mistake_classification, fees_usd, plan_id, holding_hours
- `decisions`: timestamp, asset, strategy, decision, trade_quality, composite, regime, veto, reasons, plan(JSON), sizing(JSON), executed
- `snapshots`: timestamp, equity, cash, drawdown, open_positions, regime, mode, limits_hash
- `events`: timestamp, level, kind, message
- `positions`: live open positions (restored on restart)
- `kv`: cash, peak_equity, circuit_breaker, daily/weekly pnl, strategy_allocation, last_weekly_review

Postgres is a drop-in later (same DDL); SQLite is deliberate for a $100 book.

## 5. API architecture

MVP exposes a read-only HTTP dashboard (`/`, `/api/state`) via stdlib. Planned FastAPI surface (Phase 5+):

```
GET  /state            portfolio, positions, regime, risk level
GET  /opportunities    latest scored opportunities + sizing
GET  /trades?since=    journal
GET  /review/weekly
POST /mode             {mode: PAPER|HUMAN_APPROVAL|AUTONOMOUS}   (auth required)
POST /approve/{plan}   human approval
POST /kill  /unkill    kill switch
```
Mode switching is instant: it is a setting read at every cycle (`FUND_MODE` env or `--mode`).

## 6. Project structure

```
crypto_fund/
  config.py          modes, RiskLimits (frozen, hashed), kill switch
  models.py          Candle, MarketSnapshot, TradePlan, ScoredOpportunity, SizedTrade, Position, TradeRecord
  indicators.py      EMA/SMA/RSI/MACD/ATR/VWAP/z-score/correlation (pure python)
  data/provider.py   Synthetic, Binance public, CSV providers
  agents/            scout, technical, onchain, sentiment, fundamental, red_team, portfolio_manager, llm, prompts
  strategies/        momentum, breakout, pullback, mean_reversion, narrative, event, smart_money
  risk/              regime.py, engine.py (sizing, limits, exits)
  execution/         wallet.py (policy), brokers.py (paper/human/ccxt), engine.py (11 steps)
  backtest/          engine.py (event-driven, walk-forward), metrics.py
  simulation/        monte_carlo.py (10x engine probabilities)
  memory/            journal.py (SQLite), review.py (weekly review, allocation, mistake classes)
  reports/           daily.py, dashboard.py
  orchestrator.py    one cycle
  cli.py             commands
config/risk_limits.json   hard limits (human-only)
tests/                    26 tests
docs/                     this folder
```

## 7. Risk formulas

```
risk_pct      = tier_risk[tier] × milestone_scale(equity / start)      capped at max_loss_per_trade_pct
tier          = conservative (default) | aggressive (quality ≥ 80) | speculative (quality ≥ 88 in BULL)
                EXTREME_VOL ⇒ always conservative
milestone     = 1.0 (≤1.5x) · 0.9 (≥1.5x) · 0.75 (≥2.25x) · 0.6 (≥5x) · 0.75 (<0.9x) · 0.5 (<0.75x)
risk_usd      = equity × risk_pct
cost_frac     = 2·fee + slippage + spread/2
loss_frac     = stop_distance_pct + cost_frac
notional      = risk_usd / loss_frac
notional      = min(notional, token cap, narrative cap, total exposure cap, cash,
                    volume_24h × max_share, [autonomous per-tx cap, daily cap])
reject if     notional < min_notional · slippage > max · R:R < 2 · veto · quality < 70 · any portfolio gate
max_loss_usd  = notional × loss_frac  (≤ 3% of equity by construction)
```
Portfolio gates: kill switch, circuit breaker (20% drawdown → all trading stops until a human clears it),
daily loss 5%, weekly loss 10%, max 4 positions, no leverage.

Exits: hard stop → breakeven at +1R → trail at +0.5R after first target → final target; EXTREME_VOL regime
closes any losing position (market panic mode).

## 8. Trade scoring

```
composite = Σ weight[regime][k] × score[k]   k ∈ {technical, onchain, fundamental, sentiment, momentum, risk_quality}
quality   = composite − (1 − mean_confidence) × 10 − 10 (EXTREME_VOL) − 5 (BEAR & risk-off)
90–100 exceptional · 80–89 strong · 70–79 acceptable · 60–69 watchlist (WAIT) · <60 reject (AVOID)
```
Regime weights are in `agents/portfolio_manager.py`. Score alone never authorises a trade.

## 9. Backtesting & paper-trading frameworks

- `Backtester.run`: signal on `candles[:i+1]`, fill at next open + slippage, stop-before-target on same bar,
  fees both legs, time stop, forced close at end. Metrics: win rate, PF, expectancy R, avg win/loss, avg trade,
  total return, CAGR, max DD, Sharpe-like, worst losing streak.
- `Backtester.walk_forward`: grid chosen in-sample by expectancy (≥5 trades), evaluated on the next fold only.
- Paper trading: `Orchestrator` in PAPER mode with `PaperBroker` (slippage + fees), persistent journal;
  `crypto-fund loop N` replays the synthetic universe day by day; `--source binance` uses live public data.

## 10. Monitoring & alerts

- `events` table + `/api/state` for everything; `snapshots` gives the equity curve.
- Alert hook: any `ERROR` event, circuit breaker trip, kill switch, fill, or daily report → send to
  Telegram (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, planned in Phase 4; a 15-line `urllib` POST).
