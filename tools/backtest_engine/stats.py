"""Performance statistics calculations."""

import numpy as np


def calc_total_return(initial_capital: float, final_equity: float) -> float:
    """Calculate total return as percentage."""
    if initial_capital <= 0:
        return 0.0
    return round((final_equity / initial_capital - 1.0) * 100.0, 2)


def calc_max_drawdown(equity_curve: list) -> float:
    """Calculate maximum drawdown percentage from equity curve.

    Args:
        equity_curve: List of EquitySnapshot objects with 'equity' field.

    Returns:
        Maximum drawdown as a percentage (e.g. 30.0 for 30% drawdown).
    """
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    max_dd = 0.0
    for snap in equity_curve:
        if snap.equity > peak:
            peak = snap.equity
        dd = (peak - snap.equity) / peak * 100.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def calc_win_rate(trades: list) -> float:
    """Calculate win rate as percentage of profitable trades."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.net_return_pct > 0)
    return round(wins / len(trades) * 100.0, 2)


def calc_avg_return(trades: list) -> float:
    """Calculate average net return percentage across trades."""
    if not trades:
        return 0.0
    returns = [t.net_return_pct for t in trades]
    return round(float(np.mean(returns)), 2)


def calc_median_return(trades: list) -> float:
    """Calculate median net return percentage across trades."""
    if not trades:
        return 0.0
    returns = [t.net_return_pct for t in trades]
    return round(float(np.median(returns)), 2)