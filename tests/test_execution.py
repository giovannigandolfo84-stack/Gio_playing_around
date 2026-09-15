from crypto_fund.config import Mode, RiskLimits
from crypto_fund.execution import ExecutionEngine, HumanApprovalBroker, PaperBroker, TxProposal, WalletPolicy
from crypto_fund.models import AgentReport, Decision, Regime, ScoredOpportunity, Side, TradePlan
from crypto_fund.risk import PortfolioState, RiskEngine


def _sized(mode=Mode.PAPER):
    L = RiskLimits()
    plan = TradePlan("ETH", "momentum", Side.BUY, 100.0, 95.0, [110.0], "t", "i")
    opp = ScoredOpportunity(plan, {"technical": AgentReport("technical", "ETH", 80, 0.7)}, 85, 85, Regime.BULL,
                            Decision.BUY, False, [], {}, 0.7)
    st = PortfolioState(cash=100.0)
    risk = RiskEngine(L, mode)
    return L, risk, st, risk.size(opp, st, 1e9)


def _engine(L, risk, mode, tokens=("ETH",)):
    broker = PaperBroker(L.fee_pct, L.default_slippage_pct, price_source=lambda s: 100.0)
    policy = WalletPolicy(L, mode, set(tokens), {"paper"})
    return ExecutionEngine(L, mode, broker, policy, risk, venue="paper")


def test_paper_execution_full_pipeline():
    L, risk, st, t = _sized()
    eng = _engine(L, risk, Mode.PAPER)
    res = eng.execute(t, st, 1e9)
    assert res.executed and len(st.positions) == 1 and st.cash < 100
    assert res.position.entry > 100.0  # slippage applied
    fill = eng.close(st.positions[0], st, 110.0, "TARGET")
    assert fill.ok and not st.positions and st.cash > 100


def test_execution_refuses_unapproved_and_unwhitelisted():
    L, risk, st, t = _sized()
    t.rejections.append("test")
    assert not _engine(L, risk, Mode.PAPER).execute(t, st, 1e9).executed
    L, risk, st, t = _sized()
    res = _engine(L, risk, Mode.PAPER, tokens=("BTC",)).execute(t, st, 1e9)
    assert not res.executed and "not whitelisted" in res.reason


def test_execution_refuses_on_price_drift_and_liquidity():
    L, risk, st, t = _sized()
    eng = _engine(L, risk, Mode.PAPER)
    eng.broker.price_source = lambda s: 105.0
    assert "drifted" in eng.execute(t, st, 1e9).reason
    eng.broker.price_source = lambda s: 100.0
    assert "Liquidity" in eng.execute(t, st, 10.0).reason


def test_wallet_policy_modes():
    L = RiskLimits()
    tx = TxProposal("paper", "ETH", "BUY", 1, 30.0, 0.005, "p1")
    assert WalletPolicy(L, Mode.PAPER, {"ETH"}, {"paper"}).authorize(tx) == []
    assert "Awaiting human approval" in WalletPolicy(L, Mode.HUMAN_APPROVAL, {"ETH"}, {"paper"}).authorize(tx)
    auto = WalletPolicy(L, Mode.AUTONOMOUS, {"ETH"}, {"paper"})
    assert any("per-tx cap" in v for v in auto.authorize(tx))
    tx.notional_usd = 20.0
    assert auto.authorize(tx) == []
    auto.record(tx); auto.record(tx); auto.record(tx)
    assert any("daily cap" in v for v in auto.authorize(tx))
    bad = TxProposal("paper", "ETH", "WITHDRAW", 1, 1.0, 0.001, "p2")
    assert any("Only spot" in v for v in auto.authorize(bad))


def test_human_approval_queue(tmp_path):
    inner = PaperBroker(price_source=lambda s: 100.0)
    b = HumanApprovalBroker(inner, tmp_path / "q.json")
    tx = TxProposal("paper", "ETH", "BUY", 0.1, 10.0, 0.005, "plan-1")
    f = b.execute(tx, 100.0)
    assert not f.ok and f.error == "PENDING_HUMAN_APPROVAL" and len(b.pending()) == 1
    assert b.approve("plan-1")
    f2 = b.execute(tx, 100.0)
    assert f2.ok and tx.approved_by == "human" and not b.pending()


def test_human_approval_mode_end_to_end(tmp_path):
    L, risk, st, t = _sized(Mode.HUMAN_APPROVAL)
    broker = HumanApprovalBroker(PaperBroker(price_source=lambda s: 100.0), tmp_path / "q.json")
    policy = WalletPolicy(L, Mode.HUMAN_APPROVAL, {"ETH"}, {"paper"})
    eng = ExecutionEngine(L, Mode.HUMAN_APPROVAL, broker, policy, risk, venue="paper")
    res = eng.execute(t, st, 1e9)
    assert not res.executed and res.reason == "PENDING_HUMAN_APPROVAL" and len(broker.pending()) == 1
    # a second cycle regenerates the plan (new id) -> queue is updated, not duplicated
    L2, risk2, st2, t2 = _sized(Mode.HUMAN_APPROVAL)
    assert not eng.execute(t2, st2, 1e9).executed and len(broker.pending()) == 1
    assert broker.approve(broker.pending()[0]["plan_id"])
    L3, risk3, st3, t3 = _sized(Mode.HUMAN_APPROVAL)
    res3 = eng.execute(t3, st3, 1e9)
    assert res3.executed and len(st3.positions) == 1 and not broker.pending()
