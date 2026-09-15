"""Strategy B - Breakout: confirmed close above N-bar high with volume confirmation."""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, last
from ..models import Candle, Side
from .base import Signal, Strategy


class BreakoutStrategy(Strategy):
    name = "breakout"
    timeframe = "4h"
    params = {"lookback": 50, "vol_mult": 1.5, "atr_stop": 1.5, "rr": (2.0, 4.0), "max_ext_atr": 2.0}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        p = self.params
        if len(candles) < p["lookback"] + 30:
            return None
        window = candles[-1 - p["lookback"]:-1]
        hi = max(c.high for c in window)
        c = candles[-1]
        a = last(atr(candles))
        if not a:
            return None
        vols = [x.volume for x in candles]
        v_base = sum(vols[-31:-1]) / 30
        if c.close <= hi or c.volume < p["vol_mult"] * v_base:
            return None
        if (c.close - hi) / a > p["max_ext_atr"]:
            return None  # chased too far
        entry = c.close
        stop = min(hi - 0.25 * a, entry - p["atr_stop"] * a)
        if stop >= entry:
            return None
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, p["rr"]),
                      thesis=f"Breakout above {p['lookback']}-bar high {hi:.4g} on {c.volume / v_base:.1f}x volume",
                      invalidation=f"Close back inside range below {stop:.4g}",
                      strength=min(100.0, 55 + (c.volume / v_base - 1) * 15))
