"""Pure-python technical indicators (no numpy dependency)."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .models import Candle


def sma(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    seed = sum(values[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], n: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ef, es = ema(values, fast), ema(values, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(ef, es)]
    valid = [v for v in line if v is not None]
    sig_valid = ema(valid, signal) if len(valid) >= signal else [None] * len(valid)
    sig: List[Optional[float]] = [None] * (len(line) - len(valid)) + sig_valid
    hist = [None if a is None or b is None else a - b for a, b in zip(line, sig)]
    return line, sig, hist


def atr(candles: Sequence[Candle], n: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(candles)
    if len(candles) <= n:
        return out
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c.high - c.low)
        else:
            pc = candles[i - 1].close
            trs.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
    a = sum(trs[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(candles)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


def vwap(candles: Sequence[Candle], n: int = 20) -> Optional[float]:
    window = candles[-n:]
    vol = sum(c.volume for c in window)
    if vol == 0:
        return None
    return sum(((c.high + c.low + c.close) / 3) * c.volume for c in window) / vol


def returns(values: Sequence[float]) -> List[float]:
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1] > 0]


def realized_vol(values: Sequence[float], n: int = 20) -> Optional[float]:
    r = returns(values)[-n:]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def zscore(values: Sequence[float], n: int = 20) -> Optional[float]:
    w = values[-n:]
    if len(w) < n:
        return None
    m = sum(w) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in w) / (n - 1))
    return 0.0 if sd == 0 else (values[-1] - m) / sd


def support_resistance(candles: Sequence[Candle], lookback: int = 50) -> Tuple[float, float]:
    w = candles[-lookback:]
    return min(c.low for c in w), max(c.high for c in w)


def relative_strength(values: Sequence[float], bench: Sequence[float], n: int = 20) -> Optional[float]:
    if len(values) <= n or len(bench) <= n:
        return None
    a = values[-1] / values[-1 - n] - 1
    b = bench[-1] / bench[-1 - n] - 1
    return a - b


def correlation(a: Sequence[float], b: Sequence[float], n: int = 30) -> Optional[float]:
    ra, rb = returns(a)[-n:], returns(b)[-n:]
    m = min(len(ra), len(rb))
    if m < 5:
        return None
    ra, rb = ra[-m:], rb[-m:]
    ma, mb = sum(ra) / m, sum(rb) / m
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return None if va == 0 or vb == 0 else cov / (va * vb)


def last(seq: Sequence[Optional[float]]) -> Optional[float]:
    for v in reversed(seq):
        if v is not None:
            return v
    return None
