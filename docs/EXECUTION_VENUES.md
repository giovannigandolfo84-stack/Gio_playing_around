# Execution venue evaluation ($100 experimental book)

| Option | Security | Fees | Liquidity | API quality | Automation | Geo | Reliability | Contract risk | Withdrawal control | Rate limits |
|---|---|---|---|---|---|---|---|---|---|---|
| CEX spot via API (Binance / Kraken / Coinbase Adv.) | good with trade-only keys + IP allow-list | 0.1–0.6% | best | excellent (ccxt) | full | varies (KYC) | high | none | disable withdrawals at exchange | generous |
| DEX aggregator (1inch / Jupiter / 0x) | self-custody; signer must be isolated | 0.1–0.3% + gas | good for majors | good REST | full, needs signer | global | depends on RPC | router + token contracts | policy in signer/session key | moderate |
| Smart-account session keys (ERC-4337 / Safe modules) | best structural limits (spend caps, allow-lists, expiry) | gas overhead | via DEX | maturing | full | global | maturing | module risk | native | n/a |
| Direct RPC + raw swaps | worst (custom code, MEV) | gas | — | low-level | full | global | RPC-dependent | high | manual | RPC-dependent |
| Portfolio-tracking APIs (Zerion, Debank, CoinGecko) | read-only | free/cheap | n/a | good | read | global | high | none | n/a | moderate |

## Recommendation for the MVP
1. **Phases 2–4: no venue.** Public Binance REST (no key) for data, PaperBroker for fills.
2. **Phase 5 (human-approved live): one CEX sub-account with trade-only API key.** Rationale: for $100 the
   dominant costs are gas and slippage; a CEX spot pair with 0.1% fees and deep books beats any DEX; and
   the exchange enforces "no withdrawals" for us, which is the single most valuable control. Pick by
   geography: Kraken (EU/UK-friendly, good API), Coinbase Advanced (US), Binance (largest books, check availability).
3. **Phase 6+: optionally add a DEX path** only for tokens not listed on the CEX, through an isolated
   signer with a session key that caps spend per tx/day and allow-lists router + tokens. Never before the
   CEX path has run cleanly for weeks.

Not chosen: leverage/perps venues (no leverage by policy), custodial "AI trading" platforms (opaque, key risk),
raw RPC swaps (MEV, custom contract code).
