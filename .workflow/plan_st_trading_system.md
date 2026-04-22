# st_trading_system v1 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Single-agent execution — do not dispatch subagents.**

**Goal:** 把 `strategies/st_trading_system/` 从硬编码 4-Tab Streamlit 应用重构成"子策略可组合的选股 + 持仓破位监控"两 Tab 工具，支持在 Claude Code 里 vibe-code 扩展新子策略。

**Architecture:** 深模块切分 — `substrategies/` 和 `monitors/` 两个插件目录（自动发现），`screener.py` 做纯函数组合引擎，`positions.py` 做持仓监控，`storage.py` 做 JSON 持久化，`data_provider.py` 统一 OHLCV 数据接入（复用 `tools/data_adapter/local_csv.py`）。Streamlit UI 只是薄层。

**Tech Stack:** Python 3.13, pandas, numpy, streamlit, plotly。Python 标准库的 `json`、`importlib`、`pkgutil`、`dataclasses`。测试沿用 `strategies/st_b2/parity_test.py` 风格（`test_*` 函数 + `if __name__ == "__main__"` standalone runnable）。

**背景文档:** `.workflow/prd_st_trading_system.md` — 所有架构决策的依据，必要时回查。

---

## File Structure

### Create
```
strategies/st_trading_system/
├── models.py                  # dataclasses: Position, PositionStatus, ScreeningResult
├── base.py                    # abstract: BaseSubStrategy, BaseMonitor
├── storage.py                 # JSON I/O: load/save/add/update/delete positions
├── data_provider.py           # LocalCSVProvider wrapping tools/data_adapter/local_csv
├── registry.py                # auto-discovery for substrategies/ and monitors/
├── screener.py                # screen() pure function
├── positions.py               # monitor_positions() pure function
├── substrategies/
│   ├── __init__.py            # marker
│   ├── b1.py                  # B1 bundle
│   ├── danzhen20.py           # 单针探 20 bundle
│   └── zhuan.py               # 砖型图 bundle
├── monitors/
│   ├── __init__.py            # marker
│   └── close_below_bbi.py     # close<BBI monitor
├── test_models.py
├── test_storage.py
├── test_data_provider.py
├── test_substrategies.py
├── test_monitors.py
├── test_registry.py
├── test_screener.py
└── test_positions.py
```

### Modify
- `strategies/st_trading_system/config.py` — 删除 `KB_ZET_DIR` / `KB_MOBIUS_DIR`，新增 `PORTFOLIO_PATH`
- `strategies/st_trading_system/app.py` — 完全重写为 2-Tab UI
- `strategies/st_trading_system/requirements.txt` — 去掉 `chardet`
- `tools/data_adapter/local_csv.py` — 给 `get_stock_list` 加 `include_growth_boards` 参数
- `.gitignore` — 新增 `strategies/st_trading_system/portfolio.json`

### Delete
- `strategies/st_trading_system/kb_reader.py`
- `strategies/st_trading_system/scanner.py`
- `strategies/st_trading_system/signals.py`

---

## Testing Convention

所有测试文件在结尾有：
```python
if __name__ == "__main__":
    test_func_a()
    test_func_b()
    ...
    print("All tests passed")
```
验证命令一律是 `python <test_file_path>`，预期 exit code 0 + 最后一行 `All tests passed`。不依赖 pytest。

每个测试文件开头有以下 sys.path 注入块（和仓库里 `parity_test.py` 同风格）：

```python
import sys
from pathlib import Path
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
```

---

## Task 1: 创建 models.py + 测试

**Files:**
- Create: `strategies/st_trading_system/models.py`
- Create: `strategies/st_trading_system/test_models.py`

- [ ] **Step 1.1: 写 test_models.py**

Create `strategies/st_trading_system/test_models.py`:

```python
"""Tests for models module — dataclass shapes and defaults."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategies.st_trading_system.models import (
    Position,
    PositionStatus,
    ScreeningResult,
)


def test_position_required_fields():
    p = Position(
        code="000001",
        entry_date="20260101",
        cost_basis=10.0,
        strategy_ids=["b1"],
    )
    assert p.code == "000001"
    assert p.entry_date == "20260101"
    assert p.cost_basis == 10.0
    assert p.strategy_ids == ["b1"]
    assert p.quantity is None
    assert p.notes == ""


def test_position_optional_fields():
    p = Position(
        code="000001",
        entry_date="20260101",
        cost_basis=10.0,
        strategy_ids=["b1"],
        quantity=100.0,
        notes="test",
    )
    assert p.quantity == 100.0
    assert p.notes == "test"


def test_position_status_defaults():
    s = PositionStatus(
        code="000001",
        current_price=12.0,
        pnl_pct=0.2,
    )
    assert s.pnl_abs is None
    assert s.alerts == []
    assert s.status == "ok"


def test_position_status_alert():
    s = PositionStatus(
        code="000001",
        current_price=9.0,
        pnl_pct=-0.1,
        alerts=[("close_below_bbi", "close=9.0 < bbi=10.0")],
        status="alert",
    )
    assert s.status == "alert"
    assert len(s.alerts) == 1


def test_screening_result_basic():
    r = ScreeningResult(
        code="000001",
        close=10.5,
        hit_ids=["b1", "danzhen20"],
        hit_count=2,
        indicators_snapshot={"bbi": 10.0, "short_stoch": 15.0},
    )
    assert r.code == "000001"
    assert r.hit_count == 2
    assert r.indicators_snapshot["bbi"] == 10.0


if __name__ == "__main__":
    test_position_required_fields()
    test_position_optional_fields()
    test_position_status_defaults()
    test_position_status_alert()
    test_screening_result_basic()
    print("All tests passed")
```

- [ ] **Step 1.2: 运行测试确认它 fail**

```bash
python strategies/st_trading_system/test_models.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.models'`

- [ ] **Step 1.3: 实现 models.py**

Create `strategies/st_trading_system/models.py`:

```python
"""Dataclasses for the trading system: Position, PositionStatus, ScreeningResult."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Position:
    """A user-held position, persisted in portfolio.json."""

    code: str
    entry_date: str  # YYYYMMDD
    cost_basis: float
    strategy_ids: list[str]
    quantity: float | None = None
    notes: str = ""


@dataclass
class PositionStatus:
    """Computed status for a position — not persisted."""

    code: str
    current_price: float
    pnl_pct: float
    pnl_abs: float | None = None
    alerts: list[tuple[str, str]] = field(default_factory=list)
    status: Literal["ok", "alert", "unmonitored"] = "ok"


@dataclass
class ScreeningResult:
    """One row in the screener output table."""

    code: str
    close: float
    hit_ids: list[str]
    hit_count: int
    indicators_snapshot: dict
```

- [ ] **Step 1.4: 运行测试确认 pass**

```bash
python strategies/st_trading_system/test_models.py
```
Expected: `All tests passed`

- [ ] **Step 1.5: 提交**

```bash
git add strategies/st_trading_system/models.py strategies/st_trading_system/test_models.py
git commit -m "feat(st_trading_system): add models.py with Position/PositionStatus/ScreeningResult dataclasses"
```

---

## Task 2: 创建 base.py + 测试

**Files:**
- Create: `strategies/st_trading_system/base.py`
- Create: `strategies/st_trading_system/test_base.py`

- [ ] **Step 2.1: 写 test_base.py**

Create `strategies/st_trading_system/test_base.py`:

```python
"""Tests for base abstract classes — contract enforcement."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.base import BaseSubStrategy, BaseMonitor
from strategies.st_trading_system.models import Position


def test_substrategy_subclass_inherits_defaults():
    class MyStrat(BaseSubStrategy):
        id = "mine"
        name = "Mine"
        description = "desc"
        tags = ["test"]
        min_rows = 5

        def evaluate(self, df):
            return True, {"close": 1.0}

    s = MyStrat()
    assert s.id == "mine"
    assert s.exit_monitor_id is None  # default


def test_substrategy_evaluate_contract():
    class MyStrat(BaseSubStrategy):
        id = "mine"
        name = "Mine"
        description = "desc"
        tags = []
        min_rows = 1

        def evaluate(self, df):
            return True, {"close": float(df["close"].iloc[-1])}

    df = pd.DataFrame({"close": [10.0]})
    triggered, snap = MyStrat().evaluate(df)
    assert triggered is True
    assert snap == {"close": 10.0}


def test_monitor_subclass():
    class MyMonitor(BaseMonitor):
        id = "my_monitor"
        description = "test"

        def check(self, df, position):
            return True, "triggered"

    m = MyMonitor()
    df = pd.DataFrame({"close": [10.0]})
    pos = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=[])
    alert, reason = m.check(df, pos)
    assert alert is True
    assert reason == "triggered"


if __name__ == "__main__":
    test_substrategy_subclass_inherits_defaults()
    test_substrategy_evaluate_contract()
    test_monitor_subclass()
    print("All tests passed")
```

- [ ] **Step 2.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_base.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.base'`

- [ ] **Step 2.3: 实现 base.py**

Create `strategies/st_trading_system/base.py`:

```python
"""Abstract base classes for substrategies and monitors.

Vibe-code workflow: drop a new file in substrategies/ or monitors/ with a
subclass; the registry picks it up on next import.
"""

from __future__ import annotations

import pandas as pd

from .models import Position


class BaseSubStrategy:
    """Base class for entry signal substrategies.

    Subclasses must define class attributes `id`, `name`, `description`, `tags`,
    `min_rows`. Optionally override `exit_monitor_id` (default None = no monitor).
    Must implement `evaluate(self, df) -> (triggered: bool, snapshot: dict)`.
    """

    id: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] = []
    min_rows: int = 10
    exit_monitor_id: str | None = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        raise NotImplementedError


class BaseMonitor:
    """Base class for position exit-condition monitors.

    Subclasses must define class attributes `id`, `description`.
    Must implement `check(self, df, position) -> (alert: bool, reason: str)`.
    """

    id: str = ""
    description: str = ""

    def check(self, df: pd.DataFrame, position: Position) -> tuple[bool, str]:
        raise NotImplementedError
```

- [ ] **Step 2.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_base.py
```
Expected: `All tests passed`

- [ ] **Step 2.5: 提交**

```bash
git add strategies/st_trading_system/base.py strategies/st_trading_system/test_base.py
git commit -m "feat(st_trading_system): add BaseSubStrategy and BaseMonitor abstract classes"
```

---

## Task 3: 创建 storage.py + 测试

**Files:**
- Create: `strategies/st_trading_system/storage.py`
- Create: `strategies/st_trading_system/test_storage.py`

- [ ] **Step 3.1: 写 test_storage.py**

Create `strategies/st_trading_system/test_storage.py`:

```python
"""Tests for storage module — JSON I/O and atomic write."""

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
    load_positions,
    save_positions,
    add_position,
    update_position,
    delete_position,
)


