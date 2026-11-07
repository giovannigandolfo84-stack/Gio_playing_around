"""Optional MiroFish-style AI swarm: a panel of analyst agents debates each pick (with web search for
team news / injuries) and returns a small probability nudge. Capped at +/-5pp so it can never override
the market model. Enabled only when ANTHROPIC_API_KEY is set."""
import json
import re
import urllib.request

import config
import model

PANEL = ("tactical analyst", "team-news & injury scout", "xG/statistics modeller",
         "Betfair market trader", "professional sceptic")


def review(picks: list[dict]) -> list[dict]:
    if not config.ANTHROPIC_API_KEY or not picks:
        return picks
    brief = [{"i": i, "match": f"{p['home']} v {p['away']}", "comp": p["sport"], "kickoff": p["kickoff"],
              "live": p["live"], "bet": p["selection"], "model_prob": round(p["prob"], 3)}
             for i, p in enumerate(picks)]
    prompt = (
        "You are a swarm of independent football betting agents: " + ", ".join(PANEL) + ". "
        "For each bet below, search for the latest team news (injuries, suspensions, rotation, motivation, "
        "weather), let each agent give a view, then agree a probability adjustment between -0.05 and +0.05 "
        "relative to model_prob (0 if nothing material). Reply ONLY with a JSON array: "
        '[{"i":0,"adj":0.0,"reason":"<=20 words"}].\n' + json.dumps(brief))
    body = {"model": config.SWARM_MODEL, "max_tokens": 4000,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": config.ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
        text = "".join(b.get("text", "") for b in resp["content"] if b["type"] == "text")
        verdicts = json.loads(re.search(r"\[.*\]", text, re.S).group(0))
    except Exception as e:  # never break the dashboard because of the optional layer
        print("swarm skipped:", e)
        return picks
    for v in verdicts:
        p = picks[int(v["i"])]
        adj = max(-0.05, min(0.05, float(v.get("adj", 0))))
        p["prob"] = min(0.99, max(0.01, p["prob"] + 0.5 * adj))
        p["ev"] = p["prob"] * model.eff_odds(p["odds"], p["venue"] == "Betfair Exchange") - 1
        p["swarm"] = f"{adj * 100:+.0f}pp - {v.get('reason', '')}"
    return picks
