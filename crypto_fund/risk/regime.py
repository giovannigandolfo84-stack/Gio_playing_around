"""Market regime detection from BTC daily data (+ETH confirmation)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..indicators import ema, realized_vol, last
from ..models import Candle, Regime


@dataclass
class RegimeState:
    regime: Regime
    risk_on: bool
    vol_daily: float
    trend_score: float  # -1..1


def detect_regime(btc_1d: List[Candle], eth_1d: List[Candle] | None = None) -> RegimeState:
    closes = [c.close for c in btc_1d]
    if len(closes) < 60:
        return RegimeState(Regime.SIDEWAYS, False, 0.0, 0.0)
    e20, e50, e200 = last(ema(closes, 20)), last(ema(closes, 50)), last(ema(closes, 200))
    px = closes[-1]
    vol = realized_vol(closes, 20) or 0.0
    trend = 0.0
    if e20 and e50:
        trend += 0.5 if px > e20 > e50 else (-0.5 if px < e20 < e50 else 0.0)
    if e200:
        trend += 0.5 if px > e200 else -0.5
    ret30 = closes[-1] / closes[-30] - 1
    trend += max(-0.5, min(0.5, ret30 * 2))
    trend = max(-1.0, min(1.0, trend))
    if eth_1d and len(eth_1d) >= 30:
        ec = [c.close for c in eth_1d]
        eth_ret = ec[-1] / ec[-30] - 1
        trend = 0.8 * trend + 0.2 * max(-1.0, min(1.0, eth_ret * 2))

    if vol > 0.07:
        regime = Regime.EXTREME_VOL
    elif vol > 0.045:
        regime = Regime.HIGH_VOL
    elif trend > 0.35:
        regime = Regime.BULL
    elif trend < -0.35:
        regime = Regime.BEAR
    else:
        regime = Regime.SIDEWAYS
    risk_on = regime in (Regime.BULL,) or (regime == Regime.SIDEWAYS and trend > 0)
    return RegimeState(regime, risk_on, vol, trend)
