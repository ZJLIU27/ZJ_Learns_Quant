"""Backtest engine package.

Public API:
  - run_backtest: Main entry point — runs full date-loop backtest
  - BacktestResult, Position, Trade, EquitySnapshot: Data models
"""

from .engine import run_backtest
from .models import BacktestResult, EquitySnapshot, Position, Trade

__all__ = ["run_backtest", "BacktestResult", "Position", "Trade", "EquitySnapshot"]