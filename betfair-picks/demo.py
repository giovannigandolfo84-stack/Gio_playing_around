"""Synthetic fixtures so the dashboard can be tried without an API key. Not real matches or odds."""
import random
from datetime import datetime, timedelta, timezone

TEAMS = [("Northbridge", "Kingsport"), ("Ashford Utd", "Redcliffe"), ("Valemont", "Porto Branco"),
         ("Eastholm", "Saint Lucan"), ("Rivermouth", "Calder Town"), ("Monteverde", "Alsingen"),
         ("Brookfield", "Harrow Vale"), ("Westmere", "Lindqvist"), ("Oakhurst", "Ferrol CF"),
         ("Granton", "Boreham"), ("Sundby", "Ravensholt"), ("Castelmare", "Wexley"),
         ("Highmoor", "Tarrant"), ("Duncliffe", "Pellworth"), ("Marlow Rovers", "Kestrel"),
         ("Seaview", "Ironbridge"), ("Hollins", "Corvan"), ("Brackwater", "Elmstead"),
         ("Lowther", "Amberly"), ("Fenwick", "Sallow Park"), ("Rosmore", "Dunmere"), ("Kilbride", "Hexley"),
         ("Torvik", "Belcastro"), ("Wycombe Vale", "Norland"), ("Penrose", "Greystock"), ("Caldera", "Moorgate"),
         ("Ardmore", "Lancing"), ("Thornbury", "Velmar"), ("Esterly", "Rookwood"), ("Halden", "Varese Nord")]
BOOKS = ["betfair_ex_uk", "pinnacle", "matchbook", "williamhill", "paddypower", "skybet", "unibet_uk"]


def _prices(probs, margin, rng):
    noisy = [max(0.02, p * rng.uniform(0.96, 1.04)) for p in probs]
    s = sum(noisy)
    return [round(1 / (p / s * (1 + margin)), 2) for p in noisy]


def _elo(ph, pd, pa, po, rng):
    """Stand-in for ClubElo: an independent model that disagrees a little with the market."""
    h, a = ph * rng.uniform(0.92, 1.12), pa * rng.uniform(0.92, 1.12)
    s = h + pd + a
    o = min(0.95, po * rng.uniform(0.95, 1.08))
    return {"home": h / s, "draw": pd / s, "away": a / s, "over_2.5": o, "under_2.5": 1 - o}


def events(seed: int = 7):
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    out = []
    for i, (h, a) in enumerate(TEAMS):
        ph = rng.uniform(0.25, 0.78)
        pd = min(0.30, (1 - ph) * 0.45)
        pa = 1 - ph - pd
        po = rng.uniform(0.45, 0.80)
        kick = now + timedelta(hours=-1 if i < 3 else rng.uniform(2, 70))
        books = []
        for b in BOOKS:
            margin = {"betfair_ex_uk": 0.005, "pinnacle": 0.025, "matchbook": 0.01}.get(b, 0.06)
            books.append({"key": b, "markets": [
                {"key": "h2h", "outcomes": [dict(name=n, price=p) for n, p in
                                            zip([h, a, "Draw"], _prices([ph, pa, pd], margin, rng))]},
                {"key": "totals", "outcomes": [dict(name=n, price=p, point=2.5) for n, p in
                                               zip(["Over", "Under"], _prices([po, 1 - po], margin, rng))]}]})
        out.append({"id": f"demo{i}", "sport_key": "demo", "sport_title": "Demo League",
                    "commence_time": kick.isoformat().replace("+00:00", "Z"),
                    "home_team": h, "away_team": a, "bookmakers": books,
                    "_elo": _elo(ph, pd, pa, po, rng),
                    "score": f"{rng.randint(0, 2)}-{rng.randint(0, 1)}" if i < 3 else None})
    return out
