# Solana Paper Trading Bot (FAKE MONEY ONLY)

Watches brand-new Solana coins, runs strict safety checks, and pretends to buy/sell with $1,000 of fake money.
No wallet. No private keys. No real trades. It refuses to start unless `config.json` says `"mode": "paper"`.

## Start / stop (Mac)

1. **Try the demo first:** double-click **`Try Demo.command`**. Works offline with 3 made-up coins.
2. **Run for real (fake money, real market data):** double-click **`Start Bot.command`**.
3. The dashboard opens by itself at **http://localhost:8000** (refreshes every 5 s).
4. **Stop:** click the black Terminal window and press **Control + C**, or just close that window.

First double-click: if macOS says it "can't be opened" → right-click the file → **Open** → **Open**.
If it says "permission denied": open Terminal, type `chmod +x ` (with a space), drag both `.command` files into the window, press Enter.
Needs Python 3.9+ from https://www.python.org/downloads/ (first start installs everything automatically).

The Mac stays awake while the bot runs (`caffeinate`) and goes back to normal when you stop it.

## What it does every 60 seconds

1. Gets new Solana coins from DEX Screener, then price/liquidity (30 per call, polite back-off on 429/403).
2. Safety checks — **every** rule must pass; anything unknown = FAIL:
   - liquidity ≥ $25,000, pool age 10 min – 6 h (too-young coins are re-checked for up to 60 min)
   - mint authority OFF and freeze authority OFF (Solana RPC)
   - biggest holder ≤ 10%, top 10 ≤ 40% (pool/locker/burn wallets are ignored: off-curve check via `solders`)
   - ≥ 90% of liquidity locked and no "danger" risks (RugCheck)
3. Fake trading: 2% of balance per trade, max 5 open, stop-loss −25%, take-profit +100%, sell after 6 h,
   no more buying for the day after a 5% daily loss. 3% fee/slippage taken on every buy and every sell.
   If a coin's price disappears for 10 checks in a row it is treated as a rug and sold at $0.

## Files

| File | What |
|---|---|
| `config.json` | All settings (incl. `rpc_url`). Change numbers here. |
| `logs/decisions.jsonl` | Every BUY / SKIP / WAIT / SELL with the reason |
| `data/portfolio.json` | Your fake portfolio (delete it to start over at $1,000) |
| `logs/demo_*`, `data/demo_*` | Demo-only files (reset every demo run) |

Terminal alternative: `python3 bot.py --demo` or `python3 bot.py` (after `pip install -r requirements.txt`).

Tip: the free public Solana RPC is slow and rate-limited, so many coins may be skipped as "data unavailable".
A free RPC URL from Helius or QuickNode in `config.json` → `rpc_url` makes it much more reliable.
