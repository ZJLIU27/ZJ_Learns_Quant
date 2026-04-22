"""Auto-discovered substrategy plugins."""

from __future__ import annotations

from pathlib import Path

from ..base import BaseSubStrategy
from ..registry import discover_plugins

_ITEMS: dict[str, BaseSubStrategy] = {}
_ERRORS: list[tuple[str, str]] = []


def refresh_substrategies() -> None:
    global _ITEMS, _ERRORS
    _ITEMS, _ERRORS = discover_plugins(
        package_name=__name__,
        package_path=Path(__file__).resolve().parent,
        base_class=BaseSubStrategy,
        reload_modules=True,
    )


def list_substrategies() -> list[BaseSubStrategy]:
    return sorted(_ITEMS.values(), key=lambda item: item.id)


def get_substrategy(substrategy_id: str) -> BaseSubStrategy | None:
    return _ITEMS.get(substrategy_id)


def registry_errors() -> list[tuple[str, str]]:
    return list(_ERRORS)


refresh_substrategies()
