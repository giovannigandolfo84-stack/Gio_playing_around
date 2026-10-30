"""Fake-money portfolio. Only numbers in a JSON file; no wallet, no real trades."""
import json
import os
import time
from datetime import datetime


def now_iso(t=None):
    return datetime.fromtimestamp(t or time.time()).astimezone().isoformat(timespec="seconds")


def today():
    return datetime.now().strftime("%Y-%m-%d")


class Portfolio:
    def __init__(self, cfg, path, log_path):
        self.cfg = cfg
        self.path = path
        self.log_path = log_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if os.path.exists(path):
            with open(path) as f:
                self.s = json.load(f)
        else:
            start = float(cfg["starting_balance_usd"])
            self.s = {"starting_balance": start, "cash": start, "open": [], "closed": [],
                      "day": today(), "day_start_equity": start, "halted_day": None}
        self.fee = cfg["fee_slippage_pct"] / 100

    # ---------- bookkeeping ----------
    def save(self):
        self.s["updated_at"] = now_iso()
        self.s["equity"] = round(self.equity(), 2)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.s, f, indent=2)
        os.replace(tmp, self.path)

    def log(self, action, mint, symbol, reason, **extra):
        row = {"time": now_iso(), "action": action, "symbol": symbol, "mint": mint, "reason": reason}
        row.update(extra)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        print("%s  %-5s %-10s %s" % (row["time"][11:19], action, (symbol or "?")[:10], reason))

    def equity(self):
        return self.s["cash"] + sum(p["tokens"] * p["last_price"] for p in self.s["open"])

    def holds(self, mint):
        return any(p["mint"] == mint for p in self.s["open"])

    # ---------- daily loss limit ----------
    def buying_allowed(self):
        """(True, '') or (False, why)"""
        if self.s["day"] != today():
            self.s["day"], self.s["day_start_equity"], self.s["halted_day"] = today(), self.equity(), None
        if self.s["halted_day"] == today():
            return False, "daily loss limit hit, no buying until tomorrow"
        start = self.s["day_start_equity"]
        drop = (self.equity() - start) / start * 100 if start else 0
        if drop <= -self.cfg["daily_loss_limit_pct"]:
            self.s["halted_day"] = today()
            self.log("HALT", None, None, "down %.1f%% today (limit %s%%): no more buying today"
                     % (-drop, self.cfg["daily_loss_limit_pct"]))
            return False, "daily loss limit hit, no buying until tomorrow"
        if len(self.s["open"]) >= self.cfg["max_open_trades"]:
            return False, "already %d open trades (max %d)" % (len(self.s["open"]), self.cfg["max_open_trades"])
        return True, ""

    # ---------- trades ----------
    def buy(self, mint, symbol, price, pair_url, reason, details):
        size = round(self.equity() * self.cfg["trade_size_pct"] / 100, 2)
        if size > self.s["cash"] or size <= 0:
            self.log("SKIP", mint, symbol, "not enough fake cash")
            return
        tokens = size * (1 - self.fee) / price  # 3% lost to fees/slippage on the way in
        self.s["cash"] -= size
        self.s["open"].append({"mint": mint, "symbol": symbol, "url": pair_url, "entry_time": time.time(),
                               "entry_price": price, "cost_usd": size, "tokens": tokens,
                               "last_price": price, "missing_cycles": 0})
        self.log("BUY", mint, symbol, reason, usd=size, price=price, **details)

    def sell(self, pos, price, why):
        proceeds = pos["tokens"] * price * (1 - self.fee)  # 3% lost again on the way out
        pnl = proceeds - pos["cost_usd"]
        self.s["cash"] += proceeds
        self.s["open"].remove(pos)
        pos.update({"exit_time": time.time(), "exit_price": price, "proceeds_usd": round(proceeds, 2),
                    "pnl_usd": round(pnl, 2), "pnl_pct": round(pnl / pos["cost_usd"] * 100, 2), "exit_reason": why})
        self.s["closed"].append(pos)
        self.log("SELL", pos["mint"], pos["symbol"], "%s | P/L $%.2f (%+.1f%%)" % (why, pnl, pos["pnl_pct"]),
                 price=price, pnl_usd=round(pnl, 2))

    def update_and_exit(self, prices):
        """prices: {mint: current price or None}. Applies stop-loss / take-profit / time exit."""
        c = self.cfg
        for pos in list(self.s["open"]):
            price = prices.get(pos["mint"])
            if price:
                pos["last_price"], pos["missing_cycles"] = price, 0
            else:
                pos["missing_cycles"] += 1
                if pos["missing_cycles"] >= c["missing_price_cycles_before_assume_rug"]:
                    self.sell(pos, 0.0, "price gone for %d checks, assuming rug (sold at $0)" % pos["missing_cycles"])
                    continue
            change = (pos["last_price"] / pos["entry_price"] - 1) * 100
            held_h = (time.time() - pos["entry_time"]) / 3600
            if change <= c["stop_loss_pct"]:
                self.sell(pos, pos["last_price"], "stop-loss: price %+.1f%%" % change)
            elif change >= c["take_profit_pct"]:
                self.sell(pos, pos["last_price"], "take-profit: price %+.1f%%" % change)
            elif held_h >= c["max_hold_hours"]:
                self.sell(pos, pos["last_price"], "time exit after %.1fh (price %+.1f%%)" % (held_h, change))
