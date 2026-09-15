# Security model & wallet architecture

## Non-negotiables
1. The system never asks for, stores, or logs a seed phrase, private key or recovery phrase.
2. LLMs never hold authority over funds: they emit bounded score adjustments and text, nothing else.
3. Three independent gates (red team, risk engine, execution policy) must all pass.
4. Hard limits live in `config/risk_limits.json`; there is no code path that writes to it. Its hash is
   stored in every portfolio snapshot so any edit is visible.
5. Kill switch: a file `KILL_SWITCH` at repo root or `FUND_KILL=1` stops all execution immediately.

## Operating modes
| Mode | What the AI can do | What actually happens |
|---|---|---|
| PAPER | everything | PaperBroker simulates fills; no keys exist |
| HUMAN_APPROVAL | prepare a TxProposal | written to an approval queue; `crypto-fund approve <plan_id>` executes it on the next cycle |
| AUTONOMOUS | execute within limits | per-tx cap $25, daily cap $60, spot only, whitelisted tokens/venues only, kill switch |

Switch instantly with `--mode` or `FUND_MODE`. Never skip a phase.

## Wallet architecture (Phase 5+)
**CEX (recommended first live venue for $100):**
- Dedicated sub-account. API key created with *trade only*; withdrawals disabled at the exchange; IP allow-list.
- Keys enter the process via environment variables only (`CEX_API_KEY`, `CEX_API_SECRET`); `CcxtBroker` sets
  `has["withdraw"]=False` and only ever calls `create_order` / `fetch_*`.
- Fund the sub-account with exactly the experiment capital.

**DEX (later, if needed):**
- Dedicated hot wallet (fresh EOA or smart account), funded with ≤ experiment capital + gas.
- Signing happens outside the AI process: a separate signer service (or hardware wallet / ERC-4337 session key
  with spend limit, token allow-list and expiry). The AI produces an unsigned tx via `TxProposal`; the signer
  re-validates the WalletPolicy independently before signing.
- Router/token contracts must be in the contract whitelist; unknown contracts are rejected.
- Never approve unlimited token allowances.

## Threat model
| Threat | Mitigation |
|---|---|
| Compromised market-data API / fake data | multiple providers later; sanity checks (price drift >2% vs plan aborts); liquidity checks; small size |
| Compromised or jailbroken LLM | bounded deltas; JSON schema output; no tool access; heuristic fallback; cannot touch limits or execution |
| Prompt injection via news/token metadata | all external text wrapped in `<untrusted_market_data>`; prompts instruct to treat as data; regex-based hype detection independent of LLM |
| Malicious token / rug | red team hard fails: unverified contract, age < 30d, top-10 holders > 70%, FDV > 4x, DEX liquidity < $100k; token whitelist |
| Malicious smart contract | contract whitelist; no arbitrary calls; CEX-first |
| Oracle / price manipulation | order-book simulation before execution; max slippage 1%; position ≤ 0.05% of 24h volume |
| API key theft | trade-only keys, withdrawals disabled, IP allow-list, env-only, sub-account with capped balance |
| Unauthorized transactions | WalletPolicy: spot only, whitelists, per-tx and daily caps, HUMAN_APPROVAL default before AUTONOMOUS |
| Excessive permissions | principle of least privilege on every key/session; no leverage, no margin, no withdrawals |
| Supply-chain attack | zero runtime dependencies for core; `ccxt`/`anthropic` optional and pinned; lockfile + hash check before Phase 5 |
| Runaway loop / bug | max positions 4, exposure 80%, circuit breaker 20% drawdown, daily/weekly loss limits, kill switch |
| Self-modification | AI cannot edit `risk_limits.json`; allocation multipliers bounded to [0.5,1.5] |

## Pre-live checklist (before any real key exists)
- [ ] ≥ 4 weeks PAPER with real-time data, ≥ 30 closed trades, positive expectancy after costs
- [ ] Backtests + walk-forward on real OHLCV for every active strategy
- [ ] Security review of this document against the code; dependency audit
- [ ] Trade-only key on a sub-account funded with ≤ $100; withdrawals disabled; IP allow-list
- [ ] HUMAN_APPROVAL for ≥ 2 weeks before AUTONOMOUS
