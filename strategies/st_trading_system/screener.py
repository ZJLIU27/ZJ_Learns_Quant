"""Pure screening engine for combining substrategy signals."""

from __future__ import annotations

from .models import ScreeningResult
from .substrategies import get_substrategy


def screen(
    substrategy_ids: list[str],
    mode: str,
    universe: list[str],
    date: str,
    data_provider,
    cache: dict | None = None,
) -> list[ScreeningResult]:
    """Screen a stock universe with AND/OR composition semantics."""
    if not substrategy_ids:
        return []

    normalized_mode = mode.upper()
    if normalized_mode not in {"AND", "OR"}:
        raise ValueError(f"Unsupported mode: {mode}")

    strategies = []
    max_rows = 0
    for substrategy_id in substrategy_ids:
        strategy = get_substrategy(substrategy_id)
        if strategy is None:
            raise KeyError(f"Unknown substrategy id: {substrategy_id}")
        strategies.append(strategy)
        max_rows = max(max_rows, int(getattr(strategy, "min_rows", 0)))

    result_rows: list[ScreeningResult] = []
    cache_store = cache if cache is not None else {}
    cache_token = None
    if hasattr(data_provider, "cache_token"):
        cache_token = data_provider.cache_token()

    for code in universe:
        required_keys = [
            (cache_token, code, strategy.id, date)
            for strategy in strategies
        ]
        all_cached = cache is not None and all(key in cache_store for key in required_keys)

        df = None
        if not all_cached:
            df = data_provider.get_history(code=code, end_date=date, days=max_rows or 250)
            if df is None or df.empty:
                continue

        hit_ids: list[str] = []
        indicators_snapshot: dict = {}

        for strategy in strategies:
            cache_key = (cache_token, code, strategy.id, date)
            if cache_key in cache_store:
                triggered, snapshot = cache_store[cache_key]
            else:
                triggered, snapshot = strategy.evaluate(df)
                cache_store[cache_key] = (triggered, snapshot)

            if triggered:
                hit_ids.append(strategy.id)
                indicators_snapshot.update(snapshot)

        if normalized_mode == "AND" and len(hit_ids) != len(strategies):
            continue
        if normalized_mode == "OR" and not hit_ids:
            continue

        close_value = indicators_snapshot.get("close")
        if close_value is None and df is not None:
            close_value = float(df["close"].iloc[-1])
        elif close_value is None and all_cached:
            close_value = 0.0

        result_rows.append(
            ScreeningResult(
                code=code,
                close=float(close_value),
                hit_ids=hit_ids,
                hit_count=len(hit_ids),
                indicators_snapshot=indicators_snapshot,
            )
        )

    return sorted(result_rows, key=lambda item: item.code)
