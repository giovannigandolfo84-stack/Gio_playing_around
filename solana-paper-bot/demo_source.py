"""Offline demo: 3 made-up coins. Same interface as LiveSource, no internet needed.

  DEMOGOOD - passes every check (its pool holds 55% but that's a program wallet, so it's ignored)
  MINTY    - mint authority is still ON  -> SKIP
  WHALE    - one wallet holds 22%        -> SKIP
"""
import time

from curve import demo_wallet_address, find_program_address

RAYDIUM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SUPPLY = 1_000_000_000 * 10**6


def _holders(name, pool_pct, wallet_pcts):
    pool = find_program_address([b"demo-pool", name.encode()], RAYDIUM)  # off-curve = program-owned
    rows = [("acct-%s-pool" % name, pool, pool_pct)]
    rows += [("acct-%s-%d" % (name, i), demo_wallet_address("%s%d" % (name, i)), p) for i, p in enumerate(wallet_pcts)]
    return rows


class DemoSource:
    def __init__(self):
        created = (time.time() - 45 * 60) * 1000  # pools opened 45 minutes ago
        self.coins = {
            "DEMOGOOD": dict(symbol="DEMOGOOD", price=0.0010, liq=80_000, created=created, mint_auth=None,
                             holders=_holders("good", 55, [6, 5, 4, 3, 3, 2, 2, 2, 1, 1, 1])),
            "MINTY": dict(symbol="MINTY", price=0.0040, liq=60_000, created=created, mint_auth=RAYDIUM,
                          holders=_holders("minty", 50, [5, 4, 3])),
            "WHALE": dict(symbol="WHALE", price=0.0200, liq=120_000, created=created, mint_auth=None,
                          holders=_holders("whale", 40, [22, 5, 4, 3])),
        }
        self.tick = 0

    def advance(self):
        """Each demo cycle DEMOGOOD's price rises ~50%, so it hits take-profit on cycle 3."""
        self.tick += 1
        if self.tick > 1:
            self.coins["DEMOGOOD"]["price"] *= 1.5

    def latest_solana_mints(self):
        return list(self.coins)

    def best_pairs(self, mints):
        return {m: {"baseToken": {"address": m, "symbol": c["symbol"]}, "priceUsd": str(c["price"]),
                    "liquidity": {"usd": c["liq"]}, "pairCreatedAt": c["created"], "url": None}
                for m, c in self.coins.items() if m in mints}

    def mint_info(self, mint):
        return {"mintAuthority": self.coins[mint]["mint_auth"], "freezeAuthority": None,
                "supply": str(SUPPLY), "decimals": 6}

    def largest_accounts(self, mint):
        return [(acct, int(SUPPLY * pct / 100)) for acct, _, pct in self.coins[mint]["holders"]]

    def token_account_owners(self, addresses):
        all_rows = [h for c in self.coins.values() for h in c["holders"]]
        return {acct: owner for acct, owner, _ in all_rows if acct in addresses}

    def rugcheck(self, mint):
        return {"lpLockedPct": 100, "risks": [{"name": "Low amount of holders", "level": "warn"}]}
