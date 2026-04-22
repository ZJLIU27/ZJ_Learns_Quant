"""B1 bundle substrategy."""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_bbi, calc_white_line


class B1SubStrategy(BaseSubStrategy):
    id = "b1"
    name = "B1 候选池"
    description = "close>BBI，白线上行，近4根存在大实体K线"
    tags = ["entry", "bundle"]
    min_rows = 24
    exit_monitor_id = "close_below_bbi"

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_bbi(df)
        df = calc_white_line(df)

        close = float(df["close"].iloc[-1])
        bbi = df["bbi"].iloc[-1]
        white_line_last = df["white_line"].iloc[-1]
        white_line_prev = df["white_line"].iloc[-2]
        recent_body_ratio = (
            (df["open"].iloc[-4:] - df["close"].iloc[-4:]).abs()
            / df["close"].iloc[-4:]
        )
        body_ratio_max = float(recent_body_ratio.max())

        if pd.isna(bbi) or pd.isna(white_line_last) or pd.isna(white_line_prev):
            return False, {}

        snapshot = {
            "close": close,
            "bbi": float(bbi),
            "white_line": float(white_line_last),
            "body_ratio_max_4": body_ratio_max,
        }
        triggered = (
            close > float(bbi)
            and float(white_line_last) > float(white_line_prev)
            and body_ratio_max > 0.03
        )
        return triggered, snapshot
