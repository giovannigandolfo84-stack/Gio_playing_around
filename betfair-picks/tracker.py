"""Stores every pick shown and settles it from final scores, so the real hit rate is always visible."""
import sqlite3

import config


def _db():
    con = sqlite3.connect(config.DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS picks(
        event_id TEXT, selection_key TEXT, sport_key TEXT, home TEXT, away TEXT, kickoff TEXT,
        selection TEXT, odds REAL, prob REAL, tier TEXT, result TEXT,
        PRIMARY KEY(event_id, selection_key))""")
    return con


def record(picks: list[dict]):
    with _db() as con:
        for p in picks:
            if p["live"]:
                continue  # only pre-match picks count toward the track record
            con.execute("INSERT OR IGNORE INTO picks VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                        (p["event_id"], p["selection_key"], p.get("sport_key", ""), p["home"], p["away"],
                         p["kickoff"], p["selection"], p["odds"], p["prob"], p["tier"]))


def outcome(key: str, hg: int, ag: int) -> str:
    if key == "home":
        win = hg > ag
    elif key == "away":
        win = ag > hg
    elif key == "draw":
        win = hg == ag
    else:
        side, line = key.split("_")
        win = (hg + ag > float(line)) if side == "over" else (hg + ag < float(line))
    return "won" if win else "lost"


def settle(score_rows: list[dict]):
    done = {s["id"]: s for s in score_rows if s.get("completed") and s.get("scores")}
    with _db() as con:
        for eid, key, home in con.execute("SELECT event_id, selection_key, home FROM picks WHERE result IS NULL").fetchall():
            s = done.get(eid)
            if not s:
                continue
            sc = {x["name"]: int(x["score"]) for x in s["scores"]}
            hg, ag = sc.get(s["home_team"], 0), sc.get(s["away_team"], 0)
            con.execute("UPDATE picks SET result=? WHERE event_id=? AND selection_key=?",
                        (outcome(key, hg, ag), eid, key))


def pending_sports() -> set:
    with _db() as con:
        return {r[0] for r in con.execute("SELECT DISTINCT sport_key FROM picks WHERE result IS NULL") if r[0]}


def stats() -> dict:
    with _db() as con:
        rows = con.execute("SELECT tier, odds, result FROM picks WHERE result IS NOT NULL").fetchall()
    def agg(rs):
        n = len(rs)
        won = sum(1 for r in rs if r[2] == "won")
        profit = sum((r[1] - 1) * (1 - config.BETFAIR_COMMISSION) if r[2] == "won" else -1 for r in rs)
        return {"n": n, "won": won, "hit_rate": won / n if n else None, "roi": profit / n if n else None}
    out = {"all": agg(rows)}
    for t in ("MONEY PICK", "HIGH CHANCE", "SOLID"):
        out[t] = agg([r for r in rows if r[0] == t])
    return out
