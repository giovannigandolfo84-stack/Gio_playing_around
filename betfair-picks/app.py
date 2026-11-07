"""Dashboard server.  python app.py            -> http://localhost:8050
                     python app.py --once     -> print picks in the terminal
                     python app.py --demo     -> synthetic data, no API key needed"""
import json
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config
import demo
import model
import sources
import swarm
import tracker

DEMO = "--demo" in sys.argv or not config.ODDS_API_KEY
_state = {"t": 0, "data": None}


def build() -> dict:
    errors, cands, live_scores = [], [], {}
    if DEMO:
        evs, fixtures = demo.events(), []
        live_scores = {e["id"]: e["score"] for e in evs if e.get("score")}
    else:
        fixtures, evs = sources.clubelo_fixtures(), []
        for lg in config.LEAGUES:
            try:
                got = sources.odds(lg)
            except Exception as e:
                errors.append(f"{lg}: {e}")
                continue
            evs += got
            if any(e["commence_time"] <= datetime.now(timezone.utc).isoformat() for e in got):
                try:
                    for s in sources.scores(lg):
                        if s.get("scores") and not s.get("completed"):
                            sc = {x["name"]: x["score"] for x in s["scores"]}
                            live_scores[s["id"]] = f"{sc.get(s['home_team'], 0)}-{sc.get(s['away_team'], 0)}"
                except Exception as e:
                    errors.append(f"scores {lg}: {e}")
    for e in evs:
        cands += model.evaluate(e, e.get("_elo") or model.find_elo(e, fixtures))
    picks = model.select(cands)
    picks = swarm.review(picks)
    for p in picks:
        p["description"] = model.describe(p)
        p["live_score"] = live_scores.get(p["event_id"])
    if not DEMO:
        tracker.record(picks)
        for sk in tracker.pending_sports():
            try:
                tracker.settle(sources.scores(sk, days_from=3, ttl_min=60))
            except Exception as e:
                errors.append(f"settle {sk}: {e}")
    return {"generated": datetime.now(timezone.utc).isoformat(), "demo": DEMO, "picks": picks,
            "events_scanned": len(evs), "candidates": len(cands), "credits_left": sources.credits_left(),
            "track": tracker.stats() if not DEMO else None, "errors": errors,
            "settings": {"min_odds": config.MIN_ODDS, "max_odds": config.MAX_ODDS, "min_prob": config.MIN_PROB,
                         "bankroll": config.BANKROLL, "swarm": bool(config.ANTHROPIC_API_KEY)}}


def data(force=False):
    if force or not _state["data"] or time.time() - _state["t"] > config.CACHE_MINUTES * 60:
        _state["data"], _state["t"] = build(), time.time()
    return _state["data"]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/picks"):
            body, ctype = json.dumps(data("refresh=1" in self.path)).encode(), "application/json"
        elif self.path in ("/", "/index.html"):
            body, ctype = Path(__file__).with_name("static").joinpath("index.html").read_bytes(), "text/html"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--once" in sys.argv:
        d = data()
        for i, p in enumerate(d["picks"], 1):
            print(f"{i:2}. [{p['tier']:11}] {p['home']} v {p['away']} | {p['selection']} @ {p['odds']:.2f} "
                  f"| win {p['prob']:.0%} | EV {p['ev']:+.1%} | stake {p['stake']}")
            print("    " + p["description"])
        print(f"\n{d['events_scanned']} events scanned, demo={d['demo']}, credits left={d['credits_left']}")
        for e in d["errors"]:
            print("!", e)
    else:
        print(f"Dashboard: http://localhost:{config.PORT}  (demo={DEMO})")
        ThreadingHTTPServer(("0.0.0.0", config.PORT), H).serve_forever()
