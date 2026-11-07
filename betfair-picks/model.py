"""Probability model + pick selection.

Probability = weighted blend of models that are already proven:
  * Pinnacle de-vigged odds (sharpest public market; the benchmark most pros use)
  * Market consensus (de-vigged average of ~10 UK books / exchanges)
  * ClubElo match forecasts (pre-match only)
Then we compare that probability with the Betfair Exchange price (after commission).
"""
import difflib
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

import config

SHARP_BOOKS = ("pinnacle", "betfair_ex_uk", "matchbook")
WEIGHTS = {"h2h": {"sharp": 0.5, "consensus": 0.25, "elo": 0.25},
           "totals": {"sharp": 0.55, "consensus": 0.3, "elo": 0.15}}

ALIASES = {
    "manchester city": "man city", "manchester united": "man united", "wolverhampton wanderers": "wolves",
    "tottenham hotspur": "tottenham", "brighton and hove albion": "brighton", "nottingham forest": "forest",
    "newcastle united": "newcastle", "west ham united": "west ham", "paris saint germain": "paris sg",
    "bayern munich": "bayern", "borussia dortmund": "dortmund", "inter milan": "inter",
    "atletico madrid": "atletico", "athletic bilbao": "bilbao", "psv eindhoven": "psv",
    "sheffield wednesday": "sheffield weds", "queens park rangers": "qpr", "borussia monchengladbach": "gladbach",
    "bayer leverkusen": "leverkusen", "rb leipzig": "rb leipzig", "sporting lisbon": "sporting",
}


# ---------- helpers ----------
def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("&", " and "))
    s = re.sub(r"\b(fc|afc|cf|ac|sc|ssc|as|club|de|the|calcio|1)\b", " ", s)
    s = " ".join(s.split())
    return ALIASES.get(s, s)