def _tmpfile():
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    f.close()
    os.unlink(f.name)  # ensure non-existent
    return f.name


def test_missing_file_returns_empty():
    path = _tmpfile()
    assert load_positions(path) == []


def test_roundtrip():
    path = _tmpfile()
    positions = [
        Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"]),
        Position(code="600000", entry_date="20260102", cost_basis=20.0, strategy_ids=["b1", "danzhen20"], quantity=100.0, notes="n"),
    ]
    save_positions(path, positions)
    loaded = load_positions(path)
    assert loaded == positions
    os.unlink(path)


def test_add_update_delete():
    path = _tmpfile()
    p = Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    add_position(path, p)
    assert len(load_positions(path)) == 1

    p2 = Position(code="000001", entry_date="20260101", cost_basis=11.0, strategy_ids=["b1"])
    update_position(path, 0, p2)
    loaded = load_positions(path)
    assert loaded[0].cost_basis == 11.0

    delete_position(path, 0)
    assert load_positions(path) == []
    os.unlink(path)


def test_forward_compat_missing_field():
    """load_positions tolerates JSON missing newer optional fields."""
    path = _tmpfile()
    # Old-format JSON without `quantity` or `notes`
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{
            "code": "000001",
            "entry_date": "20260101",
            "cost_basis": 10.0,
            "strategy_ids": ["b1"],
        }], f)
    loaded = load_positions(path)
    assert len(loaded) == 1
    assert loaded[0].quantity is None
    assert loaded[0].notes == ""
    os.unlink(path)


def test_atomic_write_preserves_on_failure(monkeypatch_os_replace=None):
    """If os.replace raises, original file stays intact."""
    import builtins
    path = _tmpfile()
    # Write an initial "good" file
    original = [Position(code="000001", entry_date="20260101", cost_basis=10.0, strategy_ids=[])]
    save_positions(path, original)

    # Monkeypatch os.replace to raise
    real_replace = os.replace
    def raise_replace(*a, **k):
        raise OSError("simulated")

    os.replace = raise_replace
    try:
        try:
            save_positions(path, [Position(code="999", entry_date="20260102", cost_basis=5.0, strategy_ids=[])])
            assert False, "expected OSError"
        except OSError:
            pass
    finally:
        os.replace = real_replace

    # Original file should still be intact
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
```

- [ ] **Step 3.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_storage.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.storage'`

- [ ] **Step 3.3: 实现 storage.py**

Create `strategies/st_trading_system/storage.py`:

```python
"""Position persistence via JSON with atomic writes.

Storage schema: a list of Position dicts at the top level.
Unknown fields are ignored on load; missing optional fields get dataclass defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import Position


_POSITION_FIELDS = {"code", "entry_date", "cost_basis", "strategy_ids", "quantity", "notes"}


def load_positions(path: str) -> list[Position]:
    """Load positions from JSON file. Returns [] if file does not exist."""
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        return []

    positions = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # Take only known fields to tolerate schema drift
        kwargs = {k: v for k, v in item.items() if k in _POSITION_FIELDS}
        # Required fields check
        required = {"code", "entry_date", "cost_basis", "strategy_ids"}
        if not required.issubset(kwargs.keys()):
            continue
        positions.append(Position(**kwargs))

    return positions


def save_positions(path: str, positions: list[Position]) -> None:
    """Atomically write positions to JSON. Original file preserved on write failure."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in positions], f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def add_position(path: str, position: Position) -> None:
    positions = load_positions(path)
    positions.append(position)
    save_positions(path, positions)


def update_position(path: str, index: int, position: Position) -> None:
    positions = load_positions(path)
    if not (0 <= index < len(positions)):
        raise IndexError(f"position index {index} out of range (0, {len(positions)})")
    positions[index] = position
    save_positions(path, positions)


def delete_position(path: str, index: int) -> None:
    positions = load_positions(path)
    if not (0 <= index < len(positions)):
        raise IndexError(f"position index {index} out of range (0, {len(positions)})")
    del positions[index]
    save_positions(path, positions)
```

- [ ] **Step 3.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_storage.py
```
Expected: `All tests passed`

- [ ] **Step 3.5: 提交**

```bash
git add strategies/st_trading_system/storage.py strategies/st_trading_system/test_storage.py
git commit -m "feat(st_trading_system): add storage.py with atomic JSON persistence for positions"
```

---

## Task 4: 扩展 `tools/data_adapter/local_csv.py` 支持 growth boards 切换

**Files:**
- Modify: `tools/data_adapter/local_csv.py`

背景：`get_stock_list` 目前硬编码只返回主板（前缀 `000/001/002/600/601/603/605`），排除了 `300/688/689`。PRD 要求 UI 可切换"含创业板/科创板"。扩展该函数，加 `include_growth_boards: bool = False` 参数。

- [ ] **Step 4.1: 读当前实现**

```bash
cat tools/data_adapter/local_csv.py | head -50
```
Expected: 看到 `get_stock_list(data_dir: str) -> list[str]` 签名和内部 `is_main_board` 过滤。

- [ ] **Step 4.2: 修改 `get_stock_list` 签名**

Edit `tools/data_adapter/local_csv.py`. 把 `get_stock_list` 函数替换为：

```python
def get_stock_list(data_dir: str, include_growth_boards: bool = False) -> list[str]:
    """Scan data_dir for CSV files and return A-share stock codes.

    Args:
        data_dir: Path to directory containing <code>.csv files.
        include_growth_boards: If True, also include 创业板 (300) and 科创板
            (688/689). Default False = main board only.

    Returns:
        Sorted list of stock code strings.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    codes = []
    for csv_file in data_path.glob("*.csv"):
        code = csv_file.stem
        if is_main_board(code):
            codes.append(code)
        elif include_growth_boards and code.startswith(("300", "688", "689")):
            codes.append(code)
    return sorted(codes)
```

- [ ] **Step 4.3: 调用方不变——默认参数向后兼容**

`get_stock_list(data_dir)` 保持旧行为。无需修改其他调用点。

- [ ] **Step 4.4: 手动验证**

```bash
python -c "from tools.data_adapter.local_csv import get_stock_list; print('main only:', len(get_stock_list('D:/Git/QuanToolkit/data'))); print('with growth:', len(get_stock_list('D:/Git/QuanToolkit/data', include_growth_boards=True)))"
```
Expected: 两个计数，第二个严格大于第一个。如果数据目录不存在，会抛 FileNotFoundError —— OK，跳过这一步。

- [ ] **Step 4.5: 提交**

```bash
git add tools/data_adapter/local_csv.py
git commit -m "feat(data_adapter): add include_growth_boards flag to get_stock_list"
```

---

## Task 5: 创建 data_provider.py + 测试

**Files:**
- Create: `strategies/st_trading_system/data_provider.py`
- Create: `strategies/st_trading_system/test_data_provider.py`

- [ ] **Step 5.1: 写 test_data_provider.py**

Create `strategies/st_trading_system/test_data_provider.py`:

```python
"""Tests for LocalCSVProvider — reads real CSV files under a tempdir."""

import os
import sys
import tempfile
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.data_provider import LocalCSVProvider


def _write_csv(dir_: str, code: str, rows: int = 30):
    """Write a minimal OHLCV CSV to dir/<code>.csv."""
    dates = pd.date_range("2026-01-01", periods=rows).strftime("%Y-%m-%d")
    df = pd.DataFrame({
        "date": dates,
        "open": [10.0] * rows,
        "high": [11.0] * rows,
        "low": [9.0] * rows,
        "close": [10.5] * rows,
        "volume": [1000] * rows,
    })
    df.to_csv(os.path.join(dir_, f"{code}.csv"), index=False)


def test_get_history_returns_dataframe():
    with tempfile.TemporaryDirectory() as d:
        _write_csv(d, "000001")
        provider = LocalCSVProvider(d)
        df = provider.get_history("000001", end_date="20260131", days=30)
        assert df is not None
        assert len(df) > 0
        assert "close" in df.columns
        assert "trade_date" in df.columns


def test_get_history_missing_code_returns_none():
    with tempfile.TemporaryDirectory() as d:
        provider = LocalCSVProvider(d)
        df = provider.get_history("999999", end_date="20260101", days=10)
        assert df is None


def test_get_history_respects_end_date():
    with tempfile.TemporaryDirectory() as d:
        _write_csv(d, "000001", rows=30)
        provider = LocalCSVProvider(d)
        df = provider.get_history("000001", end_date="20260110", days=100)
        assert df is not None
        # 20260110 is the 10th day, so rows <= 10
        assert len(df) <= 10
        assert df["trade_date"].iloc[-1] <= "20260110"


def test_get_latest():
    with tempfile.TemporaryDirectory() as d:
        _write_csv(d, "000001", rows=30)
        provider = LocalCSVProvider(d)
        df = provider.get_latest("000001")
        assert df is not None
        assert len(df) > 0


if __name__ == "__main__":
    test_get_history_returns_dataframe()
    test_get_history_missing_code_returns_none()
    test_get_history_respects_end_date()
    test_get_latest()
    print("All tests passed")
```

- [ ] **Step 5.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_data_provider.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.data_provider'`

- [ ] **Step 5.3: 实现 data_provider.py**

Create `strategies/st_trading_system/data_provider.py`:

```python
"""Data provider interface + LocalCSVProvider implementation.

The Provider abstraction is kept minimal on purpose: adding a live-data
backend (tushare / akshare / xtQMT) later means implementing the same two
methods on a new class. Callers of screener.py / positions.py take a
provider as a parameter — never import one directly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


_NUMERIC_COLS = ("open", "high", "low", "close", "vol")
_REQUIRED_COLS = {"trade_date", "open", "high", "low", "close", "vol"}


