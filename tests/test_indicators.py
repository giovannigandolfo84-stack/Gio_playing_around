from crypto_fund.indicators import atr, ema, macd, rsi, sma, zscore, correlation
from crypto_fund.models import Candle


def test_sma_ema_basic():
    v = [1, 2, 3, 4, 5, 6]
    assert sma(v, 3)[-1] == 5
    e = ema(v, 3)
    assert e[1] is None and e[2] == 2 and e[-1] > e[-2]


def test_rsi_bounds_and_direction():
    up = list(range(1, 40))
    r = rsi([float(x) for x in up])
    assert r[-1] == 100.0
    down = [float(x) for x in range(40, 1, -1)]
    assert rsi(down)[-1] == 0.0


def test_macd_and_atr_lengths():
    v = [100 + (i % 7) for i in range(80)]
    line, sig, hist = macd(v)
    assert len(line) == len(sig) == len(hist) == 80 and hist[-1] is not None
    cs = [Candle(i, 10, 11, 9, 10, 1) for i in range(30)]
    a = atr(cs)
    assert abs(a[-1] - 2.0) < 1e-9


def test_zscore_and_correlation():
    v = [1.0] * 19 + [5.0]
    assert zscore(v, 20) > 3
    a = [float(i) for i in range(1, 50)]
    assert correlation(a, a, 30) > 0.99
