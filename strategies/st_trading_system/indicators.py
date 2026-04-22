"""Vectorized technical indicators for the trading system.

All functions accept a DataFrame with columns: open, high, low, close, vol
and return the same DataFrame with new indicator columns appended.

SMA convention (matches TongDaXin SMA(X,N,1)):
  SMA(X, N, 1) = X.ewm(alpha=1/N, adjust=False).mean()
  This is NOT a simple rolling mean. The ewm alpha=1/N formula means:
    result[t] = (1 - 1/N) * result[t-1] + (1/N) * X[t]
  which equals (N-1)/N * prev + 1/N * current.

No external TA-Lib dependency. Pure pandas/numpy vectorized operations.
"""

import numpy as np
import pandas as pd


def calc_bbi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute BBI (Bull and Bear Index).

    Formula: BBI = (MA3 + MA6 + MA12 + MA24) / 4
    where MAn = simple rolling mean of close over n periods.

    New column added: 'bbi'
    First 23 rows will be NaN (rolling(24) warm-up).
    """
    close = df["close"]
    ma3 = close.rolling(3).mean()
    ma6 = close.rolling(6).mean()
    ma12 = close.rolling(12).mean()
    ma24 = close.rolling(24).mean()
    df = df.copy()
    df["bbi"] = (ma3 + ma6 + ma12 + ma24) / 4.0
    return df


def calc_white_line(df: pd.DataFrame) -> pd.DataFrame:
    """Compute white line indicator (double EMA of close).

    Formula: white_line = EMA(EMA(close, 10), 10)
    Matches TongDaXin EMA(X,N) = X.ewm(alpha=2/(N+1), adjust=False).mean()

    Note: TongDaXin EMA uses alpha = 2/(N+1), not 1/N.
    EMA(close, 10): alpha = 2/11
    EMA(EMA(close,10), 10): second pass with same alpha.

    New column added: 'white_line'
    """
    close = df["close"]
    alpha = 2.0 / (10 + 1)
    ema1 = close.ewm(alpha=alpha, adjust=False).mean()
    white_line = ema1.ewm(alpha=alpha, adjust=False).mean()
    df = df.copy()
    df["white_line"] = white_line
    return df


def calc_yellow_line(df: pd.DataFrame) -> pd.DataFrame:
    """Compute yellow line indicator (average of four rolling means).

    Formula: yellow_line = (MA14 + MA28 + MA57 + MA114) / 4
    where MAn = simple rolling mean of close over n periods.

    New column added: 'yellow_line'
    First 113 rows will be NaN (rolling(114) warm-up).
    """
    close = df["close"]
    ma14 = close.rolling(14).mean()
    ma28 = close.rolling(28).mean()
    ma57 = close.rolling(57).mean()
    ma114 = close.rolling(114).mean()
    df = df.copy()
    df["yellow_line"] = (ma14 + ma28 + ma57 + ma114) / 4.0
    return df


def calc_short_stoch(df: pd.DataFrame) -> pd.DataFrame:
    """Compute short-term stochastic oscillator.

    Formula: short_stoch = 100 * (C - LLV(L,3)) / (HHV(H,3) - LLV(L,3) + eps)
    where:
      LLV(L,3) = df['low'].rolling(3).min()
      HHV(H,3) = df['high'].rolling(3).max()
      eps = 1e-10 to prevent division by zero

    Note: HHV uses high (not close) in the denominator per standard stochastic
    formula. Numerator uses (close - lowest low).

    New column added: 'short_stoch'
    Values in [0, 100] for rows with sufficient history.
    """
    close = df["close"]
    low = df["low"]
    high = df["high"]
    llv3 = low.rolling(3).min()
    hhv3 = high.rolling(3).max()
    df = df.copy()
    df["short_stoch"] = 100.0 * (close - llv3) / (hhv3 - llv3 + 1e-10)
    return df


def calc_long_stoch(df: pd.DataFrame) -> pd.DataFrame:
    """Compute long-term stochastic oscillator.

    Formula: long_stoch = 100 * (C - LLV(L,21)) / (HHV(H,21) - LLV(L,21) + eps)
    where:
      LLV(L,21) = df['low'].rolling(21).min()
      HHV(H,21) = df['high'].rolling(21).max()
      eps = 1e-10 to prevent division by zero

    New column added: 'long_stoch'
    Values in [0, 100] for rows with sufficient history.
    """
    close = df["close"]
    low = df["low"]
    high = df["high"]
    llv21 = low.rolling(21).min()
    hhv21 = high.rolling(21).max()
    df = df.copy()
    df["long_stoch"] = 100.0 * (close - llv21) / (hhv21 - llv21 + 1e-10)
    return df


def calc_zhuan(df: pd.DataFrame) -> pd.DataFrame:
    """Compute brick chart (砖型图) indicator.

    Full derivation chain (TongDaXin formula -> Python):

    VAR1A = (HHV(HIGH,4) - CLOSE) / (HHV(HIGH,4) - LLV(LOW,4)) * 100 - 90
    VAR2A = SMA(VAR1A, 4, 1) + 100          # SMA(X,N,1): ewm alpha=1/N
    VAR3A = (CLOSE - LLV(LOW,4)) / (HHV(HIGH,4) - LLV(LOW,4)) * 100
    VAR4A = SMA(VAR3A, 6, 1)
    VAR5A = SMA(VAR4A, 6, 1) + 100
    VAR6A = VAR5A - VAR2A
    signal = IF(VAR6A > 4, VAR6A - 4, 0)    # the "砖型图" line

    XG derivation (two-bar rising pattern):
      AA = signal.shift(1) < signal          # signal rising vs previous bar
      CC = (~AA.shift(1).fillna(False)) & AA  # previous bar NOT rising, current IS rising
      xg = CC                                 # True on first bar of upswing

    Note on SMA vs EWM: SMA(X,N,1) in TongDaXin equals ewm(alpha=1/N, adjust=False).
    This differs from standard rolling mean.

    New columns added: 'var6a', 'signal_zhuan', 'xg'
    'xg' is a boolean Series; True indicates a valid brick chart buy signal.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    hhv4 = high.rolling(4).max()
    llv4 = low.rolling(4).min()
    range4 = hhv4 - llv4

    # VAR1A: position from high end of 4-bar range, shifted to ~[-90, 10]
    var1a = (hhv4 - close) / (range4 + 1e-10) * 100.0 - 90.0

    # VAR2A: smoothed VAR1A shifted up by 100
    var2a = var1a.ewm(alpha=1.0 / 4, adjust=False).mean() + 100.0

    # VAR3A: position from low end of 4-bar range, [0, 100]
    var3a = (close - llv4) / (range4 + 1e-10) * 100.0

    # VAR4A: first smoothing of VAR3A
    var4a = var3a.ewm(alpha=1.0 / 6, adjust=False).mean()

    # VAR5A: second smoothing + 100
    var5a = var4a.ewm(alpha=1.0 / 6, adjust=False).mean() + 100.0

    # VAR6A: the raw brick chart line
    var6a = var5a - var2a

    # signal: only positive when VAR6A > 4
    signal = var6a.where(var6a > 4, other=0.0)

    # XG: two-bar rising detection
    # AA: signal is rising vs previous bar (boolean numpy array)
    aa_vals = (signal.shift(1) < signal).values.astype(bool)
    # prev_aa: shift AA by 1; first element defaults to False
    prev_aa_vals = np.empty(len(aa_vals), dtype=bool)
    prev_aa_vals[0] = False
    prev_aa_vals[1:] = aa_vals[:-1]
    # CC: previous bar AA was False, current AA is True (start of upswing)
    cc_vals = (~prev_aa_vals) & aa_vals
    xg = pd.Series(cc_vals, index=df.index, dtype=bool)

    df = df.copy()
    df["var6a"] = var6a
    df["signal_zhuan"] = signal
    df["xg"] = xg
    return df


