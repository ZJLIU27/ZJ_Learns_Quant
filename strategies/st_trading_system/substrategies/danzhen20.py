"""Single-needle-below-20 bundle substrategy."""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_danzhen_panel


class Danzhen20SubStrategy(BaseSubStrategy):
    id = "danzhen20"
    name = "单针探 20"
    description = "红线近21根曾>=80，且本根下穿30"
    tags = ["entry", "bundle"]
    min_rows = 42
    exit_monitor_id = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_danzhen_panel(df)
        short_stoch = df["danzhen_short"].iloc[-1]
        long_stoch = df["danzhen_long"].iloc[-1]
        prev_long_stoch = df["danzhen_long"].iloc[-2]
        prior_red_line_max = df["danzhen_long"].shift(1).rolling(21, min_periods=21).max().iloc[-1]
        close = float(df["close"].iloc[-1])

        if pd.isna(short_stoch) or pd.isna(long_stoch) or pd.isna(prev_long_stoch) or pd.isna(prior_red_line_max):
            return False, {}

        snapshot = {
            "close": close,
            "short_stoch": float(short_stoch),
            "long_stoch": float(long_stoch),
            "red_line_prev_21_max": float(prior_red_line_max),
        }
        triggered = (
            float(long_stoch) < 30.0
            and float(prev_long_stoch) >= 30.0
            and float(prior_red_line_max) >= 80.0
        )
        return triggered, snapshot
