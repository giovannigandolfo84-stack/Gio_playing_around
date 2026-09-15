"""Strategy A - Momentum: strong relative strength + volume expansion, trend-aligned."""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, ema, last, rsi
from ..models import Candle, Side
from .base import Signal, Strategy


class MomentumStrategy(Strategy):
    name = "momentum"
    timeframe = "4h"
    params = {"lookback": 30, "min_ret": 0.08, "vol_mult": 1.4, "atr_stop": 2.0, "rr": (2.0, 3.5), "max_rsi": 78}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        p = self.params
        if len(candles) < 120:
            return None
        closes = [c.close for c in candles]
        ret = closes[-1] / closes[-1 - p["lookback"]] - 1
        vols = [c.volume for c in candles]
        v_now, v_base = sum(vols[-6:]) / 6, sum(vols[-60:-6]) / 54
        e20, e50 = last(ema(closes, 20)), last(ema(closes, 50))
        a = last(atr(candles))
        r = last(rsi(closes))
        if not (a and e20 and e50 and r is not None):
            return None
        if ret < p["min_ret"] or v_now < p["vol_mult"] * v_base or not (closes[-1] > e20 > e50) or r > p["max_rsi"]:
            return None
        entry = closes[-1]
        stop = max(entry - p["atr_stop"] * a, e20 - 0.5 * a)
        if stop >= entry:
            return None
        strength = min(100.0, 50 + ret * 200 + (v_now / v_base - 1) * 15)
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, p["rr"]),
                      thesis=f"Momentum: +{ret:.1%} over {p['lookback']} bars with {v_now / v_base:.1f}x volume, trend aligned",
                      invalidation=f"Close below {stop:.4g} (EMA20 - 0.5 ATR / 2 ATR stop)", strength=strength)
