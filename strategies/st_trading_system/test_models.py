"""Tests for models module — dataclass shapes and defaults."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.models import (
    Position,
    PositionStatus,
    ScreeningResult,
)


def test_position_required_fields():
    p = Position(
        code="000001",
        entry_date="20260101",
        cost_basis=10.0,
        strategy_ids=["b1"],
    )
    assert p.code == "000001"
    assert p.entry_date == "20260101"
    assert p.cost_basis == 10.0
    assert p.strategy_ids == ["b1"]
    assert p.quantity is None
    assert p.notes == ""


def test_position_optional_fields():
    p = Position(
        code="000001",
        entry_date="20260101",
        cost_basis=10.0,
        strategy_ids=["b1"],
        quantity=100.0,
        notes="test",
    )
    assert p.quantity == 100.0
    assert p.notes == "test"


def test_position_status_defaults():
    s = PositionStatus(
        code="000001",
        current_price=12.0,
        pnl_pct=0.2,
    )
    assert s.pnl_abs is None
    assert s.alerts == []
    assert s.status == "ok"


def test_position_status_alert():
    s = PositionStatus(
        code="000001",
        current_price=9.0,
        pnl_pct=-0.1,
        alerts=[("close_below_bbi", "close=9.0 < bbi=10.0")],
        status="alert",
    )
    assert s.status == "alert"
    assert len(s.alerts) == 1


def test_screening_result_basic():
    r = ScreeningResult(
        code="000001",
        close=10.5,
        hit_ids=["b1", "danzhen20"],
        hit_count=2,
        indicators_snapshot={"bbi": 10.0, "short_stoch": 15.0},
    )
    assert r.code == "000001"
    assert r.hit_count == 2
    assert r.indicators_snapshot["bbi"] == 10.0


if __name__ == "__main__":
    test_position_required_fields()
    test_position_optional_fields()
    test_position_status_defaults()
    test_position_status_alert()
    test_screening_result_basic()
    print("All tests passed")
