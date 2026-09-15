from crypto_fund.config import Mode, RiskLimits, Settings
from crypto_fund.data.provider import SyntheticProvider
from crypto_fund.memory import Journal
from crypto_fund.orchestrator import Orchestrator


def test_paper_cycle_end_to_end():
    s = Settings(mode=Mode.PAPER, limits=RiskLimits(), db_path=":memory:")
    orch = Orchestrator(s, SyntheticProvider(seed=11, bars_1d=250), Journal(":memory:"))
    res = orch.run_cycle()
    assert res.regime and "DAILY AI REPORT" in res.report
    assert res.state.equity <= 100.0 + 1e-6  # nothing can be created from thin air on cycle 1
    assert res.state.cash >= 0
    for o in res.opportunities:
        assert o.plan.thesis and o.plan.invalidation and o.plan.targets and o.plan.stop < o.plan.entry
    assert orch.journal.snapshots()  # state persisted


def test_kill_switch_blocks_execution(monkeypatch):
    monkeypatch.setenv("FUND_KILL", "1")
    s = Settings(mode=Mode.PAPER, limits=RiskLimits(), db_path=":memory:")
    orch = Orchestrator(s, SyntheticProvider(seed=11, bars_1d=250), Journal(":memory:"))
    res = orch.run_cycle()
    assert not res.executed and "HALTED" in res.report
