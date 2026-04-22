"""Brick-chart bundle substrategy."""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_zhuan


class ZhuanSubStrategy(BaseSubStrategy):
    id = "zhuan"
    name = "砖型图"
    description = "砖型图 XG 首次上拐触发"
    tags = ["entry", "bundle"]
    min_rows = 10
    exit_monitor_id = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_zhuan(df)
        signal_zhuan = df["signal_zhuan"].iloc[-1]
        var6a = df["var6a"].iloc[-1]
        xg = df["xg"].iloc[-1]

        if pd.isna(signal_zhuan) or pd.isna(var6a):
            return False, {}

        snapshot = {
            "close": float(df["close"].iloc[-1]),
            "signal_zhuan": float(signal_zhuan),
            "var6a": float(var6a),
        }
        return bool(xg), snapshot
