"""Strategy E - Narrative rotation: sector relative-strength breadth. Needs `ctx['sector_rs']`.

sector_rs: {narrative: mean 20d RS vs BTC across members}. Enter members of the
leading narrative that are themselves trend-aligned, with ATR stops.
"""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, ema, last
from ..models import Candle, Side
from .base import Signal, Strategy


class NarrativeRotationStrategy(Strategy):
    name = "narrative"
    timeframe = "1d"
    params = {"min_sector_rs": 0.06, "atr_stop": 2.0, "rr": (2.0, 3.5)}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        ctx = ctx or {}
        snap = ctx.get("snapshot")
        sector_rs = ctx.get("sector_rs") or {}
        if not snap or len(candles) < 60:
            return None
        rs = sector_rs.get(snap.narrative)
        if rs is None or rs < self.params["min_sector_rs"]:
            return None
        leader = max(sector_rs, key=sector_rs.get)
        if leader != snap.narrative:
            return None
        closes = [c.close for c in candles]
        e20, e50, a = last(ema(closes, 20)), last(ema(closes, 50)), last(atr(candles))
        if not (e20 and e50 and a) or not closes[-1] > e20 > e50:
            return None
        entry = closes[-1]
        stop = entry - self.params["atr_stop"] * a
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, self.params["rr"]),
                      thesis=f"Narrative rotation: '{snap.narrative}' leading with sector RS {rs:+.1%}",
                      invalidation=f"Sector RS turns negative or close < {stop:.4g}",
                      strength=min(100.0, 50 + rs * 300))
