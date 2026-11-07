"""Free data sources: The Odds API (Betfair Exchange + bookmaker odds, live scores) and ClubElo (match model)."""
import csv
import io
import json
import time
import urllib.parse
import urllib.request

import config

ODDS_BASE = "https://api.the-odds-api.com/v4"
_cache: dict = {}


def _get(url: str, ttl_min: int = config.CACHE_MINUTES):
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < ttl_min * 60:
        return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": "betfair-picks/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
        remaining = r.headers.get("x-requests-remaining")
    if remaining is not None:
        _cache["__credits__"] = (time.time(), remaining)
    _cache[url] = (time.time(), body)
    return body


def credits_left():
    hit = _cache.get("__credits__")
    return hit[1] if hit else None


def odds(sport: str) -> list:
    q = urllib.parse.urlencode({
        "apiKey": config.ODDS_API_KEY, "bookmakers": config.BOOKMAKERS,
        "markets": "h2h,totals", "oddsFormat": "decimal",
    })
    return json.loads(_get(f"{ODDS_BASE}/sports/{sport}/odds?{q}"))


def scores(sport: str, days_from: int = 0, ttl_min: int = 5) -> list:
    q = {"apiKey": config.ODDS_API_KEY}
    if days_from:
        q["daysFrom"] = days_from
    return json.loads(_get(f"{ODDS_BASE}/sports/{sport}/scores?{urllib.parse.urlencode(q)}", ttl_min=ttl_min))


def clubelo_fixtures() -> list[dict]:
    """ClubElo's own forecasts for upcoming matches (goal-difference + exact-score probabilities)."""
    try:
        text = _get("http://api.clubelo.com/Fixtures", ttl_min=360)
    except Exception:
        return []
    return list(csv.DictReader(io.StringIO(text)))