class LocalCSVProvider:
    """OHLCV provider backed by directory of <code>.csv files."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def _load(self, code: str) -> pd.DataFrame | None:
        csv_path = self.data_dir / f"{code}.csv"
        if not csv_path.exists():
            return None
        try:
            df = pd.read_csv(csv_path, dtype={"date": str})
        except Exception:
            return None
        if df.empty:
            return None

        if "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})
        if "volume" in df.columns:
            df = df.rename(columns={"volume": "vol"})

        if df["trade_date"].dtype == object:
            df["trade_date"] = df["trade_date"].str.replace("-", "")

        if not _REQUIRED_COLS.issubset(df.columns):
            return None

        df = df.sort_values("trade_date").reset_index(drop=True)
        for col in _NUMERIC_COLS:
            df[col] = df[col].astype("float32")
        return df

    def get_history(self, code: str, end_date: str, days: int = 250) -> pd.DataFrame | None:
        """Return rows with trade_date <= end_date, last `days` entries.

        Returns None if CSV is missing, empty, or malformed.
        """
        df = self._load(code)
        if df is None:
            return None
        df = df[df["trade_date"] <= end_date]
        if df.empty:
            return None
        return df.tail(days).reset_index(drop=True)

    def get_latest(self, code: str, days: int = 250) -> pd.DataFrame | None:
        """Return the most recent `days` rows available (no end_date cap)."""
        df = self._load(code)
        if df is None:
            return None
        return df.tail(days).reset_index(drop=True)
```

- [ ] **Step 5.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_data_provider.py
```
Expected: `All tests passed`

- [ ] **Step 5.5: 提交**

```bash
git add strategies/st_trading_system/data_provider.py strategies/st_trading_system/test_data_provider.py
git commit -m "feat(st_trading_system): add LocalCSVProvider wrapping local CSV OHLCV files"
```

---

## Task 6: 创建 substrategies/ 包骨架 + B1 + 初步测试

**Files:**
- Create: `strategies/st_trading_system/substrategies/__init__.py`
- Create: `strategies/st_trading_system/substrategies/b1.py`
- Create: `strategies/st_trading_system/test_substrategies.py` (b1 only first)

- [ ] **Step 6.1: 创建 substrategies 包标记文件**

Create `strategies/st_trading_system/substrategies/__init__.py`:

```python
"""Substrategy package. Files are auto-discovered by registry.py.

To add a new substrategy: drop a .py file here that defines a subclass of
BaseSubStrategy. Restart Streamlit to pick it up.
"""
```

- [ ] **Step 6.2: 写 test_substrategies.py 的 B1 测试**

Create `strategies/st_trading_system/test_substrategies.py`:

```python
"""Tests for the 3 v1 bundle substrategies: B1, Danzhen20, Zhuan."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd


def _make_df(opens, highs, lows, closes, vols=None):
    """Build an OHLCV DataFrame. All inputs are equal-length lists."""
    n = len(closes)
    if vols is None:
        vols = [1000.0] * n
    dates = [f"202601{i+1:02d}" for i in range(n)]
    return pd.DataFrame({
        "trade_date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "vol": vols,
    })


# ---------------- B1 ----------------

def test_b1_triggers_on_rising_close_with_large_body():
    from strategies.st_trading_system.substrategies.b1 import B1

    # 24 flat bars, then 4 rising bars; last bar has body > 3%.
    closes = [10.0] * 20 + [10.5, 10.5, 10.5, 11.0]
    opens = [10.0] * 20 + [10.5, 10.5, 10.5, 10.5]  # last bar body = 0.5 / 11 ≈ 4.5%
    highs = [o + 0.2 for o in opens]
    lows = [min(o, c) - 0.2 for o, c in zip(opens, closes)]

    df = _make_df(opens, highs, lows, closes)
    triggered, snap = B1().evaluate(df)
    assert triggered is True, f"Expected B1 to trigger, snap={snap}"
    assert "close" in snap
    assert "bbi" in snap


def test_b1_rejects_close_below_bbi():
    from strategies.st_trading_system.substrategies.b1 import B1
    # 24 bars flat at 10, last bar drops to 9 (below BBI)
    closes = [10.0] * 23 + [9.0]
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = B1().evaluate(df)
    assert triggered is False


def test_b1_rejects_short_data():
    from strategies.st_trading_system.substrategies.b1 import B1
    closes = [10.0, 11.0, 12.0]
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = B1().evaluate(df)
    assert triggered is False


if __name__ == "__main__":
    test_b1_triggers_on_rising_close_with_large_body()
    test_b1_rejects_close_below_bbi()
    test_b1_rejects_short_data()
    print("All tests passed")
```

- [ ] **Step 6.3: 运行确认 fail**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.substrategies.b1'`

- [ ] **Step 6.4: 实现 b1.py**

Create `strategies/st_trading_system/substrategies/b1.py`:

```python
"""B1 candidate-pool substrategy.

Migrated from the original scan_b1 in signals.py. Conditions on the latest bar:
  1. close > BBI
  2. white_line is rising (white_line[-1] > white_line[-2])
  3. At least one bar in last 4 has |open - close| / close > 0.03

B1 is a candidate pool — requires manual secondary confirmation.
"""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_bbi, calc_white_line


class B1(BaseSubStrategy):
    id = "b1"
    name = "B1 候选池"
    description = "BBI 之上 + 白线上行 + 近 4 根有大阳"
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
        wl = df["white_line"]

        if pd.isna(bbi) or pd.isna(wl.iloc[-1]) or pd.isna(wl.iloc[-2]):
            return False, {}

        # Condition 1
        if close <= float(bbi):
            return False, {}
        # Condition 2
        if float(wl.iloc[-1]) <= float(wl.iloc[-2]):
            return False, {}
        # Condition 3
        recent_open = df["open"].iloc[-4:]
        recent_close = df["close"].iloc[-4:]
        body_ratio = (recent_open - recent_close).abs() / recent_close
        if float(body_ratio.max()) <= 0.03:
            return False, {}

        return True, {
            "close": close,
            "bbi": float(bbi),
            "white_line": float(wl.iloc[-1]),
        }
```

- [ ] **Step 6.5: 运行确认 pass**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `All tests passed`

如果 `test_b1_triggers_on_rising_close_with_large_body` 失败，在测试文件内调整 `closes`/`opens` 数值直到满足三个条件，再跑。

- [ ] **Step 6.6: 提交**

```bash
git add strategies/st_trading_system/substrategies/__init__.py strategies/st_trading_system/substrategies/b1.py strategies/st_trading_system/test_substrategies.py
git commit -m "feat(st_trading_system): migrate B1 substrategy to substrategies/b1.py"
```

---

## Task 7: 添加 Danzhen20 substrategy + 测试

**Files:**
- Create: `strategies/st_trading_system/substrategies/danzhen20.py`
- Modify: `strategies/st_trading_system/test_substrategies.py`

- [ ] **Step 7.1: 追加 danzhen20 测试**

Append to `strategies/st_trading_system/test_substrategies.py`, 在 B1 测试块之后加：

```python
# ---------------- Danzhen20 ----------------

def test_danzhen20_triggers_when_short_low_long_high():
    from strategies.st_trading_system.substrategies.danzhen20 import Danzhen20
    # 21 bars. Highs=10, lows=5 for the first 18 (wide range).
    # Last 3 bars: high=9, low=8..9, close settles at 8 (near 3-bar low).
    highs = [10.0] * 18 + [9.0, 9.0, 9.0]
    lows = [5.0] * 18 + [9.0, 9.0, 8.0]
    closes = [7.5] * 18 + [9.0, 9.0, 8.0]
    opens = closes[:]
    df = _make_df(opens, highs, lows, closes)
    triggered, snap = Danzhen20().evaluate(df)
    assert triggered is True, f"expected trigger, snap={snap}"
    assert "short_stoch" in snap
    assert "long_stoch" in snap


def test_danzhen20_rejects_when_short_high():
    from strategies.st_trading_system.substrategies.danzhen20 import Danzhen20
    # close at top of 3-bar range → short_stoch high → reject
    highs = [10.0] * 18 + [9.0, 9.0, 10.0]
    lows = [5.0] * 18 + [9.0, 9.0, 9.0]
    closes = [7.5] * 18 + [9.0, 9.0, 10.0]
    opens = closes[:]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = Danzhen20().evaluate(df)
    assert triggered is False


def test_danzhen20_rejects_short_data():
    from strategies.st_trading_system.substrategies.danzhen20 import Danzhen20
    closes = [10.0] * 5
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = Danzhen20().evaluate(df)
    assert triggered is False
```

并在 `if __name__ == "__main__":` 下加：
```python
    test_danzhen20_triggers_when_short_low_long_high()
    test_danzhen20_rejects_when_short_high()
    test_danzhen20_rejects_short_data()
```

- [ ] **Step 7.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.substrategies.danzhen20'`

- [ ] **Step 7.3: 实现 danzhen20.py**

Create `strategies/st_trading_system/substrategies/danzhen20.py`:

```python
"""Danzhen20 (单针探 20) substrategy.

Migrated from scan_danzhen20. Conditions on latest bar:
  1. short_stoch <= 20
  2. long_stoch >= 60
"""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_long_stoch, calc_short_stoch


class Danzhen20(BaseSubStrategy):
    id = "danzhen20"
    name = "单针探 20"
    description = "短期 stoch≤20 且长期 stoch≥60 的反转信号"
    tags = ["entry", "bundle"]
    min_rows = 21
    exit_monitor_id = None  # v1 无监控器

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}

        df = calc_short_stoch(df)
        df = calc_long_stoch(df)

        short_val = df["short_stoch"].iloc[-1]
        long_val = df["long_stoch"].iloc[-1]

        if pd.isna(short_val) or pd.isna(long_val):
            return False, {}

        short_val = float(short_val)
        long_val = float(long_val)
        if not (short_val <= 20 and long_val >= 60):
            return False, {}

        return True, {
            "close": float(df["close"].iloc[-1]),
            "short_stoch": short_val,
            "long_stoch": long_val,
        }
```

- [ ] **Step 7.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `All tests passed`

如果 positive case 不触发，检查构造数据的 stoch 值并调整。

- [ ] **Step 7.5: 提交**

```bash
git add strategies/st_trading_system/substrategies/danzhen20.py strategies/st_trading_system/test_substrategies.py
git commit -m "feat(st_trading_system): migrate Danzhen20 substrategy"
```

---

## Task 8: 添加 Zhuan substrategy + 测试

**Files:**
- Create: `strategies/st_trading_system/substrategies/zhuan.py`
- Modify: `strategies/st_trading_system/test_substrategies.py`

- [ ] **Step 8.1: 追加 zhuan 测试**

Append to `test_substrategies.py`:

