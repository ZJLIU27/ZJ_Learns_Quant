"""Tests for the pure screener engine."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

import strategies.st_trading_system.screener as screener_module


class _FakeStrategy:
    def __init__(self, strategy_id: str, hit_codes: set[str], counter: dict[str, int]):
        self.id = strategy_id
        self.min_rows = 1
        self._hit_codes = hit_codes
        self._counter = counter

    def evaluate(self, df):
        code = df.attrs["code"]
        self._counter[self.id] = self._counter.get(self.id, 0) + 1
        triggered = code in self._hit_codes
        return triggered, {"close": float(df["close"].iloc[-1]), self.id: triggered}


class _FakeProvider:
    def __init__(self):
        self.calls = 0

    def cache_token(self):
        return ("fake", 1)

    def get_history(self, code, end_date, days):
        if code == "bad":
            return None
        self.calls += 1
        df = pd.DataFrame(
            {
                "trade_date": [end_date],
                "open": [10.0],
                "high": [10.0],
                "low": [10.0],
                "close": [10.0],
                "vol": [1000.0],
            }
        )
        df.attrs["code"] = code
        return df


def test_and_semantics():
    counters = {}
    strategies = {
        "alpha": _FakeStrategy("alpha", {"000001", "000002"}, counters),
        "beta": _FakeStrategy("beta", {"000001"}, counters),
    }
    provider = _FakeProvider()
    cache = {}

    old_get = screener_module.get_substrategy
    screener_module.get_substrategy = strategies.get
    try:
        results = screener_module.screen(
            substrategy_ids=["alpha", "beta"],
            mode="AND",
            universe=["000001", "000002"],
            date="20260101",
            data_provider=provider,
            cache=cache,
        )
    finally:
        screener_module.get_substrategy = old_get

    assert [row.code for row in results] == ["000001"]


def test_or_semantics_and_hit_ids():
    counters = {}
    strategies = {
        "alpha": _FakeStrategy("alpha", {"000001", "000002"}, counters),
        "beta": _FakeStrategy("beta", {"000001"}, counters),
    }
    provider = _FakeProvider()

    old_get = screener_module.get_substrategy
    screener_module.get_substrategy = strategies.get
    try:
        results = screener_module.screen(
            substrategy_ids=["alpha", "beta"],
            mode="OR",
            universe=["000001", "000002"],
            date="20260101",
            data_provider=provider,
            cache={},
        )
    finally:
        screener_module.get_substrategy = old_get

    assert [row.code for row in results] == ["000001", "000002"]
    assert results[0].hit_ids == ["alpha", "beta"]
    assert results[1].hit_ids == ["alpha"]


def test_empty_selection_returns_empty():
    results = screener_module.screen(
        substrategy_ids=[],
        mode="OR",
        universe=["000001"],
        date="20260101",
        data_provider=_FakeProvider(),
        cache={},
    )
    assert results == []


def test_bad_data_skipped():
    counters = {}
    strategies = {"alpha": _FakeStrategy("alpha", {"000001"}, counters)}
    provider = _FakeProvider()

    old_get = screener_module.get_substrategy
    screener_module.get_substrategy = strategies.get
    try:
        results = screener_module.screen(
            substrategy_ids=["alpha"],
            mode="OR",
            universe=["000001", "bad"],
            date="20260101",
            data_provider=provider,
            cache={},
        )
    finally:
        screener_module.get_substrategy = old_get

    assert [row.code for row in results] == ["000001"]


def test_cache_reuses_evaluations():
    counters = {}
    strategies = {"alpha": _FakeStrategy("alpha", {"000001"}, counters)}
    provider = _FakeProvider()
    cache = {}

    old_get = screener_module.get_substrategy
    screener_module.get_substrategy = strategies.get
    try:
        screener_module.screen(
            substrategy_ids=["alpha"],
            mode="OR",
            universe=["000001"],
            date="20260101",
            data_provider=provider,
            cache=cache,
        )
        first_calls = counters["alpha"]
        screener_module.screen(
            substrategy_ids=["alpha"],
            mode="OR",
            universe=["000001"],
            date="20260101",
            data_provider=provider,
            cache=cache,
        )
    finally:
        screener_module.get_substrategy = old_get

    assert first_calls == 1
    assert counters["alpha"] == 1
    assert provider.calls == 1


if __name__ == "__main__":
    test_and_semantics()
    test_or_semantics_and_hit_ids()
    test_empty_selection_returns_empty()
    test_bad_data_skipped()
    test_cache_reuses_evaluations()
    print("All tests passed")
