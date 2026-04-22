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
    closes = [10 + i * 0.18 for i in range(110)]
    closes += [37.5, 37.7, 37.9, 38.1, 38.3, 38.5, 38.7, 38.9, 39.1]
    closes += [39.3, 39.5, 39.6, 39.7, 39.8, 39.9, 40.0, 40.0, 40.0]
    closes += [40.0, 39.8, 39.56]
    opens = [close * 0.995 for close in closes]
    highs = [max(open_price, close) + 0.2 for open_price, close in zip(opens, closes)]
    lows = [close - 0.2 for close in closes]
    lows[-3] = 39.6
    lows[-2] = 39.6
    lows[-1] = 39.375
    triggered, snapshot = strategy.evaluate(
        _make_ohlcv(closes, opens=opens, highs=highs, lows=lows)
    )
    assert triggered is True
    assert snapshot["danzhen_short"] <= 30
    assert snapshot["danzhen_long"] >= 80
    assert snapshot["white_line"] > snapshot["yellow_line"]
    assert snapshot["danzhen_variant"] == "30"
    assert snapshot["danzhen_signal"] == "单针下30"

    strict_closes = [10 + i * 0.18 for i in range(110)]
    strict_closes += [37.5, 37.7, 37.9, 38.1, 38.3, 38.5, 38.7, 38.9, 39.1]
    strict_closes += [39.3, 39.5, 39.6, 39.7, 39.8, 39.9, 40.0, 40.0, 40.0]
    strict_closes += [40.0, 39.8, 39.5]
    strict_opens = [close * 0.995 for close in strict_closes]
    strict_highs = [max(open_price, close) + 0.2 for open_price, close in zip(strict_opens, strict_closes)]
    strict_lows = [close - 0.2 for close in strict_closes]
    strict_lows[-3] = 39.6
    strict_lows[-2] = 39.6
    strict_lows[-1] = 39.375
    strict_triggered, strict_snapshot = strategy.evaluate(
        _make_ohlcv(
            strict_closes,
            opens=strict_opens,
            highs=strict_highs,
            lows=strict_lows,
        )
    )
    assert strict_triggered is True
    assert strict_snapshot["danzhen_short"] <= 20
    assert strict_snapshot["danzhen_long"] >= 80
    assert strict_snapshot["white_line"] > strict_snapshot["yellow_line"]
    assert strict_snapshot["danzhen_variant"] == "20"
    assert strict_snapshot["danzhen_signal"] == "单针下20"

    reject_closes = [60 - i * 0.25 for i in range(110)]
    reject_closes += [37.5, 37.7, 37.9, 38.1, 38.3, 38.5, 38.7, 38.9, 39.1]
    reject_closes += [39.3, 39.5, 39.6, 39.7, 39.8, 39.9, 40.0, 40.0, 40.0]
    reject_closes += [40.0, 39.8, 39.56]
    reject_opens = [close * 0.995 for close in reject_closes]
    reject_highs = [
        max(open_price, close) + 0.2
        for open_price, close in zip(reject_opens, reject_closes)
    ]
    reject_lows = [close - 0.2 for close in reject_closes]
    reject_lows[-3] = 39.6
    reject_lows[-2] = 39.6
    reject_lows[-1] = 39.375
    reject_triggered, reject_snapshot = strategy.evaluate(
        _make_ohlcv(
            reject_closes,
            opens=reject_opens,
            highs=reject_highs,
            lows=reject_lows,
        )
    )
    assert reject_triggered is False
    assert reject_snapshot["danzhen_short"] <= 30
    assert reject_snapshot["danzhen_long"] >= 80
    assert reject_snapshot["white_line"] <= reject_snapshot["yellow_line"]


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