```python
# ---------------- Zhuan ----------------

def test_zhuan_rejects_flat_data():
    """Constant price cannot produce xg=True."""
    from strategies.st_trading_system.substrategies.zhuan import Zhuan
    closes = [10.0] * 30
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = Zhuan().evaluate(df)
    assert triggered is False


def test_zhuan_rejects_short_data():
    from strategies.st_trading_system.substrategies.zhuan import Zhuan
    closes = [10.0] * 5
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = Zhuan().evaluate(df)
    assert triggered is False


def test_zhuan_triggers_on_upswing_start():
    """Pattern: bars drifting down then one sharp up-bar should start an upswing."""
    from strategies.st_trading_system.substrategies.zhuan import Zhuan
    # 30 bars: slight downtrend then a sharp up-move on the last bar.
    closes = [10.0, 10.0, 9.9, 9.8, 9.7, 9.6, 9.5, 9.4, 9.3, 9.2,
              9.1, 9.0, 8.9, 8.8, 8.7, 8.6, 8.5, 8.4, 8.3, 8.2,
              8.1, 8.0, 7.9, 7.8, 7.7, 7.6, 7.5, 7.4, 7.3, 9.5]
    opens = closes[:]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    df = _make_df(opens, highs, lows, closes)
    triggered, _ = Zhuan().evaluate(df)
    # Note: if this assertion fails due to indicator math, adjust the jump value
    # on the last bar until the signal flips.
    assert triggered is True
```

并把这些加到 `__main__` 块：
```python
    test_zhuan_rejects_flat_data()
    test_zhuan_rejects_short_data()
    test_zhuan_triggers_on_upswing_start()
```

- [ ] **Step 8.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.substrategies.zhuan'`

- [ ] **Step 8.3: 实现 zhuan.py**

Create `strategies/st_trading_system/substrategies/zhuan.py`:

```python
"""Zhuan (砖型图) substrategy.

Migrated from scan_zhuan. Trigger: latest bar's xg flag is True (first bar
of a two-bar upswing in the brick chart indicator).
"""

from __future__ import annotations

import pandas as pd

from ..base import BaseSubStrategy
from ..indicators import calc_zhuan


class Zhuan(BaseSubStrategy):
    id = "zhuan"
    name = "砖型图"
    description = "砖型图 XG 两根上升起始信号"
    tags = ["entry", "bundle"]
    min_rows = 10
    exit_monitor_id = None

    def evaluate(self, df: pd.DataFrame) -> tuple[bool, dict]:
        if len(df) < self.min_rows:
            return False, {}
        df = calc_zhuan(df)
        xg = df["xg"].iloc[-1]
        if pd.isna(xg) or not bool(xg):
            return False, {}
        return True, {
            "close": float(df["close"].iloc[-1]),
            "signal_zhuan": float(df["signal_zhuan"].iloc[-1]),
        }
```

- [ ] **Step 8.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_substrategies.py
```
Expected: `All tests passed`

如果 `test_zhuan_triggers_on_upswing_start` 失败：
1. 临时打印 `df[['close', 'signal_zhuan', 'xg']].tail(5)` 看 signal 序列
2. 调整最后一根的 close 值（从 9.5 往上调）直到 `xg[-1] = True`
3. 再跑

- [ ] **Step 8.5: 提交**

```bash
git add strategies/st_trading_system/substrategies/zhuan.py strategies/st_trading_system/test_substrategies.py
git commit -m "feat(st_trading_system): migrate Zhuan substrategy"
```

---

## Task 9: 创建 monitors/ 包 + CloseBelowBBI + 测试

**Files:**
- Create: `strategies/st_trading_system/monitors/__init__.py`
- Create: `strategies/st_trading_system/monitors/close_below_bbi.py`
- Create: `strategies/st_trading_system/test_monitors.py`

- [ ] **Step 9.1: 创建 monitors 包标记**

Create `strategies/st_trading_system/monitors/__init__.py`:

```python
"""Monitor package. Files are auto-discovered by registry.py.

To add a new monitor: drop a .py file here defining a BaseMonitor subclass.
Restart Streamlit to pick it up.
"""
```

- [ ] **Step 9.2: 写 test_monitors.py**

Create `strategies/st_trading_system/test_monitors.py`:

```python
"""Tests for monitors."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.models import Position


def _make_df(closes):
    n = len(closes)
    dates = [f"202601{i+1:02d}" for i in range(n)]
    return pd.DataFrame({
        "trade_date": dates,
        "open": closes,
        "high": [c + 0.1 for c in closes],
        "low": [c - 0.1 for c in closes],
        "close": closes,
        "vol": [1000.0] * n,
    })


def test_close_below_bbi_no_alert_when_above():
    from strategies.st_trading_system.monitors.close_below_bbi import CloseBelowBBI
    # 24+ bars trending up → close ends above BBI.
    closes = [10.0] * 20 + [10.5, 11.0, 11.5, 12.0]
    df = _make_df(closes)
    pos = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    alert, reason = CloseBelowBBI().check(df, pos)
    assert alert is False


def test_close_below_bbi_alerts_when_below():
    from strategies.st_trading_system.monitors.close_below_bbi import CloseBelowBBI
    # 24+ bars ending with a sharp drop → close < BBI.
    closes = [10.0] * 20 + [10.0, 10.0, 10.0, 7.0]
    df = _make_df(closes)
    pos = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    alert, reason = CloseBelowBBI().check(df, pos)
    assert alert is True
    assert "bbi" in reason.lower() or "close" in reason.lower()


def test_close_below_bbi_insufficient_data_no_alert():
    from strategies.st_trading_system.monitors.close_below_bbi import CloseBelowBBI
    closes = [10.0] * 5
    df = _make_df(closes)
    pos = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["b1"])
    alert, _ = CloseBelowBBI().check(df, pos)
    assert alert is False


if __name__ == "__main__":
    test_close_below_bbi_no_alert_when_above()
    test_close_below_bbi_alerts_when_below()
    test_close_below_bbi_insufficient_data_no_alert()
    print("All tests passed")
```

- [ ] **Step 9.3: 运行确认 fail**

```bash
python strategies/st_trading_system/test_monitors.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.monitors.close_below_bbi'`

- [ ] **Step 9.4: 实现 close_below_bbi.py**

Create `strategies/st_trading_system/monitors/close_below_bbi.py`:

```python
"""CloseBelowBBI monitor — alerts when latest close drops below BBI."""

from __future__ import annotations

import pandas as pd

from ..base import BaseMonitor
from ..indicators import calc_bbi
from ..models import Position


class CloseBelowBBI(BaseMonitor):
    id = "close_below_bbi"
    description = "close < BBI 破位告警"

    def check(self, df: pd.DataFrame, position: Position) -> tuple[bool, str]:
        if len(df) < 24:
            return False, ""
        df = calc_bbi(df)
        close = float(df["close"].iloc[-1])
        bbi = df["bbi"].iloc[-1]
        if pd.isna(bbi):
            return False, ""
        bbi_val = float(bbi)
        if close < bbi_val:
            return True, f"close={close:.2f} < bbi={bbi_val:.2f}"
        return False, ""
```

- [ ] **Step 9.5: 运行确认 pass**

```bash
python strategies/st_trading_system/test_monitors.py
```
Expected: `All tests passed`

- [ ] **Step 9.6: 提交**

```bash
git add strategies/st_trading_system/monitors/__init__.py strategies/st_trading_system/monitors/close_below_bbi.py strategies/st_trading_system/test_monitors.py
git commit -m "feat(st_trading_system): add CloseBelowBBI exit monitor"
```

---

## Task 10: 创建 registry.py + 测试

**Files:**
- Create: `strategies/st_trading_system/registry.py`
- Create: `strategies/st_trading_system/test_registry.py`

- [ ] **Step 10.1: 写 test_registry.py**

Create `strategies/st_trading_system/test_registry.py`:

```python
"""Tests for registry discovery of substrategies and monitors."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def test_discovery_finds_v1_substrategies():
    from strategies.st_trading_system.registry import list_substrategies

    subs = list_substrategies()
    ids = {s.id for s in subs}
    assert "b1" in ids
    assert "danzhen20" in ids
    assert "zhuan" in ids


def test_discovery_finds_v1_monitors():
    from strategies.st_trading_system.registry import list_monitors

    monitors = list_monitors()
    ids = {m.id for m in monitors}
    assert "close_below_bbi" in ids


def test_get_substrategy_by_id():
    from strategies.st_trading_system.registry import get_substrategy

    b1 = get_substrategy("b1")
    assert b1 is not None
    assert b1.id == "b1"


def test_get_substrategy_missing_returns_none():
    from strategies.st_trading_system.registry import get_substrategy
    assert get_substrategy("nonexistent_id") is None


def test_get_monitor_by_id():
    from strategies.st_trading_system.registry import get_monitor

    m = get_monitor("close_below_bbi")
    assert m is not None
    assert m.id == "close_below_bbi"


def test_registry_errors_empty_on_clean_import():
    from strategies.st_trading_system.registry import registry_errors
    errors = registry_errors()
    # clean: all v1 modules should load
    for file, err in errors:
        print(f"UNEXPECTED: {file}: {err}")
    assert errors == []


if __name__ == "__main__":
    test_discovery_finds_v1_substrategies()
    test_discovery_finds_v1_monitors()
    test_get_substrategy_by_id()
    test_get_substrategy_missing_returns_none()
    test_get_monitor_by_id()
    test_registry_errors_empty_on_clean_import()
    print("All tests passed")
```

- [ ] **Step 10.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_registry.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.registry'`

- [ ] **Step 10.3: 实现 registry.py**

Create `strategies/st_trading_system/registry.py`:

```python
"""Auto-discovery registry for substrategies and monitors.

On first call to list_substrategies() / list_monitors(), walks the respective
package directory, imports each .py, and collects BaseSubStrategy /
BaseMonitor subclasses. Errors during import are captured in registry_errors()
so the UI can surface them without crashing the whole app.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TypeVar

from .base import BaseMonitor, BaseSubStrategy


_substrategies: dict[str, BaseSubStrategy] = {}
_monitors: dict[str, BaseMonitor] = {}
_errors: list[tuple[str, str]] = []
_loaded = False


T = TypeVar("T")


def _discover(package_module_name: str, base_cls: type[T], registry: dict[str, T]):
    """Import all submodules of package and collect base_cls subclasses."""
    try:
        pkg = importlib.import_module(package_module_name)
    except Exception as e:
        _errors.append((package_module_name, f"package import failed: {e}"))
        return

    for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        full_name = f"{package_module_name}.{modname}"
        try:
            mod = importlib.import_module(full_name)
        except Exception as e:
            _errors.append((full_name, f"module import failed: {e}"))
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not isinstance(attr, type):
                continue
            if not issubclass(attr, base_cls) or attr is base_cls:
                continue
            if not getattr(attr, "id", ""):
                continue
            try:
                instance = attr()
            except Exception as e:
                _errors.append((full_name, f"instantiation failed: {e}"))
                continue
            if instance.id in registry:
                _errors.append((full_name, f"duplicate id '{instance.id}' — keeping first"))
                continue
            registry[instance.id] = instance


def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    _discover("strategies.st_trading_system.substrategies", BaseSubStrategy, _substrategies)
    _discover("strategies.st_trading_system.monitors", BaseMonitor, _monitors)
    _loaded = True


def list_substrategies() -> list[BaseSubStrategy]:
    _ensure_loaded()
    return list(_substrategies.values())


def list_monitors() -> list[BaseMonitor]:
    _ensure_loaded()
    return list(_monitors.values())


def get_substrategy(sid: str) -> BaseSubStrategy | None:
    _ensure_loaded()
    return _substrategies.get(sid)


def get_monitor(mid: str) -> BaseMonitor | None:
    _ensure_loaded()
    return _monitors.get(mid)


def registry_errors() -> list[tuple[str, str]]:
    _ensure_loaded()
    return list(_errors)
```

