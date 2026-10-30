"""Read-only data from free public APIs. Nothing here can trade or sign anything."""
import time
from urllib.parse import urlparse

import requests

DEX = "https://api.dexscreener.com"
RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/%s/report/summary"

# Minimum seconds between two calls to the same site (be polite).
MIN_GAP = {"api.dexscreener.com": 1.1, "api.rugcheck.xyz": 1.5}
DEFAULT_GAP = 0.5  # Solana RPC


class DataError(Exception):
    """Data could not be fetched. The safety checks treat this as a FAIL."""


class LiveSource:
    def __init__(self, cfg, say=print):
        self.rpc_url = cfg["rpc_url"]
        self.timeout = cfg["http_timeout_seconds"]
        self.retries = cfg["http_max_retries"]
        self.say = say
        self.http = requests.Session()
        self.http.headers["User-Agent"] = "solana-paper-bot/1.0 (paper trading, read-only)"
        self.next_ok = {}  # host -> earliest time we may call it again

    # ---------- polite HTTP with back-off ----------
    def _request(self, method, url, **kw):
        host = urlparse(url).netloc
        gap = MIN_GAP.get(host, DEFAULT_GAP)
        for attempt in range(self.retries + 1):
            wait = self.next_ok.get(host, 0) - time.time()
            if wait > 0:
                time.sleep(wait)
            self.next_ok[host] = time.time() + gap
            try:
                r = self.http.request(method, url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                err = "network error: %s" % e.__class__.__name__
                status = None
            else:
                status = r.status_code
                if status == 200:
                    try:
                        return r.json()
                    except ValueError:
                        raise DataError("%s returned bad JSON" % host)
                err = "HTTP %s" % status
                if status not in (403, 429) and status < 500:
                    raise DataError("%s %s" % (host, err))
            if attempt == self.retries:
                break
            backoff = 2 ** (attempt + 1) * (5 if status in (403, 429) else 1)
            if status is not None:
                try:
                    backoff = max(backoff, float(r.headers.get("Retry-After", 0)))
                except ValueError:
                    pass
            backoff = min(backoff, 120)
            self.say("  ...%s from %s, waiting %ds before retrying" % (err, host, backoff))
            self.next_ok[host] = time.time() + backoff
        raise DataError("%s: %s (gave up after retries)" % (host, err))

    def _rpc(self, method, params):
        data = self._request("POST", self.rpc_url,
                             json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in data:
            raise DataError("RPC %s error: %s" % (method, data["error"].get("message")))
        return data.get("result")

    # ---------- DEX Screener ----------
    def latest_solana_mints(self):
        data = self._request("GET", DEX + "/token-profiles/latest/v1")
        if not isinstance(data, list):
            raise DataError("unexpected token-profiles response")
        mints = []
        for p in data:
            if p.get("chainId") == "solana" and p.get("tokenAddress") and p["tokenAddress"] not in mints:
                mints.append(p["tokenAddress"])
        return mints

    def best_pairs(self, mints):
        """{mint: the pool with the most liquidity where this coin is the base token}"""
        best = {}
        mints = list(mints)
        for i in range(0, len(mints), 30):  # API limit: 30 addresses per call
            chunk = mints[i:i + 30]
            data = self._request("GET", DEX + "/tokens/v1/solana/" + ",".join(chunk))
            if not isinstance(data, list):
                raise DataError("unexpected tokens response")
            for pair in data:
                mint = (pair.get("baseToken") or {}).get("address")
                if mint not in chunk:
                    continue
                liq = (pair.get("liquidity") or {}).get("usd") or 0
                old = best.get(mint)
                if old is None or liq > ((old.get("liquidity") or {}).get("usd") or 0):
                    best[mint] = pair
        return best

    # ---------- Solana RPC (read-only) ----------
    def mint_info(self, mint):
        res = self._rpc("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        try:
            parsed = res["value"]["data"]["parsed"]
            if parsed["type"] != "mint":
                raise DataError("address is not a token mint")
            return parsed["info"]
        except (TypeError, KeyError):
            raise DataError("mint account not found or not parsable")

    def largest_accounts(self, mint):
        res = self._rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        try:
            return [(a["address"], int(a["amount"])) for a in res["value"]]
        except (TypeError, KeyError, ValueError):
            raise DataError("bad getTokenLargestAccounts response")

    def token_account_owners(self, addresses):
        res = self._rpc("getMultipleAccounts", [addresses, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        owners = {}
        try:
            for addr, acc in zip(addresses, res["value"]):
                owners[addr] = acc["data"]["parsed"]["info"]["owner"]
        except (TypeError, KeyError):
            raise DataError("could not read holder account owners")
        return owners

    # ---------- RugCheck ----------
    def rugcheck(self, mint):
        return self._request("GET", RUGCHECK % mint)
