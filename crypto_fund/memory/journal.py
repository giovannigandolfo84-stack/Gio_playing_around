"""MEMORY: SQLite journal of every decision, trade and portfolio snapshot."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import TradeRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp REAL NOT NULL, asset TEXT NOT NULL, strategy TEXT NOT NULL, side TEXT NOT NULL,
  entry REAL, exit REAL, position_size REAL, stop REAL, target REAL, result TEXT,
  pnl_usd REAL, r_multiple REAL, mfe REAL, mae REAL, market_regime TEXT,
  agent_scores TEXT, thesis TEXT, exit_reason TEXT, mistake_classification TEXT,
  fees_usd REAL, plan_id TEXT, holding_hours REAL
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, asset TEXT, strategy TEXT, decision TEXT,
  trade_quality REAL, composite REAL, regime TEXT, veto INTEGER, reasons TEXT, plan TEXT, sizing TEXT, executed INTEGER
);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, equity REAL, cash REAL, drawdown REAL,
  open_positions INTEGER, regime TEXT, mode TEXT, limits_hash TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, level TEXT, kind TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS positions (
  id TEXT PRIMARY KEY, symbol TEXT, strategy TEXT, side TEXT, entry REAL, quantity REAL, stop REAL,
  targets TEXT, opened_at REAL, plan_id TEXT, narrative TEXT, mfe REAL, mae REAL, trailing_stop REAL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


class Journal:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- trades
    def record_trade(self, t: TradeRecord) -> None:
        d = t.to_dict()
        d["agent_scores"] = json.dumps(d["agent_scores"])
        cols = ", ".join(d)
        self.conn.execute(f"INSERT INTO trades ({cols}) VALUES ({', '.join('?' for _ in d)})", list(d.values()))
        self.conn.commit()

    def trades(self, since: Optional[float] = None) -> List[Dict[str, Any]]:
        q = "SELECT * FROM trades" + (" WHERE timestamp >= ?" if since else "") + " ORDER BY timestamp"
        rows = self.conn.execute(q, (since,) if since else ()).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["agent_scores"] = json.loads(d["agent_scores"] or "{}")
            out.append(d)
        return out

    # ---- decisions
    def record_decision(self, asset: str, strategy: str, decision: str, quality: float, composite: float,
                        regime: str, veto: bool, reasons: List[str], plan: dict, sizing: dict, executed: bool) -> None:
        self.conn.execute(
            "INSERT INTO decisions (timestamp, asset, strategy, decision, trade_quality, composite, regime, veto, reasons, plan, sizing, executed)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), asset, strategy, decision, quality, composite, regime, int(veto), json.dumps(reasons),
             json.dumps(plan, default=str), json.dumps(sizing, default=str), int(executed)))
        self.conn.commit()

    def decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?", (limit,))]

    # ---- snapshots / events / state
    def snapshot(self, equity: float, cash: float, dd: float, n_pos: int, regime: str, mode: str, limits_hash: str) -> None:
        self.conn.execute("INSERT INTO snapshots (timestamp, equity, cash, drawdown, open_positions, regime, mode, limits_hash) VALUES (?,?,?,?,?,?,?,?)",
                          (time.time(), equity, cash, dd, n_pos, regime, mode, limits_hash))
        self.conn.commit()

    def snapshots(self, limit: int = 500) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT ?", (limit,))][::-1]

    def event(self, level: str, kind: str, message: str) -> None:
        self.conn.execute("INSERT INTO events (timestamp, level, kind, message) VALUES (?,?,?,?)", (time.time(), level, kind, message))
        self.conn.commit()

    def events(self, limit: int = 50):
        return [dict(r) for r in self.conn.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))]

    def set(self, key: str, value: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        r = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def save_positions(self, positions) -> None:
        self.conn.execute("DELETE FROM positions")
        for p in positions:
            self.conn.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (p.id, p.symbol, p.strategy, p.side.value, p.entry, p.quantity, p.stop, json.dumps(p.targets),
                               p.opened_at, p.plan_id, p.narrative, p.mfe, p.mae, p.trailing_stop))
        self.conn.commit()

    def load_positions(self):
        from ..models import Position, Side
        out = []
        for r in self.conn.execute("SELECT * FROM positions"):
            out.append(Position(r["symbol"], r["strategy"], Side(r["side"]), r["entry"], r["quantity"], r["stop"],
                                json.loads(r["targets"]), r["opened_at"], r["plan_id"], r["narrative"], r["mfe"], r["mae"],
                                r["trailing_stop"], r["id"]))
        return out
