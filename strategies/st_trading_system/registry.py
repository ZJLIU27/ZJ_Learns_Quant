"""Generic plugin discovery for substrategies and monitors."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import Any


def discover_plugins(
    package_name: str,
    package_path: str | Path,
    base_class: type,
    *,
    reload_modules: bool = False,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Discover plugin subclasses in a package directory.

    Returns a mapping of plugin id -> plugin instance plus a list of
    ``(module_name, error)`` tuples for import/load problems.
    """
    importlib.invalidate_caches()

    path = Path(package_path)
    items: dict[str, Any] = {}
    errors: list[tuple[str, str]] = []

    for module_info in sorted(pkgutil.iter_modules([str(path)]), key=lambda item: item.name):
        if module_info.name.startswith("_"):
            continue

        full_name = f"{package_name}.{module_info.name}"
        try:
            if reload_modules and full_name in sys.modules:
                module = importlib.reload(sys.modules[full_name])
            else:
                module = importlib.import_module(full_name)
        except Exception as exc:  # pragma: no cover - exercised by registry tests
            errors.append((module_info.name, str(exc)))
            continue

        discovered = False
        for _, attr in inspect.getmembers(module, inspect.isclass):
            if attr is base_class or not issubclass(attr, base_class):
                continue
            if attr.__module__ != module.__name__:
                continue

            plugin = attr()
            plugin_id = getattr(plugin, "id", "")
            if not plugin_id:
                errors.append((module_info.name, "missing plugin id"))
                discovered = True
                continue
            if plugin_id in items:
                errors.append((module_info.name, f"duplicate id: {plugin_id}"))
                discovered = True
                continue
            items[plugin_id] = plugin
            discovered = True

        if not discovered:
            errors.append((module_info.name, f"no {base_class.__name__} subclass found"))

    return items, errors
