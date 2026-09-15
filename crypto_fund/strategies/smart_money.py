"""Strategy G - On-chain smart money: exchange outflows + distributed holders + trend."""
from __future__ import annotations

from typing import Optional, Sequence

from ..indicators import atr, ema, last
from ..models import Candle, Side
from .base import Signal, Strategy


class SmartMoneyStrategy(Strategy):
    name = "smart_money"
    timeframe = "1d"
    params = {"min_outflow_ratio": 0.02, "atr_stop": 2.0, "rr": (2.5, 4.0)}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:
        ctx = ctx or {}
        snap = ctx.get("snapshot")
        if not snap or snap.exchange_netflow_usd_24h is None or not snap.volume_24h_usd or len(candles) < 60:
            return None
        nf = snap.exchange_netflow_usd_24h / snap.volume_24h_usd
        if nf > -self.params["min_outflow_ratio"]:
            return None
        if snap.holder_top10_pct is not None and snap.holder_top10_pct > 0.5:
            return None
        closes = [c.close for c in candles]
        e50, a = last(ema(closes, 50)), last(atr(candles))
        if not (e50 and a) or closes[-1] < e50:
            return None
        entry = closes[-1]
        stop = entry - self.params["atr_stop"] * a
        return Signal(Side.BUY, entry, stop, self.targets_from_r(entry, stop, self.params["rr"]),
                      thesis=f"Smart money: net exchange outflow {nf:.1%} of volume, distributed holders, above EMA50",
                      invalidation=f"Flows flip to inflow or close < {stop:.4g}", strength=50.0)
