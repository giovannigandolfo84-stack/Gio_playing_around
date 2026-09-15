"""Configuration: operating modes and immutable hard risk limits.

RiskLimits is a frozen dataclass loaded from config/risk_limits.json. There is
deliberately no API for agents to mutate it. The file hash is recorded so any
edit is visible in the journal.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIMITS_PATH = ROOT / "config" / "risk_limits.json"
KILL_SWITCH_PATH = ROOT / "KILL_SWITCH"


class Mode(str, Enum):
    PAPER = "PAPER"                    # simulate only
    HUMAN_APPROVAL = "HUMAN_APPROVAL"  # AI prepares, human signs/approves
    AUTONOMOUS = "AUTONOMOUS"          # AI executes within hard limits


@dataclass(frozen=True)
class RiskLimits:
    starting_capital_usd: float = 100.0
    risk_per_trade_pct: Dict[str, float] = field(
        default_factory=lambda: {"conservative": 0.01, "aggressive": 0.02, "speculative": 0.03}
    )
    max_loss_per_trade_pct: float = 0.03
    max_daily_loss_pct: float = 0.05
    max_weekly_loss_pct: float = 0.10
    max_drawdown_circuit_breaker_pct: float = 0.20
    max_exposure_per_token_pct: float = 0.25
    max_exposure_per_narrative_pct: float = 0.40
    max_total_exposure_pct: float = 0.80
    max_open_positions: int = 4
    max_leverage: float = 1.0
    max_slippage_pct: float = 0.01
    max_position_vs_24h_volume_pct: float = 0.0005
    min_reward_risk: float = 2.0
    min_trade_quality_score: int = 70
    min_notional_usd: float = 5.0
    autonomous_max_per_tx_usd: float = 25.0
    autonomous_max_daily_usd: float = 60.0
    fee_pct: float = 0.001
    default_slippage_pct: float = 0.003
    source_hash: str = ""

    @classmethod
    def load(cls, path: Path | str = DEFAULT_LIMITS_PATH) -> "RiskLimits":
        p = Path(path)
        raw = p.read_bytes()
        data = json.loads(raw)
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        data["source_hash"] = hashlib.sha256(raw).hexdigest()[:16]
        return cls(**data)


@dataclass(frozen=True)
class Settings:
    mode: Mode = Mode.PAPER
    limits: RiskLimits = field(default_factory=RiskLimits)
    db_path: str = str(ROOT / "data" / "fund.db")
    universe: tuple = ("BTC", "ETH", "SOL", "LINK", "AVAX", "ARB", "OP", "INJ", "TIA", "SUI")
    quote: str = "USDT"
    use_llm: bool = False
    llm_model: str = "claude-opus-5"
    approved_venues: tuple = ("paper", "binance", "kraken", "coinbase")
    token_whitelist: tuple = ()  # empty -> universe is the whitelist

    @classmethod
    def from_env(cls) -> "Settings":
        mode = Mode(os.environ.get("FUND_MODE", "PAPER").upper())
        limits_path = os.environ.get("FUND_LIMITS", str(DEFAULT_LIMITS_PATH))
        limits = RiskLimits.load(limits_path) if Path(limits_path).exists() else RiskLimits()
        return cls(
            mode=mode,
            limits=limits,
            db_path=os.environ.get("FUND_DB", str(ROOT / "data" / "fund.db")),
            use_llm=os.environ.get("FUND_USE_LLM", "0") == "1"
            and bool(os.environ.get("ANTHROPIC_API_KEY")),
            llm_model=os.environ.get("FUND_LLM_MODEL", "claude-opus-5"),
        )

    def whitelist(self) -> set[str]:
        return set(self.token_whitelist) if self.token_whitelist else set(self.universe)


def kill_switch_active() -> bool:
    """A file named KILL_SWITCH at repo root (or env FUND_KILL=1) halts all execution."""
    return KILL_SWITCH_PATH.exists() or os.environ.get("FUND_KILL") == "1"
