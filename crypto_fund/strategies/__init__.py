from .base import Strategy, Signal  # noqa: F401
from .momentum import MomentumStrategy  # noqa: F401
from .breakout import BreakoutStrategy  # noqa: F401
from .pullback import PullbackStrategy  # noqa: F401
from .mean_reversion import MeanReversionStrategy  # noqa: F401
from .narrative import NarrativeRotationStrategy  # noqa: F401
from .event import EventStrategy  # noqa: F401
from .smart_money import SmartMoneyStrategy  # noqa: F401

ALL_STRATEGIES = [MomentumStrategy, BreakoutStrategy, PullbackStrategy, MeanReversionStrategy,
                  NarrativeRotationStrategy, EventStrategy, SmartMoneyStrategy]


def default_strategies():
    return [cls() for cls in ALL_STRATEGIES]
