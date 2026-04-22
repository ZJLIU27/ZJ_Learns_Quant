"""Tests for position monitoring."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.models import Position
from strategies.st_trading_system.positions import monitor_positions


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


class _FakeProvider:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self.data = data

    def get_latest(self, code, days=250, end_date=None):
        return self.data.get(code)


def test_no_alert_when_above_bbi():
    provider = _FakeProvider({"000001": _make_ohlcv([10 + i * 0.2 for i in range(24)])})
    positions = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])]
    status = monitor_positions(positions, provider, "20260124")[0]
    assert status.status == "ok"
    assert status.alerts == []


def test_alert_when_close_below_bbi():
    provider = _FakeProvider({"000001": _make_ohlcv([14.0] * 20 + [13.0, 12.0, 11.0, 10.0])})
    positions = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])]
    status = monitor_positions(positions, provider, "20260124")[0]
    assert status.status == "alert"
    assert status.alerts[0][0] == "close_below_bbi"


def test_unmonitored_when_no_exit_monitor():
    provider = _FakeProvider({"000001": _make_ohlcv([10 + i * 0.2 for i in range(25)])})
    positions = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["danzhen20"])]
    status = monitor_positions(positions, provider, "20260125")[0]
    assert status.status == "unmonitored"
    assert status.alerts == []


def test_or_across_multiple_strategies():
    provider = _FakeProvider({"000001": _make_ohlcv([14.0] * 20 + [13.0, 12.0, 11.0, 10.0])})
    positions = [
        Position(
            code="000001",
            entry_date="20260101",
            cost_basis=10.0,
            strategy_ids=["b1", "danzhen20"],
        )
    ]
    status = monitor_positions(positions, provider, "20260124")[0]
    assert status.status == "alert"


def test_pnl_pct_correct():
    provider = _FakeProvider({"000001": _make_ohlcv([12.0] * 24)})
    positions = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])]
    status = monitor_positions(positions, provider, "20260124")[0]
    assert round(status.pnl_pct, 4) == 0.2


def test_pnl_abs_only_when_quantity():
    provider = _FakeProvider({"000001": _make_ohlcv([12.0] * 24)})

    no_qty = Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    with_qty = Position(
        code="000001",
        entry_date="20260101",
        cost_basis=10.0,
        strategy_ids=["b1"],
        quantity=100.0,
    )
    statuses = monitor_positions([no_qty, with_qty], provider, "20260124")
    assert statuses[0].pnl_abs is None
    assert statuses[1].pnl_abs == 200.0


if __name__ == "__main__":
    test_no_alert_when_above_bbi()
    test_alert_when_close_below_bbi()
    test_unmonitored_when_no_exit_monitor()
    test_or_across_multiple_strategies()
    test_pnl_pct_correct()
    test_pnl_abs_only_when_quantity()
    print("All tests passed")