- [ ] **Step 10.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_registry.py
```
Expected: `All tests passed`

- [ ] **Step 10.5: 提交**

```bash
git add strategies/st_trading_system/registry.py strategies/st_trading_system/test_registry.py
git commit -m "feat(st_trading_system): add registry with auto-discovery for substrategies/monitors"
```

---

## Task 11: 创建 screener.py + 测试

**Files:**
- Create: `strategies/st_trading_system/screener.py`
- Create: `strategies/st_trading_system/test_screener.py`

- [ ] **Step 11.1: 写 test_screener.py**

Create `strategies/st_trading_system/test_screener.py`:

```python
"""Tests for screen() function — AND/OR semantics, hit_ids, caching, bad data."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.base import BaseSubStrategy
from strategies.st_trading_system.screener import screen


# ---- Fakes ----

class _FakeProvider:
    """In-memory provider: {code: df}."""

    def __init__(self, store: dict[str, pd.DataFrame]):
        self.store = store

    def get_history(self, code, end_date, days=250):
        df = self.store.get(code)
        if df is None:
            return None
        df = df[df["trade_date"] <= end_date]
        if df.empty:
            return None
        return df.tail(days).reset_index(drop=True)

    def get_latest(self, code, days=250):
        df = self.store.get(code)
        if df is None:
            return None
        return df.tail(days).reset_index(drop=True)


class _FakeSub(BaseSubStrategy):
    """Substrategy that triggers on stocks listed in `trigger_on`."""

    id = "fake"
    name = "Fake"
    description = "test only"
    tags = ["test"]
    min_rows = 1

    def __init__(self, sid, trigger_on):
        self.id = sid
        self.trigger_on = set(trigger_on)
        self.eval_calls = 0

    def evaluate(self, df):
        self.eval_calls += 1
        code = df.attrs.get("code", "")
        if code in self.trigger_on:
            return True, {"close": float(df["close"].iloc[-1])}
        return False, {}


def _make_df(code, closes):
    n = len(closes)
    df = pd.DataFrame({
        "trade_date": [f"202601{i+1:02d}" for i in range(n)],
        "open": closes,
        "high": [c + 0.1 for c in closes],
        "low": [c - 0.1 for c in closes],
        "close": closes,
        "vol": [1000.0] * n,
    })
    df.attrs["code"] = code
    return df


def _setup():
    store = {
        "A": _make_df("A", [10.0] * 15),
        "B": _make_df("B", [10.0] * 15),
        "C": _make_df("C", [10.0] * 15),
    }
    provider = _FakeProvider(store)
    s1 = _FakeSub("s1", trigger_on=["A", "B"])
    s2 = _FakeSub("s2", trigger_on=["B", "C"])
    return provider, s1, s2


def test_and_semantics():
    provider, s1, s2 = _setup()
    # Only B triggers both s1 and s2.
    results = screen(
        substrategy_ids=["s1", "s2"],
        mode="AND",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
    )
    codes = {r.code for r in results}
    assert codes == {"B"}, f"AND should return only B, got {codes}"


def test_or_semantics():
    provider, s1, s2 = _setup()
    results = screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
    )
    codes = {r.code for r in results}
    assert codes == {"A", "B", "C"}


def test_hit_ids_correct():
    provider, s1, s2 = _setup()
    results = screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
    )
    by_code = {r.code: r for r in results}
    assert set(by_code["A"].hit_ids) == {"s1"}
    assert set(by_code["B"].hit_ids) == {"s1", "s2"}
    assert set(by_code["C"].hit_ids) == {"s2"}
    assert by_code["B"].hit_count == 2


def test_empty_selection_returns_empty():
    provider, s1, s2 = _setup()
    results = screen(
        substrategy_ids=[],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
    )
    assert results == []


def test_missing_data_skipped():
    provider, s1, s2 = _setup()
    results = screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C", "MISSING"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
    )
    codes = {r.code for r in results}
    assert "MISSING" not in codes


def test_cache_reuses_evaluations():
    provider, s1, s2 = _setup()

    # First call: s1+s2 on A,B,C — each sub should run once per stock.
    screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
        cache={},  # start with empty cache
    )
    # 3 stocks × 2 subs = 6 evaluates total
    total_first = s1.eval_calls + s2.eval_calls
    assert total_first == 6, f"expected 6, got {total_first}"

    # Second call with an external cache persisted.
    cache = {}
    screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
        cache=cache,
    )
    s1.eval_calls = 0
    s2.eval_calls = 0
    screen(
        substrategy_ids=["s1", "s2"],
        mode="OR",
        universe=["A", "B", "C"],
        date="20260131",
        data_provider=provider,
        substrategies_override=[s1, s2],
        cache=cache,  # reused
    )
    total_second = s1.eval_calls + s2.eval_calls
    assert total_second == 0, f"expected 0 evals on cached rerun, got {total_second}"


if __name__ == "__main__":
    test_and_semantics()
    test_or_semantics()
    test_hit_ids_correct()
    test_empty_selection_returns_empty()
    test_missing_data_skipped()
    test_cache_reuses_evaluations()
    print("All tests passed")
```

- [ ] **Step 11.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_screener.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.screener'`

- [ ] **Step 11.3: 实现 screener.py**

Create `strategies/st_trading_system/screener.py`:

```python
"""Pure-function screening engine.

Given a list of substrategy ids + AND/OR mode + stock universe + date + a
data provider, returns ScreeningResult[]. Safe to call from Streamlit or CLI.

