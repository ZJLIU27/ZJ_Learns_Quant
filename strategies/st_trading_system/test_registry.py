"""Tests for generic registry discovery."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.base import BaseSubStrategy
from strategies.st_trading_system.registry import discover_plugins

_FIXTURE_ROOT = Path(__file__).resolve().parent / "test_fixtures"


def test_discover_plugins_collects_valid_subclasses():
    package_name = "registry_valid_pkg"
    package_dir = _FIXTURE_ROOT / package_name
    sys.path.insert(0, str(_FIXTURE_ROOT))
    try:
        items, errors = discover_plugins(package_name, package_dir, BaseSubStrategy, reload_modules=True)
    finally:
        sys.path.remove(str(_FIXTURE_ROOT))

        assert list(items) == ["alpha"]
        assert errors == []


def test_discover_plugins_reports_duplicate_ids():
    package_name = "registry_duplicate_pkg"
    package_dir = _FIXTURE_ROOT / package_name
    sys.path.insert(0, str(_FIXTURE_ROOT))
    try:
        items, errors = discover_plugins(package_name, package_dir, BaseSubStrategy, reload_modules=True)
    finally:
        sys.path.remove(str(_FIXTURE_ROOT))

        assert list(items) == ["dup"]
        assert len(errors) == 1
        assert errors[0][0] == "beta"
        assert "duplicate id" in errors[0][1]


def test_discover_plugins_reports_import_errors():
    package_name = "registry_broken_pkg"
    package_dir = _FIXTURE_ROOT / package_name
    sys.path.insert(0, str(_FIXTURE_ROOT))
    try:
        items, errors = discover_plugins(package_name, package_dir, BaseSubStrategy, reload_modules=True)
    finally:
        sys.path.remove(str(_FIXTURE_ROOT))

        assert items == {}
        assert len(errors) == 1
        assert errors[0][0] == "broken"
        assert "boom" in errors[0][1]


if __name__ == "__main__":
    test_discover_plugins_collects_valid_subclasses()
    test_discover_plugins_reports_duplicate_ids()
    test_discover_plugins_reports_import_errors()
    print("All tests passed")
