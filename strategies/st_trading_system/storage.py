"""JSON persistence helpers for tracked positions."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import Position

_POSITION_FIELDS = {
    "code",
    "entry_date",
    "cost_basis",
    "strategy_ids",
    "quantity",
    "notes",
}
_REQUIRED_FIELDS = {"code", "entry_date", "cost_basis", "strategy_ids"}


def load_positions(path: str | Path) -> list[Position]:
    """Load positions from a JSON file.

    Missing files or malformed top-level payloads are treated as empty storage.
    Unknown fields are ignored so newer schema changes remain forward-compatible.
    """
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(raw, list):
        return []

    positions: list[Position] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kwargs = {key: value for key, value in item.items() if key in _POSITION_FIELDS}
        if not _REQUIRED_FIELDS.issubset(kwargs):
            continue
        positions.append(Position(**kwargs))
    return positions


def save_positions(path: str | Path, positions: list[Position]) -> None:
    """Atomically persist positions to JSON."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_name(f"{file_path.name}.tmp")
    payload = [asdict(position) for position in positions]

    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        os.replace(str(temp_path), str(file_path))
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def add_position(path: str | Path, position: Position) -> None:
    positions = load_positions(path)
    positions.append(position)
    save_positions(path, positions)


def update_position(path: str | Path, index: int, position: Position) -> None:
    positions = load_positions(path)
    if not 0 <= index < len(positions):
        raise IndexError(f"position index {index} out of range")
    positions[index] = position
    save_positions(path, positions)


def delete_position(path: str | Path, index: int) -> None:
    positions = load_positions(path)
    if not 0 <= index < len(positions):
        raise IndexError(f"position index {index} out of range")
    del positions[index]
    save_positions(path, positions)