Caching: optional `cache` dict keyed by (code, sub_id, date) -> (hit, snapshot).
Callers can keep a long-lived cache across runs; screener will only call
substrategy.evaluate() when the key is missing.
"""

from __future__ import annotations

from typing import Literal

from .models import ScreeningResult
from .registry import get_substrategy


def screen(
    substrategy_ids: list[str],
    mode: Literal["AND", "OR"],
    universe: list[str],
    date: str,
    data_provider,
    substrategies_override: list | None = None,
    cache: dict | None = None,
) -> list[ScreeningResult]:
    """Run the screener.

    Args:
        substrategy_ids: which substrategies the user selected.
        mode: "AND" requires all selected to trigger; "OR" requires any.
        universe: list of stock codes to scan.
        date: scan date (YYYYMMDD). Data is truncated to trade_date <= date.
        data_provider: object with `get_history(code, end_date, days)` method.
        substrategies_override: optional list of BaseSubStrategy instances to
            use instead of the registry (for testing).
        cache: optional mutable dict shared across calls for evaluation reuse.

    Returns:
        List of ScreeningResult, one per matching stock.
    """
    if not substrategy_ids:
        return []

    if substrategies_override is not None:
        by_id = {s.id: s for s in substrategies_override}
    else:
        by_id = {}
        for sid in substrategy_ids:
            sub = get_substrategy(sid)
            if sub is not None:
                by_id[sid] = sub

    if cache is None:
        cache = {}

    selected_set = set(substrategy_ids)
    results: list[ScreeningResult] = []

    for code in universe:
        df = data_provider.get_history(code, end_date=date, days=250)
        if df is None or len(df) < 10:
            continue

        hits: list[str] = []
        snapshot: dict = {}

        for sid in substrategy_ids:
            sub = by_id.get(sid)
            if sub is None:
                continue

            key = (code, sid, date)
            if key in cache:
                triggered, snap = cache[key]
            else:
                if len(df) < sub.min_rows:
                    triggered, snap = False, {}
                else:
                    try:
                        triggered, snap = sub.evaluate(df)
                    except Exception:
                        triggered, snap = False, {}
                cache[key] = (triggered, snap)

            if triggered:
                hits.append(sid)
                snapshot.update(snap)

        if not hits:
            continue
        if mode == "AND" and set(hits) != selected_set:
            continue

        results.append(ScreeningResult(
            code=code,
            close=float(df["close"].iloc[-1]),
            hit_ids=hits,
            hit_count=len(hits),
            indicators_snapshot=snapshot,
        ))

    return results
```

- [ ] **Step 11.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_screener.py
```
Expected: `All tests passed`

- [ ] **Step 11.5: 提交**

```bash
git add strategies/st_trading_system/screener.py strategies/st_trading_system/test_screener.py
git commit -m "feat(st_trading_system): add screener.py with AND/OR composition and per-call cache"
```

---

## Task 12: 创建 positions.py + 测试

**Files:**
- Create: `strategies/st_trading_system/positions.py`
- Create: `strategies/st_trading_system/test_positions.py`

- [ ] **Step 12.1: 写 test_positions.py**

Create `strategies/st_trading_system/test_positions.py`:

```python
"""Tests for monitor_positions()."""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from strategies.st_trading_system.base import BaseMonitor, BaseSubStrategy
from strategies.st_trading_system.models import Position
from strategies.st_trading_system.positions import monitor_positions


class _FakeProvider:
    def __init__(self, store):
        self.store = store

    def get_latest(self, code, days=250):
        return self.store.get(code)

    def get_history(self, code, end_date, days=250):
        return self.store.get(code)


def _make_df(closes):
    n = len(closes)
    return pd.DataFrame({
        "trade_date": [f"202601{i+1:02d}" for i in range(n)],
        "open": closes,
        "high": [c + 0.1 for c in closes],
        "low": [c - 0.1 for c in closes],
        "close": closes,
        "vol": [1000.0] * n,
    })


class _AlwaysAlertMonitor(BaseMonitor):
    id = "always_alert"
    description = "test monitor that always alerts"

    def check(self, df, position):
        return True, "always"


class _NeverAlertMonitor(BaseMonitor):
    id = "never_alert"
    description = "test monitor that never alerts"

    def check(self, df, position):
        return False, ""


class _StubSub(BaseSubStrategy):
    id = ""
    name = "stub"
    description = ""
    tags = []
    min_rows = 1

    def __init__(self, sid, exit_monitor_id=None):
        self.id = sid
        self.exit_monitor_id = exit_monitor_id

    def evaluate(self, df):
        return False, {}


def test_ok_when_all_monitors_clear():
    provider = _FakeProvider({"X": _make_df([10.0] * 25)})
    positions = [Position(code="X", entry_date="20260101", cost_basis=9.0, strategy_ids=["s1"])]
    sub = _StubSub("s1", exit_monitor_id="never_alert")
    statuses = monitor_positions(
        positions,
        data_provider=provider,
        today="20260125",
        substrategies_override=[sub],
        monitors_override=[_NeverAlertMonitor()],
    )
    assert len(statuses) == 1
    s = statuses[0]
    assert s.status == "ok"
    assert s.alerts == []
    assert s.pnl_pct > 0


def test_alert_when_monitor_triggers():
    provider = _FakeProvider({"X": _make_df([10.0] * 25)})
    positions = [Position(code="X", entry_date="20260101", cost_basis=9.0, strategy_ids=["s1"])]
    sub = _StubSub("s1", exit_monitor_id="always_alert")
    statuses = monitor_positions(
        positions,
        data_provider=provider,
        today="20260125",
        substrategies_override=[sub],
        monitors_override=[_AlwaysAlertMonitor()],
    )
    s = statuses[0]
    assert s.status == "alert"
    assert len(s.alerts) == 1
    assert s.alerts[0][0] == "always_alert"


def test_unmonitored_when_no_exit_monitor():
    provider = _FakeProvider({"X": _make_df([10.0] * 25)})
    positions = [Position(code="X", entry_date="20260101", cost_basis=9.0, strategy_ids=["s1"])]
    sub = _StubSub("s1", exit_monitor_id=None)
    statuses = monitor_positions(
        positions,
        data_provider=provider,
        today="20260125",
        substrategies_override=[sub],
        monitors_override=[],
    )
    s = statuses[0]
    assert s.status == "unmonitored"
    assert s.alerts == []


def test_or_across_multiple_strategies():
    provider = _FakeProvider({"X": _make_df([10.0] * 25)})
    positions = [Position(code="X", entry_date="20260101", cost_basis=9.0, strategy_ids=["s1", "s2"])]
    sub1 = _StubSub("s1", exit_monitor_id="never_alert")
    sub2 = _StubSub("s2", exit_monitor_id="always_alert")
    statuses = monitor_positions(
        positions,
        data_provider=provider,
        today="20260125",
        substrategies_override=[sub1, sub2],
        monitors_override=[_AlwaysAlertMonitor(), _NeverAlertMonitor()],
    )
    s = statuses[0]
    assert s.status == "alert"
    # OR: any trigger suffices
    assert len(s.alerts) == 1


def test_pnl_pct_correct():
    provider = _FakeProvider({"X": _make_df([10.0] * 24 + [12.0])})  # current close 12
    positions = [Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["s1"])]
    sub = _StubSub("s1", exit_monitor_id=None)
    statuses = monitor_positions(
        positions, provider, "20260125", substrategies_override=[sub], monitors_override=[],
    )
    assert abs(statuses[0].pnl_pct - 0.2) < 1e-6


def test_pnl_abs_only_when_quantity():
    provider = _FakeProvider({"X": _make_df([10.0] * 24 + [12.0])})
    # without quantity
    p1 = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["s1"])
    # with quantity
    p2 = Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["s1"], quantity=100.0)
    sub = _StubSub("s1", exit_monitor_id=None)
    statuses = monitor_positions(
        [p1, p2], provider, "20260125", substrategies_override=[sub], monitors_override=[],
    )
    assert statuses[0].pnl_abs is None
    assert abs(statuses[1].pnl_abs - 200.0) < 1e-6


def test_missing_data_returns_zero_status():
    provider = _FakeProvider({})  # no data for X
    positions = [Position(code="X", entry_date="20260101", cost_basis=10.0, strategy_ids=["s1"])]
    sub = _StubSub("s1", exit_monitor_id=None)
    statuses = monitor_positions(
        positions, provider, "20260125", substrategies_override=[sub], monitors_override=[],
    )
    s = statuses[0]
    assert s.current_price == 0.0
    assert s.status == "unmonitored"


if __name__ == "__main__":
    test_ok_when_all_monitors_clear()
    test_alert_when_monitor_triggers()
    test_unmonitored_when_no_exit_monitor()
    test_or_across_multiple_strategies()
    test_pnl_pct_correct()
    test_pnl_abs_only_when_quantity()
    test_missing_data_returns_zero_status()
    print("All tests passed")
```

- [ ] **Step 12.2: 运行确认 fail**

```bash
python strategies/st_trading_system/test_positions.py
```
Expected: `ModuleNotFoundError: No module named 'strategies.st_trading_system.positions'`

- [ ] **Step 12.3: 实现 positions.py**

Create `strategies/st_trading_system/positions.py`:

```python
"""Position monitoring engine — computes PositionStatus for each user holding.

For each position, looks up the exit_monitor_id of each bound substrategy,
runs all associated monitors against today's data frame. Any trigger (OR)
flips the status to "alert". If no strategy has an exit_monitor_id, status
is "unmonitored". PnL is always computed (percent always; absolute only
when quantity is set).
"""

from __future__ import annotations

from .models import Position, PositionStatus
from .registry import get_monitor, get_substrategy


def _resolve(ids: list[str], override: list | None) -> dict:
    if override is None:
        return {}
    return {obj.id: obj for obj in override}


def monitor_positions(
    positions: list[Position],
    data_provider,
    today: str,
    substrategies_override: list | None = None,
    monitors_override: list | None = None,
) -> list[PositionStatus]:
    """Compute status for each position.

    Args:
        positions: user-held positions.
        data_provider: object with `get_latest(code, days)` method.
        today: scan date stamp (informational; used only if provider needs it).
        substrategies_override / monitors_override: for testing — bypass registry.

    Returns:
        PositionStatus per position, same order as input.
    """
    sub_by_id = _resolve([s for p in positions for s in p.strategy_ids], substrategies_override)
    mon_by_id = _resolve([], monitors_override)

    results: list[PositionStatus] = []

    for pos in positions:
        df = data_provider.get_latest(pos.code, days=250)
        if df is None or df.empty:
            results.append(PositionStatus(
                code=pos.code,
                current_price=0.0,
                pnl_pct=0.0,
                status="unmonitored",
            ))
            continue

        current_price = float(df["close"].iloc[-1])
        pnl_pct = (current_price - pos.cost_basis) / pos.cost_basis if pos.cost_basis else 0.0
        pnl_abs = (current_price - pos.cost_basis) * pos.quantity if pos.quantity is not None else None

        # Collect exit_monitor_ids from bound substrategies.
        monitor_ids: list[str] = []
        for sid in pos.strategy_ids:
            sub = sub_by_id.get(sid) if sub_by_id else get_substrategy(sid)
            if sub is None:
                continue
            mid = getattr(sub, "exit_monitor_id", None)
            if mid:
                monitor_ids.append(mid)

        alerts: list[tuple[str, str]] = []
        for mid in monitor_ids:
            monitor = mon_by_id.get(mid) if mon_by_id else get_monitor(mid)
            if monitor is None:
                continue
            try:
                alert, reason = monitor.check(df, pos)
            except Exception:
                continue
            if alert:
                alerts.append((mid, reason))

        if not monitor_ids:
            status = "unmonitored"
        elif alerts:
            status = "alert"
        else:
            status = "ok"

        results.append(PositionStatus(
            code=pos.code,
            current_price=current_price,
            pnl_pct=pnl_pct,
            pnl_abs=pnl_abs,
            alerts=alerts,
            status=status,
        ))

    return results
```

- [ ] **Step 12.4: 运行确认 pass**

```bash
python strategies/st_trading_system/test_positions.py
```
Expected: `All tests passed`

- [ ] **Step 12.5: 提交**

```bash
git add strategies/st_trading_system/positions.py strategies/st_trading_system/test_positions.py
git commit -m "feat(st_trading_system): add monitor_positions() with OR aggregation across monitors"
```

---

## Task 13: 更新 config.py

**Files:**
- Modify: `strategies/st_trading_system/config.py`

- [ ] **Step 13.1: 重写 config.py**

Replace the entire content of `strategies/st_trading_system/config.py` with:

```python
"""Global configuration for the trading management system.

Update DATA_DIR if your CSV data lives elsewhere. PORTFOLIO_PATH is the
JSON file holding user-entered positions (excluded from git).
"""

# ---- Data directory (local CSV OHLCV files) ----
DATA_DIR = 'D:/Git/QuanToolkit/data'

# ---- Portfolio persistence ----
PORTFOLIO_PATH = 'strategies/st_trading_system/portfolio.json'

# ---- Application metadata ----
APP_TITLE = '交易管理系统'
```

- [ ] **Step 13.2: 确认 import 不破**

```bash
python -c "from strategies.st_trading_system import config; print(config.APP_TITLE, config.PORTFOLIO_PATH)"
```
Expected: `交易管理系统 strategies/st_trading_system/portfolio.json`

- [ ] **Step 13.3: 提交**

```bash
git add strategies/st_trading_system/config.py
git commit -m "refactor(st_trading_system): drop KB_* configs, add PORTFOLIO_PATH"
```

---

## Task 14: 重写 app.py

**Files:**
- Modify: `strategies/st_trading_system/app.py` (完全重写)

这是最大的一块。拆成多步来做。

- [ ] **Step 14.1: 备份读旧文件结构，记住 CSS 色常量**

```bash
head -80 strategies/st_trading_system/app.py
```
Expected: 看到 `_YELLOW = "#F0B90B"` 等设计系统常量。

- [ ] **Step 14.2: 完全重写 app.py**

Replace the entire content of `strategies/st_trading_system/app.py` with:

```python
"""Streamlit app: Screener + Position tabs.

Tab 1 — 选股: multi-select substrategies + AND/OR + date + run. Display
hit table with per-stock indicator snapshot. Export CSV.

