"""Data provider abstraction for local CSV-backed OHLCV data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tools.data_adapter.local_csv import get_stock_list

_REQUIRED_COLS = {"trade_date", "open", "high", "low", "close", "vol"}


class LocalCSVProvider:
    """Thin wrapper around the repository's local CSV data adapter."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self._data_path = Path(data_dir)

    def cache_token(self) -> tuple[str, int | None]:
        """Return a stable token used by screener cache keys."""
        try:
            mtime = self._data_path.stat().st_mtime_ns
        except FileNotFoundError:
            mtime = None
        return (self.data_dir, mtime)

    def get_universe(self, include_growth_boards: bool = False) -> list[str]:
        """List stock codes available in the configured data directory."""
        return get_stock_list(self.data_dir, include_growth_boards=include_growth_boards)

    def get_history(
        self,
        code: str,
        end_date: str | None,
        days: int = 250,
    ) -> pd.DataFrame | None:
        """Load normalized OHLCV history for one stock."""
        csv_path = self._data_path / f"{code}.csv"
        if not csv_path.exists():
            return None

        try:
            df = pd.read_csv(csv_path, dtype={"date": str, "trade_date": str})
        except Exception:
            return None

        if df.empty:
            return None

        if "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})
        if "volume" in df.columns:
            df = df.rename(columns={"volume": "vol"})
        if not _REQUIRED_COLS.issubset(df.columns):
            return None

        trade_date = df["trade_date"].astype(str).str.replace("-", "", regex=False)
        df = df.copy()
        df["trade_date"] = trade_date

        for column in ("open", "high", "low", "close", "vol"):
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna(subset=["trade_date", "open", "high", "low", "close", "vol"])
        df = df.sort_values("trade_date").reset_index(drop=True)
        if end_date:
            df = df[df["trade_date"] <= end_date].reset_index(drop=True)
        if df.empty:
            return None

        return df.tail(days).reset_index(drop=True)

    def get_latest(
        self,
        code: str,
        days: int = 250,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """Return the most recent available history window."""
        return self.get_history(code=code, end_date=end_date, days=days)
