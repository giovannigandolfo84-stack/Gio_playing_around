import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo, model, tracker  # noqa: E402


def test_devig_sums_to_one():
    assert abs(sum(model.devig([1.5, 4.2, 6.5])) - 1) < 1e-9


def test_elo_row_parsing():
    row = {"Date": "2026-11-08", "Home": "Arsenal", "Away": "Everton", "GD=0": "0.25", "GD=1": "0.35",
           "GD>5": "0.05", "GD=-1": "0.35", "R:0-0": "0.1", "R:1-0": "0.3", "R:1-1": "0.2", "R:2-1": "0.4"}
    p = model.elo_probs(row)
    assert abs(p["home"] + p["draw"] + p["away"] - 1) < 1e-9
    assert abs(p["over_2.5"] - 0.4) < 1e-9


def test_team_matching():
    assert model.same_team("Manchester City", "Man City")
    assert model.same_team("Wolverhampton Wanderers", "Wolves")
    assert not model.same_team("Arsenal", "Chelsea")


def test_selection_respects_rules():
    cands = []
    for e in demo.events():
        cands += model.evaluate(e, e["_elo"])
    picks = model.select(cands)
    assert 0 < len(picks) <= 15
    assert all(p["odds"] >= 1.4 and p["prob"] >= 0.6 for p in picks)
    assert len({p["event_id"] for p in picks}) == len(picks)
    assert all(p["stake"] == 0 for p in picks if p["ev"] <= 0)


def test_live_ignores_elo():
    e = demo.events()[0]
    e["commence_time"] = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    assert all("elo" not in c["components"] for c in model.evaluate(e, e["_elo"]))


def test_settlement():
    assert tracker.outcome("home", 2, 1) == "won"
    assert tracker.outcome("over_2.5", 1, 1) == "lost"
    assert tracker.outcome("under_2.5", 1, 1) == "won"