Tab 2 — 持仓: add/edit/delete positions, refresh latest prices, show
exit-monitor alerts, click row to expand a candlestick with buy-date marker
and bound-strategy indicator overlays.
"""

import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tools.data_adapter.local_csv import get_stock_list

from strategies.st_trading_system.config import APP_TITLE, DATA_DIR, PORTFOLIO_PATH
from strategies.st_trading_system.data_provider import LocalCSVProvider
from strategies.st_trading_system.indicators import (
    calc_bbi,
    calc_long_stoch,
    calc_short_stoch,
    calc_white_line,
    calc_zhuan,
)
from strategies.st_trading_system.models import Position
from strategies.st_trading_system.positions import monitor_positions
from strategies.st_trading_system.registry import (
    list_substrategies,
    list_monitors,
    registry_errors,
)
from strategies.st_trading_system.screener import screen
from strategies.st_trading_system import storage


# --- Design tokens ---
_YELLOW = "#F0B90B"
_GOLD = "#FFD000"
_WHITE = "#FFFFFF"
_SNOW = "#F5F5F5"
_DARK_BG = "#222126"
_DARK_CARD = "#2B2F36"
_INK = "#1E2026"
_SLATE = "#848E9C"
_GREEN = "#0ECB81"
_RED = "#F6465D"
_BORDER = "#E6E8EA"

_CSS = f"""
<style>
    html, body, [class*="st-"] {{
        font-family: 'Segoe UI', Arial, sans-serif;
        color: {_INK};
    }}
    #MainMenu, footer, header {{ visibility: hidden; }}
    .app-header {{
        background: {_DARK_BG};
        padding: 16px 32px;
        margin: -16px -16px 24px -16px;
        display: flex; align-items: center; gap: 16px;
    }}
    .app-header .logo-mark {{
        width: 32px; height: 32px;
        background: {_YELLOW};
        border-radius: 8px;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 16px; color: {_INK};
    }}
    .app-header h1 {{
        font-size: 20px; font-weight: 600; color: {_WHITE}; margin: 0;
    }}
    .app-header .subtitle {{
        font-size: 13px; color: {_SLATE}; margin-left: auto;
    }}
    .dark-band {{
        background: {_DARK_BG}; border-radius: 12px; padding: 24px; margin-bottom: 24px;
    }}
    .metric-card {{
        background: {_DARK_CARD}; border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px; padding: 20px 16px; text-align: center;
    }}
    .metric-card .value {{
        font-size: 32px; font-weight: 700; color: {_YELLOW};
        line-height: 1.0; font-variant-numeric: tabular-nums;
    }}
    .metric-card .value.alert {{ color: {_RED}; }}
    .metric-card .value.ok {{ color: {_GREEN}; }}
    .metric-card .label {{
        font-size: 12px; font-weight: 600; color: {_SLATE}; margin-top: 8px;
        text-transform: uppercase; letter-spacing: 0.05em;
    }}
    .banner-error {{
        background: rgba(246, 70, 93, 0.1);
        border: 1px solid {_RED};
        border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;
        color: {_RED}; font-size: 13px;
    }}
    .stButton > button {{
        background: {_YELLOW} !important; color: {_INK} !important;
        border: none !important; border-radius: 6px !important;
        font-weight: 600 !important; padding: 8px 32px !important;
    }}
    .stButton > button:hover {{
        background: #1EAEDB !important; color: {_WHITE} !important;
    }}
