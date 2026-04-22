"""Tests for storage module."""

import json
import os
import sys
import tempfile
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.models import Position
from strategies.st_trading_system.storage import (
    add_position,
    delete_position,
    load_positions,
    save_positions,
    update_position,
)


def _tmpfile():
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    handle.close()
    os.unlink(handle.name)
    return handle.name


def test_missing_file_returns_empty():
    path = _tmpfile()
    assert load_positions(path) == []


def test_roundtrip():
    path = _tmpfile()
    positions = [
        Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"]),
        Position(
            code="600000",
            entry_date="20260102",
            cost_basis=20.0,
            strategy_ids=["b1", "danzhen20"],
            quantity=100.0,
            notes="n",
        ),
    ]
    save_positions(path, positions)
    loaded = load_positions(path)
    assert loaded == positions
    os.unlink(path)


def test_add_update_delete():
    path = _tmpfile()
    position = Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    add_position(path, position)
    assert len(load_positions(path)) == 1

    updated = Position(code="000001", entry_date="20260101", cost_basis=11.0, strategy_ids=["b1"])
    update_position(path, 0, updated)
    loaded = load_positions(path)
    assert loaded[0].cost_basis == 11.0

    delete_position(path, 0)
    assert load_positions(path) == []
    os.unlink(path)


def test_forward_compat_missing_field():
    path = _tmpfile()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            [
                {
                    "code": "000001",
                    "entry_date": "20260101",
                    "cost_basis": 10.0,
                    "strategy_ids": ["b1"],
                }
            ],
            handle,
        )
    loaded = load_positions(path)
    assert len(loaded) == 1
    assert loaded[0].quantity is None
    assert loaded[0].notes == ""
    os.unlink(path)


def test_atomic_write_preserves_on_failure():
    path = _tmpfile()
    original = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=[])]
    save_positions(path, original)

    real_replace = os.replace

    def raise_replace(*args, **kwargs):
        raise OSError("simulated")

    os.replace = raise_replace
    try:
        try:
            save_positions(
                path,
                [Position(code="999999", entry_date="20260102", cost_basis=5.0, strategy_ids=[])],
            )
            assert False, "expected OSError"
        except OSError:
            pass
    finally:
        os.replace = real_replace

    loaded = load_positions(path)
    assert len(loaded) == 1
    assert loaded[0].code == "000001"
    os.unlink(path)


if __name__ == "__main__":
    test_missing_file_returns_empty()
    test_roundtrip()
    test_add_update_delete()
    test_forward_compat_missing_field()
    test_atomic_write_preserves_on_failure()
    print("All tests passed")