def same_team(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.78


def devig(prices: list[float]) -> list[float]:
    inv = [1 / p for p in prices]
    tot = sum(inv)
    return [x / tot for x in inv]


def eff_odds(price: float, exchange: bool) -> float:
    return 1 + (price - 1) * (1 - config.BETFAIR_COMMISSION) if exchange else price


# ---------- ClubElo ----------
def elo_probs(row: dict) -> dict:
    """Turn a ClubElo fixtures row into {home, draw, away, over_X, under_X} probabilities."""
    out = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for k, v in row.items():
        if not k or not k.startswith("GD"):
            continue
        p = float(v or 0)
        if k == "GD=0":
            out["draw"] += p
        elif k.startswith("GD>") or (k.startswith("GD=") and int(k[3:]) > 0):
            out["home"] += p
        else:
            out["away"] += p
    goals = {}
    for k, v in row.items():
        if k and k.startswith("R:"):
            h, a = k[2:].split("-")
            goals[int(h) + int(a)] = goals.get(int(h) + int(a), 0) + float(v or 0)
    if goals and sum(goals.values()) > 0.9:
        tot = sum(goals.values())
        for line in (0.5, 1.5, 2.5, 3.5, 4.5):
            under = sum(p for g, p in goals.items() if g < line) / tot
            out[f"under_{line}"], out[f"over_{line}"] = under, 1 - under
    s = out["home"] + out["draw"] + out["away"]
    if s <= 0:
        return {}
    for k in ("home", "draw", "away"):
        out[k] /= s
    return out


def find_elo(event: dict, fixtures: list[dict]) -> dict:
    day = event["commence_time"][:10]
    for row in fixtures:
        d = (row.get("Date") or "")[:10]
        if d and abs((datetime.fromisoformat(d) - datetime.fromisoformat(day)).days) > 1:
            continue
        if same_team(event["home_team"], row.get("Home", "")) and same_team(event["away_team"], row.get("Away", "")):
            return elo_probs(row)
    return {}


# ---------- candidates ----------
def _market_selections(event: dict) -> dict:
    """{selection_key: {"label", "market", "books": {book: (price, fair_prob)}}}"""
    sel: dict = {}
    home, away = event["home_team"], event["away_team"]
    for bk in event.get("bookmakers", []):
        for m in bk.get("markets", []):
            if m["key"] == "h2h" and len(m["outcomes"]) == 3:
                fair = devig([o["price"] for o in m["outcomes"]])
                for o, p in zip(m["outcomes"], fair):
                    key = "home" if o["name"] == home else "away" if o["name"] == away else "draw"
                    label = f"{o['name']} to win" if key != "draw" else "Draw"
                    sel.setdefault(key, {"label": label, "market": "h2h", "books": {}})["books"][bk["key"]] = (o["price"], p)
            elif m["key"] == "totals":
                by_point: dict = {}
                for o in m["outcomes"]:
                    by_point.setdefault(o.get("point"), []).append(o)
                for point, outs in by_point.items():
                    if len(outs) != 2:
                        continue
                    fair = devig([o["price"] for o in outs])
                    for o, p in zip(outs, fair):
                        key = f"{o['name'].lower()}_{point}"
                        sel.setdefault(key, {"label": f"{o['name']} {point} goals", "market": "totals",
                                             "books": {}})["books"][bk["key"]] = (o["price"], p)
    return sel


def evaluate(event: dict, elo: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    kickoff = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
    live = kickoff <= now
    out = []
    for key, s in _market_selections(event).items():
        books = s["books"]
        sharp_book = next((b for b in SHARP_BOOKS if b in books), None)
        comps = {}
        if sharp_book:
            comps["sharp"] = books[sharp_book][1]
        comps["consensus"] = statistics.mean(p for _, p in books.values())
        if elo.get(key) is not None and not live:
            comps["elo"] = elo[key]
        w = WEIGHTS[s["market"]]
        prob = sum(comps[c] * w[c] for c in comps) / sum(w[c] for c in comps)

        if "betfair_ex_uk" in books:
            price, venue, exchange = books["betfair_ex_uk"][0], "Betfair Exchange", True
        else:  # fall back to best UK price, flagged
            venue, (price, _) = max(books.items(), key=lambda kv: kv[1][0])
            exchange = venue in ("matchbook",)
        e_odds = eff_odds(price, exchange)
        ev = prob * e_odds - 1
        out.append({
            "event_id": event["id"], "sport_key": event.get("sport_key", ""), "sport": event.get("sport_title", event.get("sport_key", "")),
            "home": event["home_team"], "away": event["away_team"], "kickoff": event["commence_time"],
            "live": live, "selection": s["label"], "selection_key": key, "market": s["market"],
            "odds": price, "venue": venue, "prob": prob, "implied": 1 / price, "ev": ev,
            "components": comps, "spread": max(comps.values()) - min(comps.values()),
            "n_books": len(books),
        })
    return out


def kelly_stake(p: dict) -> float:
    eff = eff_odds(p["odds"], p["venue"] == "Betfair Exchange")
    if p["ev"] <= 0:
        return 0.0
    f = 0.25 * p["ev"] / (eff - 1)              # quarter Kelly
    return round(min(f, 0.03) * config.BANKROLL, 2)  # cap 3% of bankroll


def describe(p: dict) -> str:
    c = p["components"]
    parts = [f"Model {p['prob']:.0%} vs {p['venue']} implied {p['implied']:.0%} "
             f"({(p['prob'] - p['implied']) * 100:+.1f}pp)."]
    src = []
    if "sharp" in c:
        src.append(f"sharp market {c['sharp']:.0%}")
    src.append(f"{p['n_books']}-book consensus {c['consensus']:.0%}")
    if "elo" in c:
        src.append(f"ClubElo {c['elo']:.0%}")
    line = ", ".join(src)
    parts.append(line[0].upper() + line[1:] + ".")
    parts.append("Models agree." if p["spread"] < 0.05 else f"Models disagree by {p['spread']:.0%} - lower trust.")
    if p.get("swarm"):
        parts.append(f"AI panel: {p['swarm']}")
    return " ".join(parts)


def select(cands: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=config.HOURS_AHEAD)
    ok = [c for c in cands
          if config.MIN_ODDS <= c["odds"] <= config.MAX_ODDS and c["prob"] >= config.MIN_PROB
          and datetime.fromisoformat(c["kickoff"].replace("Z", "+00:00")) <= horizon]
    for c in ok:
        # rank: win chance first, value as a booster, penalise model disagreement
        c["score"] = c["prob"] + 0.75 * c["ev"] - 0.5 * max(0, c["spread"] - 0.05)
    best_per_event: dict = {}
    for c in sorted(ok, key=lambda x: x["score"], reverse=True):
        best_per_event.setdefault(c["event_id"], c)
    picks = sorted(best_per_event.values(), key=lambda x: x["score"], reverse=True)[: config.MAX_PICKS]
    for p in picks:
        if p["ev"] >= 0.02 and p["prob"] >= 0.65 and p["spread"] < 0.08:
            p["tier"] = "MONEY PICK"
        elif p["prob"] >= 0.70:
            p["tier"] = "HIGH CHANCE"
        else:
            p["tier"] = "SOLID"
        p["stake"] = kelly_stake(p)
        p["description"] = describe(p)
    return picks
