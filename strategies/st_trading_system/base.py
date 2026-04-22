"""Base contracts for entry substrategies and exit monitors."""

from __future__ import annotations

import pandas as pd

from .models import Position


class BaseSubStrategy:
    """Contract for one pluggable entry substrategy."""

    id: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] = []
    min_rows: int = 10
    exit_monitor_id: str | None = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        """Return whether the latest bar hits and an indicator snapshot."""
        raise NotImplementedError


class BaseMonitor:
    """Contract for one pluggable exit-condition monitor."""

    id: str = ""
    description: str = ""

    def check(self, df: pd.DataFrame, position: Position) -> tuple[bool, str]:
        """Return whether an alert is triggered and the reason."""
        raise NotImplementedError
