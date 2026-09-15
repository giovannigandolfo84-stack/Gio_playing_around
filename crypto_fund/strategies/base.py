"""Strategy interface. A strategy converts candles into a fully specified TradePlan or None.

Each strategy exposes `signal(candles, ctx)` for backtesting on a single
timeframe series and `propose(snapshot, ctx)` for live/paper use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..models import Candle, MarketSnapshot, Side, TradePlan


@dataclass
class Signal:
    side: Side
    entry: float
    stop: float
    targets: List[float]
    thesis: str
    invalidation: str
    strength: float = 50.0  # 0-100 momentum/quality hint used by PM as "momentum" input


class Strategy:
    name = "base"
    timeframe = "4h"
    params: dict = {}

    def __init__(self, **overrides):
        self.params = {**self.params, **overrides}

    def signal(self, candles: Sequence[Candle], ctx: dict | None = None) -> Optional[Signal]:  # pragma: no cover
        raise NotImplementedError

    def propose(self, snap: MarketSnapshot, ctx: dict | None = None) -> Optional[TradePlan]:
        cs = snap.candles.get(self.timeframe)
        if not cs:
            return None
        sig = self.signal(cs, ctx or {"snapshot": snap})
        if not sig:
            return None
        return TradePlan(symbol=snap.symbol, strategy=self.name, side=sig.side, entry=sig.entry, stop=sig.stop,
                         targets=sig.targets, thesis=sig.thesis, invalidation=sig.invalidation,
                         narrative=snap.narrative, timeframe=self.timeframe)

    @staticmethod
    def targets_from_r(entry: float, stop: float, rr: Sequence[float] = (2.0, 3.5)) -> List[float]:
        risk = entry - stop
        return [entry + risk * r for r in rr]
