"""Tests for pure app helpers."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.app import (
    _resolve_screen_indicator_ids,
    _resolve_selected_screen_code,
    _resolve_selected_screen_code_from_rows,
)
from strategies.st_trading_system.models import ScreeningResult


def _result(code: str, hit_ids: list[str]) -> ScreeningResult:
    return ScreeningResult(
        code=code,
        close=10.0,
        hit_ids=hit_ids,
        hit_count=len(hit_ids),
        indicators_snapshot={},
    )


def test_resolve_selected_screen_code_defaults_to_first():
    results = [_result("000001", ["b1"]), _result("000002", ["zhuan"])]
    assert _resolve_selected_screen_code(results, None) == "000001"


def test_resolve_selected_screen_code_keeps_existing_when_present():
    results = [_result("000001", ["b1"]), _result("000002", ["zhuan"])]
    assert _resolve_selected_screen_code(results, "000002") == "000002"


def test_resolve_selected_screen_code_falls_back_when_missing():
    results = [_result("000003", ["danzhen20"]), _result("000004", ["zhuan"])]
    assert _resolve_selected_screen_code(results, "000001") == "000003"


def test_resolve_selected_screen_code_from_rows_prefers_selected_row():
    row_codes = ["000003", "000004", "000005"]
    assert _resolve_selected_screen_code_from_rows(row_codes, [1], "000003") == "000004"


def test_resolve_selected_screen_code_from_rows_keeps_previous_without_selection():
    row_codes = ["000003", "000004", "000005"]
    assert _resolve_selected_screen_code_from_rows(row_codes, [], "000005") == "000005"


def test_resolve_selected_screen_code_from_rows_falls_back_to_first_when_invalid():
    row_codes = ["000003", "000004", "000005"]
    assert _resolve_selected_screen_code_from_rows(row_codes, [99], "000001") == "000003"


def test_resolve_screen_indicator_ids_merges_defaults_and_manual():
    resolved = _resolve_screen_indicator_ids(["b1"], ["zhuan_panel", "yellow_line"])
    assert resolved == ["bbi", "white_line", "yellow_line", "zhuan_panel"]


if __name__ == "__main__":
    test_resolve_selected_screen_code_defaults_to_first()
    test_resolve_selected_screen_code_keeps_existing_when_present()
    test_resolve_selected_screen_code_falls_back_when_missing()
    test_resolve_selected_screen_code_from_rows_prefers_selected_row()
    test_resolve_selected_screen_code_from_rows_keeps_previous_without_selection()
    test_resolve_selected_screen_code_from_rows_falls_back_to_first_when_invalid()
    test_resolve_screen_indicator_ids_merges_defaults_and_manual()
    print("All tests passed")
