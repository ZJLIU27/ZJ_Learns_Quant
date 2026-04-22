"""Tests for built-in monitors."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.models import Position
from strategies.st_trading_system.monitors import get_monitor, list_monitors


def _make_ohlcv(closes: list[float]) -> pd.DataFrame:
    opens = [close * 0.99 for close in closes]
    highs = [close + 0.5 for close in closes]
    lows = [close - 0.5 for close in closes]
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "trade_date": dates.strftime("%Y%m%d"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "vol": [1000.0] * len(closes),
        }
    )


def test_discovery_finds_close_below_bbi_monitor():
    ids = [monitor.id for monitor in list_monitors()]
    assert ids == ["close_below_bbi"]


def test_close_below_bbi_alert_and_ok():
    monitor = get_monitor("close_below_bbi")
    position = Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])

    rising_df = _make_ohlcv([10 + i * 0.2 for i in range(24)])
    alert, reason = monitor.check(rising_df, position)
    assert alert is False
    assert ">=" in reason

    falling_df = _make_ohlcv([14.0] * 20 + [13.0, 12.0, 11.0, 10.0])
    alert, reason = monitor.check(falling_df, position)
    assert alert is True
    assert "close=" in reason and "bbi=" in reason


if __name__ == "__main__":
    test_discovery_finds_close_below_bbi_monitor()
    test_close_below_bbi_alert_and_ok()
    print("All tests passed")
