"""Dataclasses for the trading system: Position, PositionStatus, ScreeningResult."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Position:
    """A user-held position, persisted in portfolio.json."""

    code: str
    entry_date: str  # YYYYMMDD
    cost_basis: float
    strategy_ids: list[str]
    quantity: float | None = None
    notes: str = ""


@dataclass
class PositionStatus:
    """Computed status for a position — not persisted."""

    code: str
    current_price: float
    pnl_pct: float
    pnl_abs: float | None = None
    alerts: list[tuple[str, str]] = field(default_factory=list)
    status: Literal["ok", "alert", "unmonitored"] = "ok"


@dataclass
class ScreeningResult:
    """One row in the screener output table."""

    code: str
    close: float
    hit_ids: list[str]
    hit_count: int
    indicators_snapshot: dict


@dataclass(frozen=True)
class IndicatorPreset:
    """Metadata for one chartable indicator preset."""

    id: str
    name: str
    panel: Literal["overlay", "subchart"]
    description: str
    default_strategy_ids: list[str] = field(default_factory=list)
