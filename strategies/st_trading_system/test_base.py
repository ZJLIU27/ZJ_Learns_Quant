"""Tests for base abstract classes."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.base import BaseMonitor, BaseSubStrategy
from strategies.st_trading_system.models import Position


def test_substrategy_subclass_inherits_defaults():
    class MyStrat(BaseSubStrategy):
        id = "mine"
        name = "Mine"
        description = "desc"
        tags = ["test"]
        min_rows = 5

        def evaluate(self, df):
            return True, {"close": 1.0}

    strategy = MyStrat()
    assert strategy.id == "mine"
    assert strategy.exit_monitor_id is None


def test_substrategy_evaluate_contract():
    class MyStrat(BaseSubStrategy):
        id = "mine"
        name = "Mine"
        description = "desc"
        tags = []
        min_rows = 1

        def evaluate(self, df):
            return True, {"close": float(df["close"].iloc[-1])}

    df = pd.DataFrame({"close": [10.0]})
    triggered, snapshot = MyStrat().evaluate(df)
    assert triggered is True
    assert snapshot == {"close": 10.0}


def test_monitor_subclass():
    class MyMonitor(BaseMonitor):
        id = "my_monitor"
        description = "test"

        def check(self, df, position):
            return True, "triggered"

    monitor = MyMonitor()
    df = pd.DataFrame({"close": [10.0]})
    position = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=[])
    alert, reason = monitor.check(df, position)
    assert alert is True
    assert reason == "triggered"


if __name__ == "__main__":
    test_substrategy_subclass_inherits_defaults()
    test_substrategy_evaluate_contract()
    test_monitor_subclass()
    print("All tests passed")
