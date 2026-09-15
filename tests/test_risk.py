import os

import pytest

from crypto_fund.config import Mode, RiskLimits
from crypto_fund.models import AgentReport, Decision, Position, Regime, ScoredOpportunity, Side, TradePlan
from crypto_fund.risk import PortfolioState, RiskEngine


def _opp(quality=85, regime=Regime.SIDEWAYS, veto=False, entry=100.0, stop=95.0, target=110.0):
    plan = TradePlan("ETH", "momentum", Side.BUY, entry, stop, [target], "t", "i")
    return ScoredOpportunity(plan, {"technical": AgentReport("technical", "ETH", 70, 0.6)}, quality, quality, regime,
                             Decision.BUY, veto, [], {}, 0.6)


def test_position_size_formula():
    L = RiskLimits()
    eng = RiskEngine(L, Mode.PAPER)
    st = PortfolioState(cash=100.0)
    t = eng.size(_opp(quality=85, stop=90.0, target=125.0), st, volume_24h_usd=1e9)
    assert t.approved
    # tier aggressive (quality>=80) -> 2% risk = $2 ; loss fraction = 10% stop + costs
    cost = 2 * L.fee_pct + L.default_slippage_pct + 0.0005 / 2
    expected = 2.0 / (0.10 + cost)
    assert abs(t.notional_usd - expected) < 1e-6
    assert t.max_loss_usd <= L.max_loss_per_trade_pct * 100 + 1e-9


def test_caps_and_rejections():
    L = RiskLimits()
    eng = RiskEngine(L, Mode.PAPER)
    st = PortfolioState(cash=100.0)
    # veto -> reject
    assert not eng.size(_opp(veto=True), st, 1e9).approved
    # low quality -> reject
    assert not eng.size(_opp(quality=60), st, 1e9).approved
    # poor R:R -> reject
    assert not eng.size(_opp(target=104), st, 1e9).approved
    # liquidity cap: tiny volume -> notional capped below minimum -> reject
    assert not eng.size(_opp(), st, volume_24h_usd=1000).approved
    # token exposure cap: existing ETH position at cap
    st = PortfolioState(cash=75.0)
    st.positions.append(Position("ETH", "m", Side.BUY, 100, 0.25, 95, [110], 0, "p"))
    st.prices["ETH"] = 100
    t = eng.size(_opp(), st, 1e9)
    assert "token exposure cap exhausted" in t.rejections


def test_circuit_breaker_and_kill_switch(monkeypatch):
    L = RiskLimits()
    eng = RiskEngine(L, Mode.PAPER)
    st = PortfolioState(cash=75.0, peak_equity=100.0)
    gates = eng.portfolio_gates(st)
    assert any("circuit breaker" in g.lower() for g in gates) and st.circuit_breaker_tripped
    monkeypatch.setenv("FUND_KILL", "1")
    st2 = PortfolioState(cash=100.0)
    assert any("KILL" in g for g in eng.portfolio_gates(st2))


def test_autonomous_caps():
    L = RiskLimits()
    eng = RiskEngine(L, Mode.AUTONOMOUS)
    st = PortfolioState(cash=1000.0, starting_capital=1000.0, peak_equity=1000.0)
    t = eng.size(_opp(quality=90, regime=Regime.BULL), st, 1e10)
    assert t.approved and t.notional_usd <= L.autonomous_max_per_tx_usd


def test_milestone_scaling_reduces_risk_after_growth_and_drawdown():
    eng = RiskEngine(RiskLimits(), Mode.PAPER)
    assert eng.milestone_scale(500, 100) < eng.milestone_scale(100, 100)
    assert eng.milestone_scale(70, 100) < eng.milestone_scale(100, 100)


def test_manage_exits():
    eng = RiskEngine(RiskLimits(), Mode.PAPER)
    p = Position("ETH", "m", Side.BUY, 100, 1, 95, [110, 120], 0, "p")
    assert eng.manage_exits(p, 101, 106, 100, Regime.BULL) is None
    assert p.trailing_stop == 100  # moved to breakeven after +1R
    assert eng.manage_exits(p, 99, 100, 99, Regime.BULL) == "TRAILING_STOP"
    q = Position("ETH", "m", Side.BUY, 100, 1, 95, [110], 0, "p")
    assert eng.manage_exits(q, 111, 112, 105, Regime.BULL) == "TARGET"
