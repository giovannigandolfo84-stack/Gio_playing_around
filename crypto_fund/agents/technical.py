"""AGENT 2 - TECHNICAL ANALYST: multi-timeframe structure -> TECHNICAL_SCORE."""
from __future__ import annotations

from ..indicators import atr, ema, last, macd, rsi, support_resistance, vwap
from ..models import MarketSnapshot
from .base import Agent, AgentReport, clamp


def _structure(closes, highs, lows, n=20) -> str:
    """Higher-highs/higher-lows classification on the last 2n bars."""
    if len(closes) < 2 * n:
        return "unknown"
    hh = max(highs[-n:]) > max(highs[-2 * n:-n])
    hl = min(lows[-n:]) > min(lows[-2 * n:-n])
    if hh and hl:
        return "uptrend"
    if not hh and not hl:
        return "downtrend"
    return "range"


class TechnicalAnalyst(Agent):
    name = "technical"
    llm_prompt_key = "technical"

    def heuristic(self, snap: MarketSnapshot, ctx: dict) -> AgentReport:
        score, why, flags, data = 50.0, [], [], {}
        weights = {"1d": 0.35, "4h": 0.3, "1h": 0.2, "15m": 0.1, "5m": 0.05}
        structures = {}
        for tf, w in weights.items():
            cs = snap.candles.get(tf)
            if not cs or len(cs) < 60:
                continue
            closes = [c.close for c in cs]
            st = _structure(closes, [c.high for c in cs], [c.low for c in cs])
            structures[tf] = st
            e20, e50 = last(ema(closes, 20)), last(ema(closes, 50))
            tf_score = 0.0
            if st == "uptrend":
                tf_score += 20
            elif st == "downtrend":
                tf_score -= 20
            if e20 and e50:
                tf_score += 10 if closes[-1] > e20 > e50 else (-10 if closes[-1] < e20 < e50 else 0)
            r = last(rsi(closes))
            if r is not None:
                data[f"rsi_{tf}"] = r
                if r > 80:
                    tf_score -= 10; flags.append(f"RSI {tf} overbought ({r:.0f})")
                elif r < 25:
                    tf_score -= 5
                elif 50 <= r <= 70:
                    tf_score += 5
            _, _, hist = macd(closes)
            h = last(hist)
            if h is not None:
                tf_score += 5 if h > 0 else -5
            score += tf_score * w
        # extension vs ATR
        c4h = snap.candles["4h"]
        a = last(atr(c4h))
        e20_4h = last(ema([c.close for c in c4h], 20))
        if a and e20_4h:
            ext = (snap.price - e20_4h) / a
            data["atr_extension_4h"] = ext
            data["atr_4h_pct"] = a / snap.price
            if ext > 3:
                score -= 12; flags.append(f"Overextended: {ext:.1f} ATR above 4h EMA20")
            elif 0 < ext < 1.5:
                score += 5; why.append("Trending but not overextended")
        v = vwap(snap.candles["1h"], 24)
        if v:
            data["vwap_dist_pct"] = (snap.price - v) / v
        lo, hi = support_resistance(c4h, 50)
        data["support"], data["resistance"] = lo, hi
        aligned = sum(1 for s in structures.values() if s == "uptrend")
        if aligned >= 3:
            why.append(f"Uptrend on {aligned} timeframes")
        elif sum(1 for s in structures.values() if s == "downtrend") >= 3:
            why.append("Downtrend on majority of timeframes")
        data["structure_1d"] = {"uptrend": 1.0, "range": 0.0, "downtrend": -1.0, "unknown": 0.0}[structures.get("1d", "unknown")]
        return AgentReport(self.name, snap.symbol, clamp(score), 0.65, why, flags, data)
