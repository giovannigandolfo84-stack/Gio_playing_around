"""Strategy D - Mean reversion: statistically abnormal short-term drop in a non-bear regime."""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, ema, last, rsi, zscore
from ..models import Candle, Side
from .base import Signal, Strategy


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    timeframe = "1h"
    params = {"z": -2.5, "n": 48, "rsi_max": 28, "atr_stop": 1.5, "rr": (2.0,)}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        p = self.params
        if len(candles) < 250:
            return None
        closes = [c.close for c in candles]
        z = zscore(closes, p["n"])
        r = last(rsi(closes))
        a = last(atr(candles))
        e200 = last(ema(closes, 200))
        if z is None or r is None or not a or not e200:
            return None
        if z > p["z"] or r > p["rsi_max"] or closes[-1] < e200 * 0.9:
            return None
        entry = closes[-1]
        stop = entry - p["atr_stop"] * a
        mean = sum(closes[-p["n"]:]) / p["n"]
        target = min(mean, entry + (entry - stop) * 2.5)
        if target <= entry + (entry - stop) * 2.0:
            return None
        return Signal(Side.BUY, entry, stop, [target],
                      thesis=f"Mean reversion: z={z:.1f}, RSI {r:.0f}, still above 0.9x EMA200",
                      invalidation=f"Continuation below {stop:.4g}", strength=45.0)
