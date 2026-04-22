"""Monitor that alerts when close falls below BBI."""

from __future__ import annotations

import pandas as pd

from ..base import BaseMonitor
from ..indicators import calc_bbi
from ..models import Position


class CloseBelowBBIMonitor(BaseMonitor):
    id = "close_below_bbi"
    description = "close < BBI 时告警"

    def check(self, df: pd.DataFrame, position: Position) -> tuple[bool, str]:
        if len(df) < 24:
            return False, "insufficient data for BBI"

        df = calc_bbi(df)
        close = df["close"].iloc[-1]
        bbi = df["bbi"].iloc[-1]
        if pd.isna(bbi):
            return False, "BBI unavailable"

        close_value = float(close)
        bbi_value = float(bbi)
        if close_value < bbi_value:
            return True, f"close={close_value:.4f} < bbi={bbi_value:.4f}"
        return False, f"close={close_value:.4f} >= bbi={bbi_value:.4f}"
