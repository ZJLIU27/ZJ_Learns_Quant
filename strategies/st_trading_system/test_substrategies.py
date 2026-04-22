"""Tests for built-in substrategies."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.substrategies import get_substrategy, list_substrategies


def _make_ohlcv(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    if opens is None:
        opens = [close * 0.99 for close in closes]
    if highs is None:
        highs = [max(open_price, close) + 0.5 for open_price, close in zip(opens, closes)]
    if lows is None:
        lows = [min(open_price, close) - 0.5 for open_price, close in zip(opens, closes)]

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


def test_discovery_finds_all_v1_bundles():
    ids = [strategy.id for strategy in list_substrategies()]
    assert ids == ["b1", "danzhen20", "zhuan"]


def test_b1_triggers_on_constructed_positive():
    strategy = get_substrategy("b1")
    closes = [10 + i * 0.2 for i in range(24)]
    opens = [close * 0.99 for close in closes]
    opens[-2] = closes[-2] * 0.94
    triggered, snapshot = strategy.evaluate(_make_ohlcv(closes, opens=opens))
    assert triggered is True
    assert {"close", "bbi", "white_line"}.issubset(snapshot)


def test_b1_rejects_on_constructed_negative():
    strategy = get_substrategy("b1")

    below_bbi_closes = [14.0] * 24
    below_triggered, _ = strategy.evaluate(_make_ohlcv(below_bbi_closes))
    assert below_triggered is False

    white_fail_closes = [10 + i * 0.2 for i in range(20)] + [10.8, 10.8, 10.8, 12.0]
    white_fail_opens = [close * 0.99 for close in white_fail_closes]
    white_fail_opens[-2] = white_fail_closes[-2] * 0.94
    white_triggered, _ = strategy.evaluate(_make_ohlcv(white_fail_closes, opens=white_fail_opens))
    assert white_triggered is False

    no_body_closes = [10 + i * 0.2 for i in range(24)]
    no_body_opens = [close * 0.995 for close in no_body_closes]
    no_body_triggered, _ = strategy.evaluate(_make_ohlcv(no_body_closes, opens=no_body_opens))
    assert no_body_triggered is False


def test_danzhen20_trigger_and_reject():
    strategy = get_substrategy("danzhen20")
    closes = [10 + i * 0.4 for i in range(40)] + [24.0, 23.0, 22.0, 21.0, 16.0]
    opens = [close * 1.01 for close in closes]
    highs = [close + 1.0 for close in closes]
    lows = [close - 1.0 for close in closes]
    triggered, snapshot = strategy.evaluate(
        _make_ohlcv(closes, opens=opens, highs=highs, lows=lows)
    )
    assert triggered is True
    assert snapshot["long_stoch"] < 30
    assert snapshot["red_line_prev_21_max"] >= 80

    reject_closes = [10 + i * 0.6 for i in range(25)]
    reject_closes += [24.4 - (i + 1) * 0.3 for i in range(26)]
    reject_closes += [18.0, 16.0]
    reject_triggered, reject_snapshot = strategy.evaluate(_make_ohlcv(reject_closes))
    assert reject_triggered is False
    assert reject_snapshot["long_stoch"] < 30
    assert reject_snapshot["red_line_prev_21_max"] < 80


def test_zhuan_trigger_and_reject():
    strategy = get_substrategy("zhuan")
    positive_closes = [10 + i * 0.2 for i in range(20)] + [12.0, 12.0, 13.0, 15.0]
    positive_triggered, snapshot = strategy.evaluate(_make_ohlcv(positive_closes))
    assert positive_triggered is True
    assert "signal_zhuan" in snapshot

    negative_triggered, _ = strategy.evaluate(_make_ohlcv([10 + i * 0.2 for i in range(24)]))
    assert negative_triggered is False


def test_short_data_returns_false():
    short_df = _make_ohlcv([10.0, 10.2, 10.4, 10.6, 10.8])
    for substrategy_id in ("b1", "danzhen20", "zhuan"):
        triggered, _ = get_substrategy(substrategy_id).evaluate(short_df)
        assert triggered is False


if __name__ == "__main__":
    test_discovery_finds_all_v1_bundles()
    test_b1_triggers_on_constructed_positive()
    test_b1_rejects_on_constructed_negative()
    test_danzhen20_trigger_and_reject()
    test_zhuan_trigger_and_reject()
    test_short_data_returns_false()
    print("All tests passed")