</style>
"""


def _inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def _render_errors():
    errors = registry_errors()
    if not errors:
        return
    for file, err in errors:
        st.markdown(
            f'<div class="banner-error"><strong>{file}</strong> — {err}</div>',
            unsafe_allow_html=True,
        )


def _data_provider():
    if "provider" not in st.session_state:
        st.session_state["provider"] = LocalCSVProvider(DATA_DIR)
    return st.session_state["provider"]


def _scan_cache():
    if "scan_cache" not in st.session_state:
        st.session_state["scan_cache"] = {}
    return st.session_state["scan_cache"]


# =========================================================================
# Tab 1 — 选股
# =========================================================================

def _tab_screener():
    st.subheader("选股")

    subs = list_substrategies()
    if not subs:
        st.warning("没有可用的子策略。检查 substrategies/ 目录和 registry 错误 banner。")
        return

    # Group by tag for display.
    tag_groups: dict[str, list] = {}
    for s in subs:
        for tag in s.tags or ["untagged"]:
            tag_groups.setdefault(tag, []).append(s)

    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            scan_date = st.date_input("扫描日期", date.today())
        with col2:
            mode = st.radio("组合方式", ["AND", "OR"], horizontal=True)
        with col3:
            include_growth = st.checkbox("含创业板/科创板", value=False)

        st.markdown("**选择子策略**")
        all_ids: list[str] = []
        selected_ids: list[str] = []
        for tag in sorted(tag_groups.keys()):
            st.markdown(f"*{tag}*")
            for s in tag_groups[tag]:
                key = f"sub_{s.id}"
                if st.checkbox(f"{s.name} — {s.description}", key=key):
                    selected_ids.append(s.id)
                all_ids.append(s.id)

        run_clicked = st.button("Run Scan", use_container_width=False)

    if not run_clicked:
        st.info("勾选子策略并点 Run Scan。")
        return

    if not selected_ids:
        st.warning("至少选一个子策略。")
        return

    date_str = scan_date.strftime("%Y%m%d")

    with st.spinner("Scanning..."):
        universe = get_stock_list(DATA_DIR, include_growth_boards=include_growth)
        results = screen(
            substrategy_ids=selected_ids,
            mode=mode,
            universe=universe,
            date=date_str,
            data_provider=_data_provider(),
            cache=_scan_cache(),
        )

    st.markdown(f"**{len(results)} 只命中**")

    if not results:
        return

    # Build display DataFrame.
    rows = []
    all_snapshot_keys: set[str] = set()
    for r in results:
        row = {
            "code": r.code,
            "hit_count": r.hit_count,
            "hit_ids": ", ".join(r.hit_ids),
            "close": round(r.close, 3),
        }
        for k, v in r.indicators_snapshot.items():
            if isinstance(v, (int, float)):
                row[k] = round(float(v), 3)
            else:
                row[k] = v
            all_snapshot_keys.add(k)
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values(["hit_count", "code"], ascending=[False, True]).reset_index(drop=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Export CSV",
        data=csv_bytes,
        file_name=f"screen_{date_str}.csv",
        mime="text/csv",
    )


# =========================================================================
# Tab 2 — 持仓
# =========================================================================

def _tab_positions():
    st.subheader("持仓")

    subs = list_substrategies()
    sub_ids = [s.id for s in subs]

    # Load positions from disk into session_state on first render.
    if "positions_loaded" not in st.session_state:
        st.session_state["positions"] = [
            _position_to_dict(p) for p in storage.load_positions(PORTFOLIO_PATH)
        ]
        st.session_state["positions_loaded"] = True

    positions_dicts = st.session_state["positions"]

    # ---------------- Summary band ----------------
    statuses: list = []
    if positions_dicts:
        positions = [_dict_to_position(p) for p in positions_dicts]
        statuses = monitor_positions(
            positions=positions,
            data_provider=_data_provider(),
            today=date.today().strftime("%Y%m%d"),
        )

    alert_n = sum(1 for s in statuses if s.status == "alert")
    ok_n = sum(1 for s in statuses if s.status == "ok")
    unmon_n = sum(1 for s in statuses if s.status == "unmonitored")
    total_pnl_pct = (
        sum(s.pnl_pct for s in statuses) / len(statuses) if statuses else 0.0
    )

    st.markdown(
        f'<div class="dark-band">'
        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:16px;">'
        f'<div class="metric-card"><div class="value">{len(positions_dicts)}</div><div class="label">总持仓</div></div>'
        f'<div class="metric-card"><div class="value alert">{alert_n}</div><div class="label">告警</div></div>'
        f'<div class="metric-card"><div class="value ok">{ok_n}</div><div class="label">安全</div></div>'
        f'<div class="metric-card"><div class="value">{unmon_n}</div><div class="label">无监控</div></div>'
        f'<div class="metric-card"><div class="value">{total_pnl_pct*100:.2f}%</div><div class="label">平均浮动</div></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ---------------- Add form ----------------
    with st.expander("新增持仓", expanded=False):
        with st.form("add_position_form", clear_on_submit=True):
            code = st.text_input("股票代码", placeholder="例如 000001")
            col_a, col_b = st.columns(2)
            with col_a:
                entry_dt = st.date_input("买入日", date.today())
            with col_b:
                cost = st.number_input("成本价", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            strat_sel = st.multiselect("绑定子策略", sub_ids)
            qty = st.number_input("数量 (可选, 0 = 不记录)", min_value=0.0, value=0.0, step=1.0)
            notes = st.text_input("备注 (可选)")
            submitted = st.form_submit_button("添加")
            if submitted:
                if not code.strip():
                    st.error("股票代码不能为空")
                else:
                    new_pos = Position(
                        code=code.strip(),
                        entry_date=entry_dt.strftime("%Y%m%d"),
                        cost_basis=float(cost),
                        strategy_ids=list(strat_sel),
                        quantity=float(qty) if qty > 0 else None,
                        notes=notes.strip(),
                    )
                    storage.add_position(PORTFOLIO_PATH, new_pos)
                    st.session_state["positions"] = [
                        _position_to_dict(p) for p in storage.load_positions(PORTFOLIO_PATH)
                    ]
                    st.success(f"添加: {new_pos.code}")
                    st.rerun()

    # ---------------- Table + per-row expansion ----------------
    if not positions_dicts:
        st.info("还没有持仓。点开'新增持仓'添加第一条。")
        return

    # Table header
    header_cols = st.columns([1.5, 1.5, 1.3, 1.3, 1.3, 2, 1, 1, 1])
    for c, label in zip(
        header_cols,
        ["code", "买入日", "成本", "现价", "浮动%", "绑定策略", "状态", "操作", ""],
    ):
        c.markdown(f"**{label}**")

    # Data rows
    for i, (pos_dict, stat) in enumerate(zip(positions_dicts, statuses)):
        row_cols = st.columns([1.5, 1.5, 1.3, 1.3, 1.3, 2, 1, 1, 1])
        bg = "rgba(246, 70, 93, 0.08)" if stat.status == "alert" else ""
        row_cols[0].markdown(f'<div style="background:{bg};padding:4px;">{pos_dict["code"]}</div>', unsafe_allow_html=True)
        row_cols[1].write(pos_dict["entry_date"])
        row_cols[2].write(f'{pos_dict["cost_basis"]:.2f}')
        row_cols[3].write(f"{stat.current_price:.2f}")
        pnl_color = _GREEN if stat.pnl_pct >= 0 else _RED
        row_cols[4].markdown(f'<span style="color:{pnl_color}">{stat.pnl_pct*100:+.2f}%</span>', unsafe_allow_html=True)
        row_cols[5].write(", ".join(pos_dict["strategy_ids"]) or "(无)")
        row_cols[6].markdown(
            f'<span style="color:{_RED if stat.status == "alert" else _SLATE}">{stat.status}</span>',
            unsafe_allow_html=True,
        )
        if row_cols[7].button("删", key=f"del_{i}"):
            storage.delete_position(PORTFOLIO_PATH, i)
            st.session_state["positions"] = [
                _position_to_dict(p) for p in storage.load_positions(PORTFOLIO_PATH)
            ]
            st.rerun()
        if row_cols[8].button("图", key=f"chart_{i}"):
            st.session_state[f"expand_{i}"] = not st.session_state.get(f"expand_{i}", False)
            st.rerun()

        if st.session_state.get(f"expand_{i}"):
            _render_position_chart(_dict_to_position(pos_dict), stat)
            if stat.alerts:
                st.markdown("**告警详情：**")
                for mid, reason in stat.alerts:
                    st.markdown(f"- `{mid}`: {reason}")


# ---------- helpers ----------

def _position_to_dict(p: Position) -> dict:
    return {
        "code": p.code,
        "entry_date": p.entry_date,
        "cost_basis": p.cost_basis,
        "strategy_ids": list(p.strategy_ids),
        "quantity": p.quantity,
        "notes": p.notes,
    }


def _dict_to_position(d: dict) -> Position:
    return Position(
        code=d["code"],
        entry_date=d["entry_date"],
        cost_basis=d["cost_basis"],
        strategy_ids=list(d.get("strategy_ids", [])),
        quantity=d.get("quantity"),
        notes=d.get("notes", ""),
    )


def _render_position_chart(pos: Position, status) -> None:
    df = _data_provider().get_latest(pos.code, days=120)
    if df is None:
        st.warning(f"无 {pos.code} 数据")
        return

    # Compute indicator overlays based on bound strategies.
    overlay_bbi = False
    overlay_white = False
    overlay_stoch = False
    overlay_zhuan = False
    for sid in pos.strategy_ids:
        if sid == "b1":
            overlay_bbi = overlay_white = True
        elif sid == "danzhen20":
            overlay_stoch = True
        elif sid == "zhuan":
            overlay_zhuan = True

    if overlay_bbi:
        df = calc_bbi(df)
    if overlay_white:
        df = calc_white_line(df)
    if overlay_stoch:
        df = calc_short_stoch(df)
        df = calc_long_stoch(df)
    if overlay_zhuan:
        df = calc_zhuan(df)

    plot_dates = pd.to_datetime(df["trade_date"], format="%Y%m%d")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=plot_dates, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="OHLC",
        increasing_line_color=_GREEN, decreasing_line_color=_RED,
    ))
    if overlay_bbi and "bbi" in df.columns:
        fig.add_trace(go.Scatter(x=plot_dates, y=df["bbi"], name="BBI",
                                 line=dict(color=_YELLOW, width=1.5)))
    if overlay_white and "white_line" in df.columns:
        fig.add_trace(go.Scatter(x=plot_dates, y=df["white_line"], name="白线",
                                 line=dict(color="#FFFFFF", width=1.2)))
    if overlay_zhuan and "signal_zhuan" in df.columns:
        fig.add_trace(go.Scatter(x=plot_dates, y=df["signal_zhuan"], name="砖型图",
                                 line=dict(color=_GOLD, width=1.2, dash="dash")))

    # Buy-date vertical line
    try:
        entry_dt = pd.to_datetime(pos.entry_date, format="%Y%m%d")
        fig.add_vline(x=entry_dt, line=dict(color=_YELLOW, dash="dot", width=1))
    except Exception:
        pass

    fig.update_layout(
        title=dict(text=f"{pos.code} — 成本 {pos.cost_basis:.2f}", font=dict(size=13, color=_SLATE)),
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_DARK_BG,
        font=dict(color=_SLATE, size=11),
        height=420,
        xaxis_rangeslider_visible=False,
        margin=dict(l=50, r=30, t=40, b=30),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=10, color=_SLATE)),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Secondary stoch panel if needed
    if overlay_stoch and "short_stoch" in df.columns:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=plot_dates, y=df["short_stoch"], name="short", line=dict(color=_YELLOW)))
        fig2.add_trace(go.Scatter(x=plot_dates, y=df["long_stoch"], name="long", line=dict(color=_GOLD)))
        fig2.add_hline(y=20, line=dict(color=_RED, dash="dot", width=1))
        fig2.add_hline(y=60, line=dict(color=_GREEN, dash="dot", width=1))
        fig2.update_layout(
            paper_bgcolor=_DARK_BG, plot_bgcolor=_DARK_BG,
            font=dict(color=_SLATE, size=11), height=200,
            margin=dict(l=50, r=30, t=20, b=30),
            xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        )
        st.plotly_chart(fig2, use_container_width=True)


# =========================================================================
# Main
# =========================================================================

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    _inject_css()

    st.markdown(
        f'<div class="app-header">'
        f'<div class="logo-mark">T</div>'
        f'<h1>{APP_TITLE}</h1>'
        f'<span class="subtitle">A-Share Screener & Positions</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _render_errors()

    tab1, tab2 = st.tabs(["选股", "持仓"])
    with tab1:
        _tab_screener()
    with tab2:
        _tab_positions()


if __name__ == "__main__":
    main()
```

- [ ] **Step 14.3: 语法校验（不启动 Streamlit）**

```bash
python -c "import ast; ast.parse(open('strategies/st_trading_system/app.py', encoding='utf-8').read())"
```
Expected: 空输出（解析成功）。

- [ ] **Step 14.4: import 校验**

```bash
python -c "import sys; sys.path.insert(0, '.'); from strategies.st_trading_system import app; print('import ok')"
```
Expected: `import ok`。

若报错，修正缺失的 import 或 typo，重新校验。

- [ ] **Step 14.5: 提交**

```bash
git add strategies/st_trading_system/app.py
git commit -m "feat(st_trading_system): rewrite app.py as 2-tab screener+positions UI"
```

---

## Task 15: 清理旧文件 + 更新 requirements.txt + .gitignore

**Files:**
- Delete: `strategies/st_trading_system/kb_reader.py`
- Delete: `strategies/st_trading_system/scanner.py`
- Delete: `strategies/st_trading_system/signals.py`
- Modify: `strategies/st_trading_system/requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 15.1: 删除过时文件**

```bash
rm strategies/st_trading_system/kb_reader.py strategies/st_trading_system/scanner.py strategies/st_trading_system/signals.py
```

- [ ] **Step 15.2: 删除 __pycache__ 里对应的 pyc**

```bash
rm -f strategies/st_trading_system/__pycache__/kb_reader.cpython-*.pyc strategies/st_trading_system/__pycache__/scanner.cpython-*.pyc strategies/st_trading_system/__pycache__/signals.cpython-*.pyc
```

- [ ] **Step 15.3: 更新 requirements.txt**

Replace `strategies/st_trading_system/requirements.txt` with:

```
streamlit>=1.35
plotly>=5.0
pandas>=2.0
numpy>=1.26
```

（移除了 `chardet`）

- [ ] **Step 15.4: 更新 .gitignore**

查看现状并追加：

```bash
cat .gitignore 2>/dev/null | tail -10
```

然后在 `.gitignore` 末尾追加这一行（如果已存在则跳过）：

```
strategies/st_trading_system/portfolio.json
```

如果 `.gitignore` 不存在，则创建一个：

```
__pycache__/
*.pyc
strategies/st_trading_system/portfolio.json
```

- [ ] **Step 15.5: 回归所有测试**

```bash
python strategies/st_trading_system/test_models.py && \
python strategies/st_trading_system/test_base.py && \
python strategies/st_trading_system/test_storage.py && \
python strategies/st_trading_system/test_data_provider.py && \
python strategies/st_trading_system/test_substrategies.py && \
python strategies/st_trading_system/test_monitors.py && \
python strategies/st_trading_system/test_registry.py && \
python strategies/st_trading_system/test_screener.py && \
python strategies/st_trading_system/test_positions.py
```
Expected: 每个都输出 `All tests passed`，最后 exit code 0。

- [ ] **Step 15.6: import app.py 没断**

```bash
python -c "import sys; sys.path.insert(0, '.'); from strategies.st_trading_system import app; print('ok')"
```
Expected: `ok`。

- [ ] **Step 15.7: 提交**

```bash
git add -A strategies/st_trading_system/requirements.txt .gitignore
git add -u strategies/st_trading_system/
git commit -m "chore(st_trading_system): remove deprecated kb_reader/scanner/signals, drop chardet dep"
```

---

## Task 16: 手动 Streamlit 冒烟测试（用户交付）

这个任务由人执行，不是自动化。

- [ ] **Step 16.1: 启动 Streamlit**

```bash
cd strategies/st_trading_system && streamlit run app.py
```
Expected: 浏览器打开 http://localhost:8501，页面显示"交易管理系统"标题、两个 Tab（选股 / 持仓）。

- [ ] **Step 16.2: 选股 Tab 冒烟**

1. 勾选 `b1 / danzhen20 / zhuan` 三个策略
2. 切换 OR，点 Run Scan
3. 等待扫描完成，确认结果表出现、包含 `code / hit_count / hit_ids / close` 列
4. 切换 AND 再点 Run Scan，确认结果集变小
5. 点 Export CSV，确认能下载

- [ ] **Step 16.3: 持仓 Tab 冒烟**

1. 点"新增持仓"，填入 `000001 / 今天 / 10.0 / 勾选 b1`，提交
2. 确认表里出现一行，显示现价、浮动%、状态
3. 点该行的"图"按钮，确认下方展开 K 线，带 BBI/白线 overlay + 买入日虚线
4. 再点"删"按钮，确认行消失
5. 关掉 Streamlit 重启，确认持仓（若还保留）从 portfolio.json 正确载入

- [ ] **Step 16.4: 错误注入验证**

在 `substrategies/` 新建一个 `broken.py`，内容就是 `raise ImportError("test")`，刷新页面。预期：顶部出现红色 banner 显示 `broken` 加载失败，其他三个策略继续可用。

测完后删掉 `broken.py`。

- [ ] **Step 16.5: 提交**

（仅当上面 step 中修了任何 bug 时才提交）

```bash
git add -A
git commit -m "fix: smoke-test corrections from Task 16"
```

---

## Self-Review

- **PRD 覆盖**：全部 user stories 覆盖到任务。
- **占位符**：所有代码块完整，无 "TODO" / "implement later"。
- **类型一致性**：`Position.strategy_ids` 全程是 `list[str]`；`ScreeningResult.hit_ids` 全程是 `list[str]`；`PositionStatus.alerts` 全程是 `list[tuple[str, str]]`。
- **文件路径**：每个文件路径精确到目录。
- **命令可复现**：所有 Run/Expected 都可验证。
