"""st_b2 KDJ Reversal Strategy Module

Standalone strategy logic with zero environment dependencies.
No imports of tushare, xtdata, or any platform-specific module.

Public API:
  - compute_kdj(closes, highs, lows, ...) -> (K, D, J)
  - generate_signals(market_data, params) -> {trade_date: [candidates]}
  - get_default_config() -> dict
"""

import numpy as np
import pandas as pd


def get_default_config() -> dict:
    """Return default strategy parameters."""
    return {
        "kdj_n": 9,
        "kdj_init": 50.0,
        "j_pre_max": 20.0,
        "j_now_max": 65.0,
        "daily_return_min_pct": 4.0,
        "vol_ratio_min": 1.1,
    }


def compute_kdj(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    n: int = 9,
    k_init: float = 50.0,
    d_init: float = 50.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute KDJ indicator arrays.

    Returns (K, D, J) arrays, same length as input.
    Formula matches TongDaXin SMA convention:
      RSV = (CLOSE - LLV(LOW,N)) / (HHV(HIGH,N) - LLV(LOW,N)) * 100
      K = SMA(RSV, 3, 1)  i.e.  K = (2*K_prev + RSV) / 3
      D = SMA(K, 3, 1)    i.e.  D = (2*D_prev + K) / 3
      J = 3*K - 2*D
    """
    length = len(closes)
    k_arr = np.zeros(length)
    d_arr = np.zeros(length)
    j_arr = np.zeros(length)

    k_prev = k_init
    d_prev = d_init

    for i in range(length):
        start = max(0, i - n + 1)
        low_n = np.min(lows[start : i + 1])
        high_n = np.max(highs[start : i + 1])

        if high_n == low_n:
            rsv = 0.0
        else:
            rsv = (closes[i] - low_n) / (high_n - low_n) * 100.0

        k = (2.0 * k_prev + rsv) / 3.0
        d = (2.0 * d_prev + k) / 3.0
        j = 3.0 * k - 2.0 * d

        k_arr[i] = k
        d_arr[i] = d
        j_arr[i] = j

        k_prev = k
        d_prev = d

    return k_arr, d_arr, j_arr


def generate_signals(
    market_data: dict[str, pd.DataFrame],
    params: dict | None = None,
) -> dict[str, list[dict]]:
    """Run st_b2 screening on all stocks.

    Args:
        market_data: {stock_code: DataFrame} with columns:
                     trade_date, open, high, low, close, vol
        params: Strategy parameters dict (uses defaults if None)

    Returns:
        {trade_date: [{code, close, daily_return_pct, vol_ratio, j_now, j_prev}, ...]}
        Candidates sorted by daily_return_pct descending per date.
    """
    if params is None:
        params = get_default_config()

    kdj_n = params.get("kdj_n", 9)
    kdj_init = params.get("kdj_init", 50.0)
    j_pre_max = params.get("j_pre_max", 20.0)
    j_now_max = params.get("j_now_max", 65.0)
    daily_return_min_pct = params.get("daily_return_min_pct", 4.0)
    vol_ratio_min = params.get("vol_ratio_min", 1.1)

    min_bars = kdj_n + 2  # Need at least N+2 bars for KDJ + previous J

    # Pre-compute per-stock data: index by trade_date for fast lookup
    stock_data: dict[str, list[dict]] = {}
    for code, df in market_data.items():
        if len(df) < min_bars:
            continue

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        vols = df["vol"].values.astype(float)
        dates = df["trade_date"].values

        k_arr, d_arr, j_arr = compute_kdj(closes, highs, lows, kdj_n, kdj_init)

        # Build per-date lookup: only store where we have enough history
        for i in range(min_bars - 1, len(df)):
            date = dates[i]
            prev_close = closes[i - 1]
            if prev_close <= 0:
                continue
            daily_ret = (closes[i] / prev_close - 1.0) * 100.0
            vol_ratio = vols[i] / vols[i - 1] if vols[i - 1] > 0 else 0.0

            # Apply screening conditions
            if j_arr[i - 1] >= j_pre_max:
                continue
            if j_arr[i] > j_now_max:
                continue
            if daily_ret <= daily_return_min_pct:
                continue
            if vol_ratio < vol_ratio_min:
                continue

            if date not in stock_data:
                stock_data[date] = []
            stock_data[date].append({
                "code": code,
                "close": float(closes[i]),
                "daily_return_pct": round(daily_ret, 2),
                "vol_ratio": round(vol_ratio, 2),
                "j_now": round(float(j_arr[i]), 2),
                "j_prev": round(float(j_arr[i - 1]), 2),
            })

    # Sort candidates by daily return (descending) per date
    result: dict[str, list[dict]] = {}
    for date in sorted(stock_data.keys()):
        candidates = sorted(stock_data[date], key=lambda x: x["daily_return_pct"], reverse=True)
        result[date] = candidates

    return result