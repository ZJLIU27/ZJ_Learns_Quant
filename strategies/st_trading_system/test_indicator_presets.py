"""Tests for chart indicator presets."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.indicator_presets import (
    apply_indicator_presets,
    get_default_indicator_ids,
    list_indicator_presets,
)


def _make_ohlcv(length: int = 140) -> pd.DataFrame:
    closes = [10 + i * 0.2 for i in range(length)]
    opens = [close * 0.99 for close in closes]
    highs = [max(open_price, close) + 0.5 for open_price, close in zip(opens, closes)]
    lows = [min(open_price, close) - 0.5 for open_price, close in zip(opens, closes)]
    dates = pd.date_range("2026-01-01", periods=length, freq="D")
    return pd.DataFrame(
        {
            "trade_date": dates.strftime("%Y%m%d"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "vol": [1000.0] * length,
        }
    )


def test_list_indicator_presets_and_defaults():
    preset_ids = [preset.id for preset in list_indicator_presets()]
    assert preset_ids == ["bbi", "white_line", "yellow_line", "danzhen_panel", "zhuan_panel"]
    assert get_default_indicator_ids(["b1"]) == ["bbi", "white_line", "yellow_line"]
    assert get_default_indicator_ids(["danzhen20"]) == ["danzhen_panel"]
    assert get_default_indicator_ids(["zhuan"]) == ["zhuan_panel"]
    assert get_default_indicator_ids(["b1", "zhuan"]) == ["bbi", "white_line", "yellow_line", "zhuan_panel"]


def test_apply_indicator_presets_adds_overlay_columns():
    df = apply_indicator_presets(_make_ohlcv(), ["bbi", "white_line", "yellow_line"])
    assert {"bbi", "white_line", "yellow_line"}.issubset(df.columns)
    assert df["yellow_line"].notna().sum() > 0


def test_apply_indicator_presets_adds_danzhen_columns():
    df = apply_indicator_presets(_make_ohlcv(), ["danzhen_panel"])
    required = {
        "danzhen_short",
        "danzhen_medium",
        "danzhen_medium_long",
        "danzhen_long",
        "danzhen_four_line_zero",
        "danzhen_short_below_20",
        "danzhen_short_cross_long",
        "danzhen_short_cross_medium",
    }
    assert required.issubset(df.columns)


def test_apply_indicator_presets_adds_zhuan_columns():
    df = apply_indicator_presets(_make_ohlcv(), ["zhuan_panel"])
    assert {"var6a", "signal_zhuan", "xg"}.issubset(df.columns)


if __name__ == "__main__":
    test_list_indicator_presets_and_defaults()
    test_apply_indicator_presets_adds_overlay_columns()
    test_apply_indicator_presets_adds_danzhen_columns()
    test_apply_indicator_presets_adds_zhuan_columns()
    print("All tests passed")
