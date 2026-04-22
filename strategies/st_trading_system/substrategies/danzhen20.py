"""Single-needle-below-20 bundle substrategy."""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_long_stoch, calc_short_stoch


class Danzhen20SubStrategy(BaseSubStrategy):
    id = "danzhen20"
    name = "单针探 20"
    description = "short_stoch<=20 且 long_stoch>=60"
    tags = ["entry", "bundle"]
    min_rows = 21
    exit_monitor_id = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_short_stoch(df)
        df = calc_long_stoch(df)
        short_stoch = df["short_stoch"].iloc[-1]
        long_stoch = df["long_stoch"].iloc[-1]
        close = float(df["close"].iloc[-1])

        if pd.isna(short_stoch) or pd.isna(long_stoch):
            return False, {}

        snapshot = {
            "close": close,
            "short_stoch": float(short_stoch),
            "long_stoch": float(long_stoch),
        }
        triggered = float(short_stoch) <= 20.0 and float(long_stoch) >= 60.0
        return triggered, snapshot
