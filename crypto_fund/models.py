"""Core data models shared by agents, risk engine, execution and journal."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional
import time
import uuid


def now() -> float:
    return time.time()


class Regime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOL = "HIGH_VOL"
    EXTREME_VOL = "EXTREME_VOL"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Decision(str, Enum):
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"


@dataclass
class Candle:
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketSnapshot:
    """Everything the agents are allowed to know about an asset right now."""
    symbol: str
    candles: Dict[str, List[Candle]]           # timeframe -> candles (oldest first)
    price: float
    volume_24h_usd: float
    spread_pct: float = 0.001
    market_cap_usd: Optional[float] = None
    fdv_usd: Optional[float] = None
    circulating_ratio: Optional[float] = None   # circ / total supply
    days_to_next_unlock: Optional[int] = None
    unlock_pct_of_supply: Optional[float] = None
    holder_top10_pct: Optional[float] = None
    exchange_netflow_usd_24h: Optional[float] = None  # +inflow (bearish), -outflow
    dex_liquidity_usd: Optional[float] = None
    social_mentions_24h: Optional[int] = None
    social_mentions_7d_avg: Optional[float] = None
    news: List[str] = field(default_factory=list)
    narrative: str = "generic"
    contract_verified: bool = True
    token_age_days: int = 3650
    btc_corr_30d: Optional[float] = None


@dataclass
class AgentReport:
    agent: str
    symbol: str
    score: float                       # 0-100
    confidence: float                  # 0-1
    rationale: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    data: Dict[str, float] = field(default_factory=dict)


@dataclass
class TradePlan:
    """A fully specified candidate trade. Every field must be answered before execution."""
    symbol: str
    strategy: str
    side: Side
    entry: float
    stop: float
    targets: List[float]
    thesis: str
    invalidation: str
    narrative: str = "generic"
    timeframe: str = "4h"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=now)

    @property
    def stop_distance_pct(self) -> float:
        return abs(self.entry - self.stop) / self.entry

    @property
    def reward_risk(self) -> float:
        if not self.targets:
            return 0.0
        risk = abs(self.entry - self.stop)
        reward = abs(self.targets[0] - self.entry)
        return reward / risk if risk > 0 else 0.0


@dataclass
class ScoredOpportunity:
    plan: TradePlan
    reports: Dict[str, AgentReport]
    composite_score: float
    trade_quality: float
    regime: Regime
    decision: Decision
    red_team_veto: bool
    red_team_reasons: List[str]
    weights: Dict[str, float]
    confidence: float


@dataclass
class SizedTrade:
    opportunity: ScoredOpportunity
    quantity: float
    notional_usd: float
    risk_usd: float
    max_loss_usd: float
    expected_fees_usd: float
    expected_slippage_usd: float
    risk_tier: str
    checks: List[str]          # passed checks
    rejections: List[str]      # failed checks (non-empty -> not tradable)

    @property
    def approved(self) -> bool:
        return not self.rejections and self.quantity > 0


@dataclass
class Position:
    symbol: str
    strategy: str
    side: Side
    entry: float
    quantity: float
    stop: float
    targets: List[float]
    opened_at: float
    plan_id: str
    narrative: str = "generic"
    mfe: float = 0.0   # max favourable excursion (R multiples)
    mae: float = 0.0   # max adverse excursion (R multiples)
    trailing_stop: Optional[float] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.stop)

    def unrealized(self, price: float) -> float:
        sign = 1 if self.side == Side.BUY else -1
        return sign * (price - self.entry) * self.quantity

    def r_multiple(self, price: float) -> float:
        if self.risk_per_unit == 0:
            return 0.0
        sign = 1 if self.side == Side.BUY else -1
        return sign * (price - self.entry) / self.risk_per_unit


@dataclass
class TradeRecord:
    """Closed-trade journal entry (mirrors DB schema)."""
    timestamp: float
    asset: str
    strategy: str
    side: str
    entry: float
    exit: float
    position_size: float
    stop: float
    target: float
    result: str            # WIN / LOSS / BREAKEVEN
    pnl_usd: float
    r_multiple: float
    mfe: float
    mae: float
    market_regime: str
    agent_scores: Dict[str, float]
    thesis: str
    exit_reason: str
    mistake_classification: str = ""
    fees_usd: float = 0.0
    plan_id: str = ""
    holding_hours: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
