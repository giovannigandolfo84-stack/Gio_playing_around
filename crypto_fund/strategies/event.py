"""Strategy F - Event trading: substantive catalyst + technical confirmation, never hype alone."""
from __future__ import annotations

import re
from typing import Optional, Sequence

from ..indicators import atr, ema, last
from ..models import Candle, Side
from .base import Signal, Strategy

CATALYST = re.compile(r"\b(listing|mainnet|upgrade|launch(ed)?|partnership announced|integration)\b", re.I)


class EventStrategy(Strategy):
    name = "event"
    timeframe = "1h"
    params = {"atr_stop": 2.0, "rr": (2.0, 3.0), "max_move_before": 0.12}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        ctx = ctx or {}
        snap = ctx.get("snapshot")
        if not snap or len(candles) < 100:
            return None
        catalysts = [n for n in snap.news if CATALYST.search(n)]
        if not catalysts:
            return None
        closes = [c.close for c in candles]
        # if price already moved > max_move in last 24h, the news is priced in
        if closes[-1] / closes[-25] - 1 > self.params["max_move_before"]:
            return None
        e50, a = last(ema(closes, 50)), last(atr(candles))
        if not (e50 and a) or closes[-1] < e50:
            return None
        entry = closes[-1]
        stop = entry - self.params["atr_stop"] * a
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, self.params["rr"]),
                      thesis=f"Event: {catalysts[0][:80]} with price above EMA50 and <12% pre-move",
                      invalidation=f"Event fades / close < {stop:.4g}", strength=55.0)
