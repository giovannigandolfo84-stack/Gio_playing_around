"""Solana new-coin PAPER TRADING bot. Fake money only: no wallet, no keys, no real trades.

  python bot.py          -> live data, fake money, checks every 60 s
  python bot.py --demo   -> offline demo with 3 made-up coins
"""
import argparse
import json
import os
import sys
import time

import safety
from trader import Portfolio

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(HERE, "config.json")) as f:
        cfg = json.load(f)
    if cfg.get("mode") != "paper":
        sys.exit('REFUSING TO RUN: config.json must contain "mode": "paper". This bot only does fake trading.')
    return cfg


class Bot:
    def __init__(self, cfg, src, pf):
        self.cfg, self.src, self.pf = cfg, src, pf
        self.watch = {}   # young coins: mint -> first time we saw them
        self.done = set()  # coins we already decided on (skip or buy)

    def cycle(self):
        cfg, pf = self.cfg, self.pf

        # 1) Update prices of open trades and apply stop-loss / take-profit / time exit.
        if pf.s["open"]:
            try:
                pairs = self.src.best_pairs([p["mint"] for p in pf.s["open"]])
            except Exception as e:
                print("  could not refresh prices (%s), will retry next cycle" % e)
                pairs = None
            if pairs is not None:
                prices = {}
                for m, pair in pairs.items():
                    try:
                        prices[m] = float(pair.get("priceUsd"))
                    except (TypeError, ValueError):
                        pass
                pf.update_and_exit(prices)

        # 2) Find new coins.
        try:
            new = [m for m in self.src.latest_solana_mints() if m not in self.done and m not in self.watch]
        except Exception as e:
            print("  could not get new tokens (%s), will retry next cycle" % e)
            new = []
        now = time.time()
        for m in new:
            self.watch[m] = now
        candidates = [m for m in self.watch if not pf.holds(m)]

        # 3) Check each candidate; every rule must pass.
        pairs = {}
        if candidates:
            try:
                pairs = self.src.best_pairs(candidates)
            except Exception as e:
                print("  could not get pool data (%s), will retry next cycle" % e)
                candidates = []
        for mint in candidates:
            pair = pairs.get(mint)
            symbol = ((pair or {}).get("baseToken") or {}).get("symbol") or mint[:6]
            allowed, why_not = pf.buying_allowed()
            if not allowed:
                pf.log("SKIP", mint, symbol, "not checked: " + why_not)
                self.forget(mint)
                continue
            status, reason, details = safety.full_check(self.src, mint, pair, cfg)
            if status == safety.WAIT:
                age_watched = (time.time() - self.watch[mint]) / 60
                if age_watched >= cfg["recheck_young_for_minutes"]:
                    pf.log("SKIP", mint, symbol, "%s, gave up after %d min of re-checking"
                           % (reason, cfg["recheck_young_for_minutes"]))
                    self.forget(mint)
                elif mint in new:
                    pf.log("WAIT", mint, symbol, reason + " - will re-check for up to %d min"
                           % cfg["recheck_young_for_minutes"])
                continue
            if status == safety.FAIL:
                pf.log("SKIP", mint, symbol, reason, **details)
            else:
                pf.buy(mint, symbol, float(pair["priceUsd"]), pair.get("url"), "all checks passed: " + reason, details)
            self.forget(mint)
        pf.save()

    def forget(self, mint):
        self.watch.pop(mint, None)
        self.done.add(mint)


def main():
    ap = argparse.ArgumentParser(description="Solana paper-trading bot (fake money only)")
    ap.add_argument("--demo", action="store_true", help="offline demo with 3 made-up coins")
    ap.add_argument("--no-dashboard", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.demo:
        from demo_source import DemoSource
        src = DemoSource()
        pf_path, log_path, title = "data/demo_portfolio.json", "logs/demo_decisions.jsonl", "DEMO (made-up coins)"
        for p in (pf_path, log_path):  # demo always starts fresh
            if os.path.exists(os.path.join(HERE, p)):
                os.remove(os.path.join(HERE, p))
        interval, cycles = 3, 4
    else:
        from datasource import LiveSource
        src = LiveSource(cfg)
        pf_path, log_path, title = "data/portfolio.json", "logs/decisions.jsonl", "LIVE data, fake money"
        interval, cycles = cfg["loop_seconds"], None

    pf_path, log_path = os.path.join(HERE, pf_path), os.path.join(HERE, log_path)
    pf = Portfolio(cfg, pf_path, log_path)
    pf.save()
    bot = Bot(cfg, src, pf)

    port = cfg["dashboard_port"]
    if not args.no_dashboard:
        from dashboard import start_dashboard
        try:
            start_dashboard(port, pf_path, log_path, title)
        except OSError:
            sys.exit("Port %d is busy. The bot is probably already running in another window. "
                     "Close that window first (or press Ctrl+C in it)." % port)

    print("=" * 64)
    print(" PAPER TRADING BOT - FAKE MONEY ONLY (%s)" % title)
    print(" Dashboard: http://localhost:%d" % port)
    print(" Stop: press Ctrl+C in this window (or just close it)")
    print("=" * 64)

    n = 0
    try:
        while cycles is None or n < cycles:
            n += 1
            if args.demo:
                src.advance()
            print("\n--- cycle %d | balance $%.2f | open trades %d ---" % (n, pf.equity(), len(pf.s["open"])))
            try:
                bot.cycle()
            except Exception as e:  # never crash the loop; log and carry on
                print("  cycle error: %r (will retry)" % e)
            time.sleep(interval)
        print("\nDemo finished: 1 BUY, 2 SKIPs, 1 SELL. See the dashboard.")
        if not args.no_dashboard:
            print("The dashboard stays open. Press Ctrl+C (or close this window) to quit.")
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pf.save()
        print("\nStopped. Your fake portfolio is saved in", os.path.relpath(pf_path, HERE))


if __name__ == "__main__":
    main()
