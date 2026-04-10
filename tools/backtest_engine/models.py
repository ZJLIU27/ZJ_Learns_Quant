"""Backtest engine data models."""

from dataclasses import dataclass, field


@dataclass
class Position:
    """Open position held in portfolio."""
    code: str
    buy_date: str
    buy_price: float
    shares: int
    cost: float


@dataclass
class Trade:
    """Closed trade record."""
    code: str
    buy_date: str
    buy_price: float
    sell_date: str
    sell_price: float
    shares: int
    gross_return_pct: float
    net_return_pct: float
    cost_pct: float


@dataclass
class EquitySnapshot:
    """Equity curve point for a single trading day."""
    trade_date: str
    equity: float
    cash: float
    positions: int


@dataclass
class BacktestResult:
    """Complete backtest result."""
    initial_capital: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    trade_count: int
    avg_return_pct: float
    median_return_pct: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquitySnapshot] = field(default_factory=list)

    def __post_init__(self):
        assert self.initial_capital > 0, "initial_capital must be positive"
        assert self.trade_count >= 0, "trade_count must be non-negative"