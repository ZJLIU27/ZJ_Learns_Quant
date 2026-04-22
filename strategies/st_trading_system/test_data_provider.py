"""Tests for LocalCSVProvider."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.data_provider import LocalCSVProvider

_FIXTURE_DIR = Path(__file__).resolve().parent / "test_fixtures" / "local_csv"


def test_get_history_normalizes_and_filters():
    provider = LocalCSVProvider(str(_FIXTURE_DIR))
    df = provider.get_history("000001", end_date="20260102", days=5)
    assert df is not None
    assert list(df["trade_date"]) == ["20260101", "20260102"]
    assert "vol" in df.columns
    assert float(df["close"].iloc[-1]) == 11.0


def test_get_latest_returns_tail_window():
    provider = LocalCSVProvider(str(_FIXTURE_DIR))
    df = provider.get_latest("000001", days=2)
    assert df is not None
    assert list(df["trade_date"]) == ["20260102", "20260103"]


def test_missing_csv_returns_none():
    provider = LocalCSVProvider(str(_FIXTURE_DIR))
    assert provider.get_history("999999", end_date="20260101") is None


def test_get_universe_respects_growth_board_flag():
    provider = LocalCSVProvider(str(_FIXTURE_DIR))
    assert provider.get_universe(include_growth_boards=False) == ["000001"]
    assert provider.get_universe(include_growth_boards=True) == ["000001", "300001"]


if __name__ == "__main__":
    test_get_history_normalizes_and_filters()
    test_get_latest_returns_tail_window()
    test_missing_csv_returns_none()
    test_get_universe_respects_growth_board_flag()
    print("All tests passed")
