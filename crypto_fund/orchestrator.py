"""ORCHESTRATOR: one research->decision->execution cycle.

scout -> (technical, onchain, sentiment, fundamental) -> strategies -> red team ->
portfolio manager -> risk engine -> execution -> journal. Then manage open positions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .agents import (FundamentalAnalyst, MarketScout, OnChainAnalyst, PortfolioManager, RedTeamAgent,
                     SentimentAgent, TechnicalAnalyst)
from .agents.llm import LLMClient
from .config import Mode, Settings, kill_switch_active
from .data.provider import MarketDataProvider
from .execution import ExecutionEngine, HumanApprovalBroker, PaperBroker, WalletPolicy
from .indicators import relative_strength
from .memory import Journal
from .memory.review import classify_mistake
from .models import Decision, MarketSnapshot, ScoredOpportunity, SizedTrade, TradeRecord
from .reports.daily import daily_report
from .risk import PortfolioState, RiskEngine, detect_regime
from .strategies import default_strategies


@dataclass
class CycleResult:
    regime: str
    opportunities: List[ScoredOpportunity]
    sized: Dict[str, SizedTrade]
    executed: List[str]
    closed: List[str]
    red_flags: List[str]
    report: str
    state: PortfolioState
    llm_calls: int = 0


class Orchestrator:
    def __init__(self, settings: Settings, provider: MarketDataProvider, journal: Optional[Journal] = None,
                 broker=None, top_n: int = 5):
        self.s, self.provider = settings, provider
        self.journal = journal or Journal(settings.db_path)
        self.llm = LLMClient(settings.llm_model) if settings.use_llm else None
        if self.llm and not self.llm.available:
            self.llm = None
        L = settings.limits
        self.scout = MarketScout(self.llm)
        self.analysts = [TechnicalAnalyst(self.llm), OnChainAnalyst(self.llm), SentimentAgent(self.llm), FundamentalAnalyst(self.llm)]
        self.red_team = RedTeamAgent(L, self.llm)
        self.pm = PortfolioManager(L)
        self.risk = RiskEngine(L, settings.mode)
        self.strategies = default_strategies()
        self.top_n = top_n
        self._prices: Dict[str, float] = {}
        inner = broker or PaperBroker(L.fee_pct, L.default_slippage_pct, price_source=lambda s: self._prices.get(s, 0.0))
        if settings.mode == Mode.HUMAN_APPROVAL:
            inner = HumanApprovalBroker(inner, str(settings.db_path) + ".approvals.json")
        self.broker = inner
        self.policy = WalletPolicy(L, settings.mode, settings.whitelist(), set(settings.approved_venues))
        self.exec = ExecutionEngine(L, settings.mode, self.broker, self.policy, self.risk, venue="paper" if settings.mode == Mode.PAPER else settings.approved_venues[1])
        self.state = self._load_state()

    # ------------------------------------------------------------------ state
    def _load_state(self) -> PortfolioState:
        L = self.s.limits
        st = PortfolioState(cash=self.journal.get("cash", L.starting_capital_usd), starting_capital=L.starting_capital_usd,
                            peak_equity=self.journal.get("peak_equity", L.starting_capital_usd))
        st.positions = self.journal.load_positions()
        st.circuit_breaker_tripped = self.journal.get("circuit_breaker", False)
        day = time.strftime("%Y-%m-%d")
        if self.journal.get("day") == day:
            st.realized_pnl_today = self.journal.get("pnl_today", 0.0)
            st.autonomous_spent_today = self.journal.get("auto_spent_today", 0.0)
        week = time.strftime("%Y-%W")
        if self.journal.get("week") == week:
            st.realized_pnl_week = self.journal.get("pnl_week", 0.0)
        self.journal.set("starting_capital", L.starting_capital_usd)
        return st

    def _save_state(self, regime: str) -> None:
        st = self.state
        st.update_peak()
        j = self.journal
        j.set("cash", st.cash); j.set("peak_equity", st.peak_equity); j.set("circuit_breaker", st.circuit_breaker_tripped)
        j.set("day", time.strftime("%Y-%m-%d")); j.set("pnl_today", st.realized_pnl_today); j.set("auto_spent_today", st.autonomous_spent_today)
        j.set("week", time.strftime("%Y-%W")); j.set("pnl_week", st.realized_pnl_week)
        j.save_positions(st.positions)
        j.snapshot(st.equity, st.cash, st.drawdown, len(st.positions), regime, self.s.mode.value, self.s.limits.source_hash)

    # ------------------------------------------------------------------ cycle
    def run_cycle(self) -> CycleResult:
        snaps: Dict[str, MarketSnapshot] = {}
        for sym in self.s.universe:
            try:
                snaps[sym] = self.provider.snapshot(sym)
            except Exception as e:  # data failure is not a trade signal
                self.journal.event("WARN", "data", f"{sym}: {e}")
        if not snaps:
            raise RuntimeError("No market data")
        for sym, sn in snaps.items():
            self._prices[sym] = sn.price
            self.state.prices[sym] = sn.price
        btc = snaps.get("BTC") or next(iter(snaps.values()))
        eth = snaps.get("ETH")
        rs = detect_regime(btc.candles["1d"], eth.candles["1d"] if eth else None)
        btc_closes = [c.close for c in btc.candles["1d"]]
        sector_rs: Dict[str, List[float]] = {}
        for sn in snaps.values():
            r = relative_strength([c.close for c in sn.candles["1d"]], btc_closes, 20)
            if r is not None:
                sector_rs.setdefault(sn.narrative, []).append(r)
        ctx = {"btc_1d_closes": btc_closes, "regime": rs.regime, "risk_on": rs.risk_on,
               "sector_rs": {k: sum(v) / len(v) for k, v in sector_rs.items()}}

        # --- manage exits first
        closed = self._manage_positions(snaps, rs.regime)

        # --- research
        opp_report = self.scout.screen(snaps, ctx)
        opportunities: List[ScoredOpportunity] = []
        red_flags: List[str] = []
        alloc = self.journal.get("strategy_allocation", {}) or {}
        for scout_rep in opp_report.top(self.top_n):
            sn = snaps[scout_rep.symbol]
            reports = {a.name: a.analyze(sn, ctx) for a in self.analysts}
            reports["scout"] = scout_rep
            for strat in self.strategies:
                plan = strat.propose(sn, {**ctx, "snapshot": sn})
                if not plan:
                    continue
                verdict = self.red_team.review(plan, sn, reports, ctx, self.state.equity)
                sig = strat.signal(sn.candles[strat.timeframe], {**ctx, "snapshot": sn})
                momentum = (sig.strength if sig else 50.0) * alloc.get(strat.name, 1.0)
                opp = self.pm.evaluate(plan, reports, min(100.0, momentum), verdict, rs.regime, rs.risk_on)
                opportunities.append(opp)
                red_flags.extend(f"{plan.symbol}: {r}" for r in verdict.hard_fails)
        opportunities.sort(key=lambda o: o.trade_quality, reverse=True)

        # --- size + execute
        sized: Dict[str, SizedTrade] = {}
        executed: List[str] = []
        taken_symbols = set()
        for opp in opportunities:
            sn = snaps[opp.plan.symbol]
            st = self.risk.size(opp, self.state, sn.volume_24h_usd, sn.spread_pct)
            sized[opp.plan.id] = st
            did = False
            if opp.decision == Decision.BUY and st.approved and opp.plan.symbol not in taken_symbols \
                    and not any(p.symbol == opp.plan.symbol for p in self.state.positions):
                res = self.exec.execute(st, self.state, sn.volume_24h_usd)
                if res.executed:
                    did = True
                    taken_symbols.add(opp.plan.symbol)
                    executed.append(f"{opp.plan.symbol} {opp.plan.strategy} ${st.notional_usd:.2f}")
                    self.journal.event("INFO", "execution", f"Opened {opp.plan.symbol} via {opp.plan.strategy} ${st.notional_usd:.2f}: {opp.plan.thesis}")
                else:
                    self.journal.event("INFO", "execution", f"Not executed {opp.plan.symbol}: {res.reason}")
            self.journal.record_decision(opp.plan.symbol, opp.plan.strategy, opp.decision.value, opp.trade_quality,
                                         opp.composite_score, opp.regime.value, opp.red_team_veto, opp.red_team_reasons,
                                         {"entry": opp.plan.entry, "stop": opp.plan.stop, "targets": opp.plan.targets,
                                          "thesis": opp.plan.thesis, "invalidation": opp.plan.invalidation, "rr": opp.plan.reward_risk},
                                         {"notional_usd": st.notional_usd, "risk_usd": st.risk_usd, "max_loss_usd": st.max_loss_usd,
                                          "tier": st.risk_tier, "rejections": st.rejections}, did)

        action = "BUY" if executed else ("SELL" if closed else ("WAIT" if any(o.decision == Decision.WAIT for o in opportunities) else "HOLD"))
        if kill_switch_active():
            action = "HALTED (kill switch)"
        report = daily_report(self.state, rs.regime.value, btc.price, eth.price if eth else 0.0, opportunities,
                              {pid: {"notional_usd": s.notional_usd, "tier": s.risk_tier} for pid, s in sized.items()},
                              red_flags, action, self.s.limits.starting_capital_usd)
        self._save_state(rs.regime.value)
        return CycleResult(rs.regime.value, opportunities, sized, executed, closed, red_flags, report, self.state,
                           self.llm.calls if self.llm else 0)

    # ------------------------------------------------------------------ positions
    def _manage_positions(self, snaps: Dict[str, MarketSnapshot], regime) -> List[str]:
        closed = []
        for pos in list(self.state.positions):
            sn = snaps.get(pos.symbol)
            if not sn:
                continue
            last = sn.candles["1h"][-1]
            reason = self.risk.manage_exits(pos, sn.price, last.high, last.low, regime)
            if not reason:
                continue
            exit_px = (pos.trailing_stop or pos.stop) if "STOP" in reason else (pos.targets[-1] if reason == "TARGET" else sn.price)
            fill = self.exec.close(pos, self.state, exit_px, reason)
            if not fill.ok:
                self.journal.event("ERROR", "execution", f"Failed to close {pos.symbol}: {fill.error}")
                continue
            pnl = (fill.price - pos.entry) * pos.quantity - fill.fee_usd
            r = pnl / (pos.risk_per_unit * pos.quantity) if pos.risk_per_unit else 0.0
            self.state.realized_pnl_today += pnl
            self.state.realized_pnl_week += pnl
            dec = next((d for d in self.journal.decisions(200) if d["asset"] == pos.symbol and d["executed"]), None)
            quality = dec["trade_quality"] if dec else 0.0
            self.journal.record_trade(TradeRecord(
                timestamp=time.time(), asset=pos.symbol, strategy=pos.strategy, side=pos.side.value, entry=pos.entry,
                exit=fill.price, position_size=pos.quantity, stop=pos.stop, target=pos.targets[-1], result="WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN",
                pnl_usd=pnl, r_multiple=r, mfe=pos.mfe, mae=pos.mae, market_regime=regime.value, agent_scores={},
                thesis="", exit_reason=reason, mistake_classification=classify_mistake(reason, r, pos.mfe, pos.mae, quality),
                fees_usd=fill.fee_usd, plan_id=pos.plan_id, holding_hours=(time.time() - pos.opened_at) / 3600))
            closed.append(f"{pos.symbol} {reason} {pnl:+.2f}")
            self.journal.event("INFO", "execution", f"Closed {pos.symbol} ({reason}) P&L {pnl:+.2f} ({r:+.2f}R)")
        return closed
