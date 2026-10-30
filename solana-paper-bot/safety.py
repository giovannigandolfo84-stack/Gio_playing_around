"""Safety checks. Every rule must pass. Anything unknown is a FAIL."""
import time

from curve import is_on_curve
from datasource import DataError

# Burn addresses: tokens sent here are gone forever, so they don't count as holders.
BURN_ADDRESSES = {
    "1nc1nerator11111111111111111111111111111111",
    "11111111111111111111111111111111",
}

PASS, FAIL, WAIT = "pass", "fail", "wait"


def pool_age_minutes(pair, now=None):
    created = pair.get("pairCreatedAt")
    if not created:
        return None
    return ((now or time.time()) - created / 1000) / 60


def check_market(pair, cfg, now=None):
    """Cheap checks using DEX Screener data. Returns (PASS|FAIL|WAIT, reason)."""
    if pair is None:
        return WAIT, "no trading pool found yet"
    age = pool_age_minutes(pair, now)
    if age is None:
        return FAIL, "pool age unknown"
    if age < cfg["min_pool_age_minutes"]:
        return WAIT, "pool too young (%.0f min, need %s)" % (age, cfg["min_pool_age_minutes"])
    if age > cfg["max_pool_age_hours"] * 60:
        return FAIL, "pool too old (%.1f h, max %s h)" % (age / 60, cfg["max_pool_age_hours"])
    liq = (pair.get("liquidity") or {}).get("usd")
    if liq is None:
        return FAIL, "liquidity unknown"
    if liq < cfg["min_liquidity_usd"]:
        return FAIL, "liquidity too low ($%s, need $%s)" % (f"{liq:,.0f}", f"{cfg['min_liquidity_usd']:,}")
    try:
        if float(pair.get("priceUsd")) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return FAIL, "price unknown"
    return PASS, "liquidity $%s, pool age %.0f min" % (f"{liq:,.0f}", age)


def check_onchain(src, mint, cfg):
    """Mint/freeze authority and holder concentration. Returns (ok, reason, details)."""
    info = src.mint_info(mint)
    if "mintAuthority" not in info or "freezeAuthority" not in info:
        return False, "authority status unknown", {}
    if info["mintAuthority"] is not None:
        return False, "mint authority is ON (creator can print more coins)", {}
    if info["freezeAuthority"] is not None:
        return False, "freeze authority is ON (creator can freeze your coins)", {}
    supply = int(info.get("supply") or 0)
    if supply <= 0:
        return False, "token supply unknown", {}

    largest = src.largest_accounts(mint)
    if not largest:
        return False, "holder list unknown", {}
    owners = src.token_account_owners([a for a, _ in largest])
    holders, excluded = [], 0
    for addr, amount in largest:
        owner = owners.get(addr)
        if owner is None:
            return False, "holder owner unknown", {}
        if owner in BURN_ADDRESSES or not is_on_curve(owner):
            excluded += 1  # pool / locker / burn wallet: program-owned, not a person
            continue
        holders.append(amount * 100 / supply)
    holders.sort(reverse=True)
    top1 = holders[0] if holders else 0
    top10 = sum(holders[:10])
    details = {"top_holder_pct": round(top1, 2), "top10_pct": round(top10, 2), "excluded_program_wallets": excluded}
    if top1 > cfg["max_top_holder_pct"]:
        return False, "whale: biggest holder owns %.1f%% (max %s%%)" % (top1, cfg["max_top_holder_pct"]), details
    if top10 > cfg["max_top10_holders_pct"]:
        return False, "top 10 holders own %.1f%% (max %s%%)" % (top10, cfg["max_top10_holders_pct"]), details
    return True, "authorities off, top holder %.1f%%, top10 %.1f%%" % (top1, top10), details


def check_rugcheck(src, mint, cfg):
    rep = src.rugcheck(mint)
    if not isinstance(rep, dict):
        return False, "RugCheck report unknown", {}
    lp = rep.get("lpLockedPct")
    risks = rep.get("risks")
    if lp is None:
        return False, "LP lock unknown (RugCheck)", {}
    if risks is None:
        return False, "risk list unknown (RugCheck)", {}
    danger = [r.get("name", "?") for r in risks if str(r.get("level", "")).lower() == "danger"]
    details = {"lp_locked_pct": round(float(lp), 1), "danger_risks": danger}
    if float(lp) < cfg["min_lp_locked_pct"]:
        return False, "only %.0f%% of liquidity locked (need %s%%)" % (float(lp), cfg["min_lp_locked_pct"]), details
    if danger:
        return False, "RugCheck danger: " + ", ".join(danger), details
    return True, "LP %.0f%% locked, no danger risks" % float(lp), details


def full_check(src, mint, pair, cfg, now=None):
    """Returns (PASS|FAIL|WAIT, reason, details)."""
    status, reason = check_market(pair, cfg, now)
    if status != PASS:
        return status, reason, {}
    reasons, details = [reason], {}
    for check in (check_onchain, check_rugcheck):
        try:
            ok, why, d = check(src, mint, cfg)
        except (DataError, ValueError, TypeError, KeyError) as e:
            return FAIL, "data unavailable, counted as FAIL (%s)" % e, details
        details.update(d)
        if not ok:
            return FAIL, why, details
        reasons.append(why)
    return PASS, "; ".join(reasons), details
