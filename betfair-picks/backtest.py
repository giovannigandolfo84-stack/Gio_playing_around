"""Historical check of the strategy on football-data.co.uk CSVs (free, includes Pinnacle closing odds
and Betfair Exchange odds). Shows the REAL hit rate and ROI you would have had at each probability level.

  python backtest.py E0 SP1 I1 D1 F1 --seasons 2223 2324 2425
"""
import argparse
import csv
import io
import urllib.request

import model

URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"


def rows(div, season):
    with urllib.request.urlopen(URL.format(season=season, div=div), timeout=30) as r:
        yield from csv.DictReader(io.StringIO(r.read().decode("latin-1")))


def f(r, *keys):
    for k in keys:
        try:
            v = float(r.get(k) or "")
            if v > 1:
                return v
        except ValueError:
            pass
    return None


def run(divs, seasons, min_odds=1.4, max_odds=2.2, commission=0.05):
    buckets = {}
    for div in divs:
        for season in seasons:
            try:
                data = list(rows(div, season))
            except Exception as e:
                print("skip", div, season, e)
                continue
            for r in data:
                if not r.get("FTR"):
                    continue
                ps = [f(r, "PSCH", "PSH"), f(r, "PSCD", "PSD"), f(r, "PSCA", "PSA")]
                if None in ps:
                    continue
                fair = model.devig(ps)
                bet = [f(r, "BFECH", "BFEH"), f(r, "BFECD", "BFED"), f(r, "BFECA", "BFEA")]
                exch = None not in bet
                if not exch:
                    bet, commission_used = [f(r, "MaxCH", "MaxH"), f(r, "MaxCD", "MaxD"), f(r, "MaxCA", "MaxA")], 0
                    if None in bet:
                        continue
                else:
                    commission_used = commission
                i = max(range(3), key=lambda k: fair[k])
                o = bet[i]
                if not (min_odds <= o <= max_odds):
                    continue
                won = "HDA"[i] == r["FTR"]
                b = buckets.setdefault(int(fair[i] * 20) / 20, [0, 0, 0.0])
                b[0] += 1
                b[1] += won
                b[2] += (o - 1) * (1 - commission_used) if won else -1
    print(f"{'model prob':>10} {'bets':>6} {'hit rate':>9} {'ROI':>7}")
    tot = [0, 0, 0.0]
    for k in sorted(buckets):
        n, w, pl = buckets[k]
        tot = [tot[0] + n, tot[1] + w, tot[2] + pl]
        print(f"{k:>9.0%}+ {n:>6} {w / n:>9.1%} {pl / n:>+7.1%}")
    if tot[0]:
        print(f"{'ALL':>10} {tot[0]:>6} {tot[1] / tot[0]:>9.1%} {tot[2] / tot[0]:>+7.1%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("divs", nargs="*", default=["E0", "SP1", "I1", "D1", "F1"])
    ap.add_argument("--seasons", nargs="*", default=["2223", "2324", "2425"])
    a = ap.parse_args()
    run(a.divs, a.seasons)
