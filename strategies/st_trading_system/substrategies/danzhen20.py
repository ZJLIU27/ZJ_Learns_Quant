"""Single-needle-below-20 bundle substrategy."""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_danzhen_panel, calc_white_line, calc_yellow_line


class Danzhen20SubStrategy(BaseSubStrategy):
    id = "danzhen20"
    name = "单针下20/30"
    description = "短<=30(严格20) 且 长>=80 且 白线>黄线"
    tags = ["entry", "bundle"]
    min_rows = 114
    exit_monitor_id = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_yellow_line(calc_white_line(calc_danzhen_panel(df)))
        short_stoch = df["danzhen_short"].iloc[-1]
        long_stoch = df["danzhen_long"].iloc[-1]
        white_line = df["white_line"].iloc[-1]
        yellow_line = df["yellow_line"].iloc[-1]
        close = float(df["close"].iloc[-1])

        if (
            pd.isna(short_stoch)
            or pd.isna(long_stoch)
            or pd.isna(white_line)
            or pd.isna(yellow_line)
        ):
            return False, {}

        is_hit_30 = (
            float(short_stoch) <= 30.0
            and float(long_stoch) >= 80.0
            and float(white_line) > float(yellow_line)
        )
        is_hit_20 = (
            float(short_stoch) <= 20.0
            and float(long_stoch) >= 80.0
            and float(white_line) > float(yellow_line)
        )

        variant = "20" if is_hit_20 else "30"
        snapshot = {
            "close": close,
            "danzhen_short": float(short_stoch),
            "danzhen_long": float(long_stoch),
            "white_line": float(white_line),
            "yellow_line": float(yellow_line),
            "danzhen_variant": variant,
            "danzhen_signal": f"单针下{variant}",
        }
        return is_hit_30, snapshot
