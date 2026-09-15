from crypto_fund.agents import (FundamentalAnalyst, MarketScout, OnChainAnalyst, PortfolioManager, RedTeamAgent,
                                SentimentAgent, TechnicalAnalyst)
from crypto_fund.config import RiskLimits
from crypto_fund.data.provider import SyntheticProvider
from crypto_fund.models import Decision, Regime, Side, TradePlan
from crypto_fund.risk import detect_regime


def _ctx(prov):
    btc = prov.snapshot("BTC")
    return {"btc_1d_closes": [c.close for c in btc.candles["1d"]], "risk_on": True}


def test_agents_produce_bounded_scores():
    prov = SyntheticProvider(seed=1, bars_1d=200)
    snap = prov.snapshot("ETH")
    ctx = _ctx(prov)
    for a in (TechnicalAnalyst(), OnChainAnalyst(), SentimentAgent(), FundamentalAnalyst(), MarketScout()):
        r = a.analyze(snap, ctx)
        assert 0 <= r.score <= 100 and 0 <= r.confidence <= 1


def test_red_team_vetoes_scam_token():
    prov = SyntheticProvider(seed=1, bars_1d=200)
    snap = prov.snapshot("SCAMCOIN")
    ctx = _ctx(prov)
    reports = {a.name: a.analyze(snap, ctx) for a in (TechnicalAnalyst(), OnChainAnalyst(), SentimentAgent(), FundamentalAnalyst())}
    plan = TradePlan("SCAMCOIN", "momentum", Side.BUY, snap.price, snap.price * 0.9, [snap.price * 1.3], "t", "i")
    v = RedTeamAgent(RiskLimits()).review(plan, snap, reports, ctx, 100.0)
    assert v.veto and len(v.hard_fails) >= 3
    pm = PortfolioManager(RiskLimits())
    opp = pm.evaluate(plan, reports, 80, v, Regime.BULL, True)
    assert opp.decision == Decision.AVOID


def test_red_team_passes_clean_large_cap():
    prov = SyntheticProvider(seed=1, bars_1d=200)
    snap = prov.snapshot("ETH")
    ctx = _ctx(prov)
    reports = {a.name: a.analyze(snap, ctx) for a in (TechnicalAnalyst(), OnChainAnalyst(), SentimentAgent(), FundamentalAnalyst())}
    plan = TradePlan("ETH", "momentum", Side.BUY, snap.price, snap.price * 0.95, [snap.price * 1.12], "t", "i")
    v = RedTeamAgent(RiskLimits()).review(plan, snap, reports, ctx, 100.0)
    assert not v.veto


def test_pm_weights_change_with_regime_and_sum_to_one():
    pm = PortfolioManager(RiskLimits())
    for r in Regime:
        assert abs(sum(pm.weights_for(r).values()) - 1.0) < 1e-9
    assert pm.weights_for(Regime.BEAR)["risk_quality"] > pm.weights_for(Regime.BULL)["risk_quality"]


def test_regime_detection_runs():
    prov = SyntheticProvider(seed=5, bars_1d=300)
    rs = detect_regime(prov.candles("BTC", "1d", 300), prov.candles("ETH", "1d", 300))
    assert rs.regime in Regime and -1 <= rs.trend_score <= 1
