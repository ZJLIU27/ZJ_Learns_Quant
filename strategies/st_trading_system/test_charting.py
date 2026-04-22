"""Tests for shared chart building."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.charting import build_stock_chart


def _make_ohlcv(length: int = 40) -> pd.DataFrame:
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


class _FakeProvider:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_history(self, code, end_date, days):
        df = self.df.copy()
        if end_date:
            df = df[df["trade_date"] <= end_date].reset_index(drop=True)
        return df.tail(days).reset_index(drop=True)


def test_build_stock_chart_respects_end_date():
    provider = _FakeProvider(_make_ohlcv(50))
    bundle = build_stock_chart(
        code="000001",
        end_date="20260210",
        days=120,
        active_indicator_ids=["bbi", "white_line"],
        provider=provider,
    )
    assert bundle is not None
    assert bundle.df["trade_date"].iloc[-1] == "20260210"


def test_build_stock_chart_adds_expected_panels():
    provider = _FakeProvider(_make_ohlcv(60))
    bundle = build_stock_chart(
        code="000001",
        end_date="20260220",
        days=120,
        active_indicator_ids=["bbi", "white_line", "yellow_line", "danzhen_panel", "zhuan_panel"],
        provider=provider,
    )
    assert bundle is not None
    assert [trace.name for trace in bundle.main_panel.traces] == ["OHLC", "BBI", "白线", "黄线"]
    assert [panel.panel_id for panel in bundle.subcharts] == ["danzhen_panel", "zhuan_panel"]
    assert len(bundle.subcharts[0].hlines) == 2


if __name__ == "__main__":
    test_build_stock_chart_respects_end_date()
    test_build_stock_chart_adds_expected_panels()
    print("All tests passed")
