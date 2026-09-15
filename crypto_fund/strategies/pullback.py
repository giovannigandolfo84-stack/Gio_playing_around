"""Strategy C - Pullback: buy controlled retracement to EMA20 in an established uptrend."""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, ema, last, rsi
from ..models import Candle, Side
from .base import Signal, Strategy


class PullbackStrategy(Strategy):
    name = "pullback"
    timeframe = "4h"
    params = {"touch_atr": 0.75, "atr_stop": 1.5, "rr": (2.0, 3.0), "rsi_lo": 38, "rsi_hi": 60}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        p = self.params
        if len(candles) < 120:
            return None
        closes = [c.close for c in candles]
        e20, e50 = ema(closes, 20), ema(closes, 50)
        a = last(atr(candles))
        r = last(rsi(closes))
        if not (a and e20[-1] and e50[-1] and e20[-10] and r is not None):
            return None
        uptrend = e20[-1] > e50[-1] and e20[-1] > e20[-10] and closes[-1] > e50[-1]
        c = candles[-1]
        touched = c.low <= e20[-1] + p["touch_atr"] * a and c.close > e20[-1] - 0.25 * a
        bounce = c.close > c.open
        if not (uptrend and touched and bounce and p["rsi_lo"] <= r <= p["rsi_hi"]):
            return None
        entry = c.close
        stop = min(c.low, e20[-1]) - p["atr_stop"] * a * 0.6
        if stop >= entry:
            return None
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, p["rr"]),
                      thesis=f"Pullback to rising EMA20 in uptrend, RSI {r:.0f}, bullish bar",
                      invalidation=f"Loss of pullback low {stop:.4g}", strength=55.0)
