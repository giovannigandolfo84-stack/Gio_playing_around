"""Market data providers.

All providers implement `snapshot(symbol)` -> MarketSnapshot and `candles(symbol, tf, n)`.
- SyntheticProvider: deterministic, offline, used for tests/backtests/paper demos.
- BinancePublicProvider: public REST (no key) via urllib, for live paper trading.
- CSVProvider: load your own OHLCV history for backtests.

External data is UNTRUSTED. Providers only return numbers/strings; nothing here
ever executes anything.
"""
from __future__ import annotations

import csv
import json
import math
import random
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from ..models import Candle, MarketSnapshot

TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")


class MarketDataProvider(Protocol):
    def candles(self, symbol: str, timeframe: str, n: int) -> List[Candle]: ...
    def snapshot(self, symbol: str) -> MarketSnapshot: ...


# --------------------------------------------------------------------------- synthetic
class SyntheticProvider:
    """Deterministic GBM-with-regimes price generator. Seeded per symbol."""

    PROFILES = {
        "BTC": dict(price=60000, vol=0.028, drift=0.0006, mcap=1.2e12, vol24=2.5e10, narrative="store-of-value"),
        "ETH": dict(price=3000, vol=0.035, drift=0.0005, mcap=3.6e11, vol24=1.2e10, narrative="smart-contracts"),
        "SOL": dict(price=150, vol=0.05, drift=0.001, mcap=7e10, vol24=3e9, narrative="L1"),
        "LINK": dict(price=15, vol=0.045, drift=0.0004, mcap=9e9, vol24=5e8, narrative="oracles"),
        "AVAX": dict(price=30, vol=0.05, drift=0.0003, mcap=1.2e10, vol24=4e8, narrative="L1"),
        "ARB": dict(price=1.0, vol=0.055, drift=0.0, mcap=3e9, vol24=3e8, narrative="L2"),
        "OP": dict(price=2.0, vol=0.055, drift=0.0002, mcap=2.5e9, vol24=2.5e8, narrative="L2"),
        "INJ": dict(price=25, vol=0.06, drift=0.0012, mcap=2.4e9, vol24=2e8, narrative="defi"),
        "TIA": dict(price=8, vol=0.065, drift=-0.0004, mcap=1.5e9, vol24=1.5e8, narrative="modular"),
        "SUI": dict(price=1.5, vol=0.06, drift=0.0008, mcap=4e9, vol24=4e8, narrative="L1"),
        "SCAMCOIN": dict(price=0.001, vol=0.15, drift=0.01, mcap=5e6, vol24=2e5, narrative="meme"),
    }

    def __init__(self, seed: int = 42, bars_1d: int = 400, start_ts: Optional[float] = None):
        self.seed = seed
        self.bars_1d = bars_1d
        self.start_ts = start_ts or (time.time() - bars_1d * 86400)
        self._cache: Dict[str, List[Candle]] = {}

    def _profile(self, symbol: str) -> dict:
        return self.PROFILES.get(symbol, dict(price=1.0, vol=0.07, drift=0.0, mcap=5e8, vol24=5e7, narrative="generic"))

    def _base_1h(self, symbol: str) -> List[Candle]:
        if symbol in self._cache:
            return self._cache[symbol]
        p = self._profile(symbol)
        rng = random.Random(f"{self.seed}:{symbol}")
        n = self.bars_1d * 24
        hv = p["vol"] / math.sqrt(24)
        hd = p["drift"] / 24
        price = p["price"]
        out: List[Candle] = []
        ts = self.start_ts
        regime_left, regime_mult = 0, 1.0
        for i in range(n):
            if regime_left <= 0:
                regime_left = rng.randint(24 * 5, 24 * 40)
                regime_mult = rng.choice([1.0, 1.0, 1.6, 0.7, 2.2])
            regime_left -= 1
            r = rng.gauss(hd * regime_mult, hv * regime_mult)
            o = price
            c = max(o * (1 + r), 1e-9)
            wick = abs(rng.gauss(0, hv * 0.35))
            h = max(o, c) * (1 + wick)
            l = min(o, c) * (1 - wick)
            base_vol = p["vol24"] / 24 / price
            v = base_vol * (0.4 + abs(r) / hv * 0.8 + rng.random())
            out.append(Candle(ts, o, h, l, c, v))
            price = c
            ts += 3600
        self._cache[symbol] = out
        return out

    @staticmethod
    def resample(c1h: List[Candle], timeframe: str) -> List[Candle]:
        secs = TF_SECONDS[timeframe]
        if secs < 3600:
            # synthesise sub-hour bars by splitting the hourly bar
            k = 3600 // secs
            out = []
            for c in c1h:
                step = (c.close - c.open) / k
                for j in range(k):
                    o = c.open + step * j
                    cl = o + step
                    out.append(Candle(c.ts + j * secs, o, max(o, cl, c.high if j == k // 2 else max(o, cl)),
                                      min(o, cl, c.low if j == k // 2 else min(o, cl)), cl, c.volume / k))
            return out
        k = secs // 3600
        out = []
        for i in range(0, len(c1h) - len(c1h) % k, k):
            chunk = c1h[i:i + k]
            out.append(Candle(chunk[0].ts, chunk[0].open, max(x.high for x in chunk),
                              min(x.low for x in chunk), chunk[-1].close, sum(x.volume for x in chunk)))
        return out

    def candles(self, symbol: str, timeframe: str, n: int) -> List[Candle]:
        return self.resample(self._base_1h(symbol), timeframe)[-n:]

    def snapshot(self, symbol: str) -> MarketSnapshot:
        p = self._profile(symbol)
        c = {tf: self.candles(symbol, tf, 300) for tf in TIMEFRAMES}
        price = c["1h"][-1].close
        rng = random.Random(f"{self.seed}:{symbol}:meta")
        scam = symbol == "SCAMCOIN"
        return MarketSnapshot(
            symbol=symbol, candles=c, price=price,
            volume_24h_usd=sum(x.volume for x in c["1h"][-24:]) * price,
            spread_pct=0.02 if scam else 0.0005,
            market_cap_usd=p["mcap"] * price / p["price"],
            fdv_usd=p["mcap"] * price / p["price"] * (5.0 if scam else rng.uniform(1.0, 1.8)),
            circulating_ratio=0.2 if scam else rng.uniform(0.55, 1.0),
            days_to_next_unlock=3 if scam else rng.choice([None, 45, 90, 200]),
            unlock_pct_of_supply=0.15 if scam else rng.choice([0.0, 0.01, 0.02]),
            holder_top10_pct=0.8 if scam else rng.uniform(0.15, 0.4),
            exchange_netflow_usd_24h=rng.gauss(0, p["vol24"] * 0.02),
            dex_liquidity_usd=50_000 if scam else p["vol24"] * 0.1,
            social_mentions_24h=int(rng.uniform(100, 5000) * (10 if scam else 1)),
            social_mentions_7d_avg=rng.uniform(100, 3000),
            news=["Partnership rumour circulating on X"] if scam else [],
            narrative=p["narrative"],
            contract_verified=not scam,
            token_age_days=12 if scam else 1500,
        )


# --------------------------------------------------------------------------- binance public
class BinancePublicProvider:
    """Public klines/ticker endpoints (no API key). Read-only."""

    BASE = "https://api.binance.com"
    TF_MAP = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def __init__(self, quote: str = "USDT", timeout: int = 10):
        self.quote, self.timeout = quote, timeout

    def _get(self, path: str) -> object:
        req = urllib.request.Request(self.BASE + path, headers={"User-Agent": "crypto-fund/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def candles(self, symbol: str, timeframe: str, n: int) -> List[Candle]:
        data = self._get(f"/api/v3/klines?symbol={symbol}{self.quote}&interval={self.TF_MAP[timeframe]}&limit={min(n, 1000)}")
        return [Candle(k[0] / 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in data]

    def snapshot(self, symbol: str) -> MarketSnapshot:
        c = {tf: self.candles(symbol, tf, 300) for tf in TIMEFRAMES}
        t = self._get(f"/api/v3/ticker/24hr?symbol={symbol}{self.quote}")
        book = self._get(f"/api/v3/ticker/bookTicker?symbol={symbol}{self.quote}")
        bid, ask = float(book["bidPrice"]), float(book["askPrice"])
        price = float(t["lastPrice"])
        return MarketSnapshot(symbol=symbol, candles=c, price=price,
                              volume_24h_usd=float(t["quoteVolume"]),
                              spread_pct=(ask - bid) / price if price else 0.01)


# --------------------------------------------------------------------------- csv
class CSVProvider:
    """CSV columns: ts,open,high,low,close,volume (ts in seconds). One file per symbol/timeframe."""

    def __init__(self, folder: Path | str):
        self.folder = Path(folder)

    def candles(self, symbol: str, timeframe: str, n: int) -> List[Candle]:
        path = self.folder / f"{symbol}_{timeframe}.csv"
        rows: List[Candle] = []
        with path.open() as f:
            for r in csv.DictReader(f):
                rows.append(Candle(float(r["ts"]), float(r["open"]), float(r["high"]),
                                   float(r["low"]), float(r["close"]), float(r["volume"])))
        return rows[-n:] if n else rows

    def snapshot(self, symbol: str) -> MarketSnapshot:
        c = {}
        for tf in TIMEFRAMES:
            try:
                c[tf] = self.candles(symbol, tf, 300)
            except FileNotFoundError:
                pass
        base = c.get("1h") or c.get("1d") or next(iter(c.values()))
        price = base[-1].close
        return MarketSnapshot(symbol=symbol, candles=c, price=price,
                              volume_24h_usd=sum(x.volume for x in base[-24:]) * price)
