"""Auto-discovered exit monitors."""

from __future__ import annotations

from pathlib import Path

from ..base import BaseMonitor
from ..registry import discover_plugins

_ITEMS: dict[str, BaseMonitor] = {}
_ERRORS: list[tuple[str, str]] = []


def refresh_monitors() -> None:
    global _ITEMS, _ERRORS
    _ITEMS, _ERRORS = discover_plugins(
        package_name=__name__,
        package_path=Path(__file__).resolve().parent,
        base_class=BaseMonitor,
        reload_modules=True,
    )


def list_monitors() -> list[BaseMonitor]:
    return sorted(_ITEMS.values(), key=lambda item: item.id)


def get_monitor(monitor_id: str) -> BaseMonitor | None:
    return _ITEMS.get(monitor_id)


def registry_errors() -> list[tuple[str, str]]:
    return list(_ERRORS)


refresh_monitors()