def calc_danzhen_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the display-oriented 单针下20 panel from the confirmed note formula.

    This keeps chart rendering aligned with the Obsidian source without changing
    the existing strategy scanner implementation.
    """
    close = df["close"]
    low = df["low"]

    llv3 = low.rolling(3).min()
    llv10 = low.rolling(10).min()
    llv20 = low.rolling(20).min()
    llv21 = low.rolling(21).min()

    hhv_close_3 = close.rolling(3).max()
    hhv_close_10 = close.rolling(10).max()
    hhv_close_20 = close.rolling(20).max()
    hhv_close_21 = close.rolling(21).max()

    short = 100.0 * (close - llv3) / (hhv_close_3 - llv3 + 1e-10)
    medium = 100.0 * (close - llv10) / (hhv_close_10 - llv10 + 1e-10)
    medium_long = 100.0 * (close - llv20) / (hhv_close_20 - llv20 + 1e-10)
    long = 100.0 * (close - llv21) / (hhv_close_21 - llv21 + 1e-10)

    df = df.copy()
    df["danzhen_short"] = short
    df["danzhen_medium"] = medium
    df["danzhen_medium_long"] = medium_long
    df["danzhen_long"] = long
    df["danzhen_four_line_zero"] = np.where(
        (short <= 6) & (medium <= 6) & (medium_long <= 6) & (long <= 6),
        -30.0,
        0.0,
    )
    df["danzhen_short_below_20"] = np.where(
        (short <= 20) & (long >= 60),
        -30.0,
        0.0,
    )
    df["danzhen_short_cross_long"] = np.where(
        (short.shift(1) <= long.shift(1)) & (short > long) & (long < 20),
        -30.0,
        0.0,
    )
    df["danzhen_short_cross_medium"] = np.where(
        (short.shift(1) <= medium.shift(1)) & (short > medium) & (medium < 30),
        -30.0,
        0.0,
    )
    return df
