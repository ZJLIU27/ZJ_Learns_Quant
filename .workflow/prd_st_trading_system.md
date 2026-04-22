# PRD: 子策略可组合的网页选股与持仓监控工具（`st_trading_system` 重构）

> **状态**：v1 范围已与用户完成"grill-me"对焦，可直接进入实现阶段。
> **本地决策**：不提 GitHub Issue，本文件即作为实现依据。

## Problem Statement

我早些时候在 `strategies/st_trading_system/` 做了一个 Streamlit 网页工具，当时的功能和现在的预期完全不一样：

- 当前版本是四个 Tab（每日扫描 / 个股查看 / 知识库浏览 / 持仓管理），硬编码了 B1、单针探 20、砖型图三个策略，策略之间只能各自独立出一份清单，不能组合；Tab 3 的 Obsidian 浏览器和选股工具没关系；Tab 4 的持仓管理只是一张孤立的表，和选股逻辑、策略定义断开。
- 我真正想要的是一个**本地单机运行**的工具：以"选股"和"持仓"为核心。选股要能把策略拆成小块（子策略），用户多选后用 AND/OR 组合成一次扫描；持仓要和策略绑定，能按策略里定义的退出条件监控破位，而不是当 Excel 用。
- 另外，后续我打算在 Claude Code 里 vibe-code 继续优化具体策略（拆子策略、加条件），所以"新增子策略"这条路必须简单到改一个文件夹就生效，不要我手动去 UI 或注册表里挂。

## Solution

把 `st_trading_system` 重写成两个 Tab、四个可独立测试的"深模块"，围绕"子策略注册表 + 组合引擎 + 持仓监控 + 本地存储"组织：

- **Tab 1 选股**：用户从子策略列表里勾选若干条，选 AND 或 OR 组合，选扫描日期，一键执行；结果表给出每只股票命中的子策略清单、关键指标快照，可排序、可导出。
- **Tab 2 持仓**：用户录入持仓（代码、买入日、成本价、关联的子策略/策略组），点刷新后工具用当日数据算当前价、浮盈浮亏，并跑每个持仓关联的"退出条件监控"，破位给告警；点击行可展开 K 线图，叠加绑定策略的指标，标出买入日。
- 子策略写成 `substrategies/` 包里的独立小文件（一个 `BaseSubStrategy` 子类一个文件）；退出监控器写成 `monitors/` 包里的独立小文件（一个 `BaseMonitor` 子类一个文件）。新增只需丢一个文件，注册表自动发现，不改 UI。策略文档放在 Obsidian 知识库里（不在这个工具里渲染）。

## User Stories

1. 作为个人量化交易者，我想打开本地的网页选股工具，看到一个简洁的两 Tab 界面（选股 / 持仓），这样我不用被无关的功能干扰。
2. 作为选股使用者，我想在选股 Tab 看到所有可用子策略的清单（名称 + 一句话描述 + tag 分组），这样我能快速挑出今天想组合的几条。
3. 作为选股使用者，我想同时勾选多个子策略，这样我能用"多条件组合"代替单一死板的策略。
4. 作为选股使用者，我想切换 AND / OR 组合方式，这样严格底仓和开放底仓两种诉求都能满足。
5. 作为选股使用者，我想指定扫描日期（默认今天），这样我能对历史日期复盘出当日候选池。
6. 作为选股使用者，我想一个复选框切换"是否包含创业板/科创板"，默认只扫主板，这样我能按需求调整扫描范围。
7. 作为选股使用者，我想在结果表里看到每只股票命中了哪些子策略（名字列表）和命中数量，这样我可以按综合强度排序。
8. 作为选股使用者，我想看到每只命中股票当前的关键指标快照（收盘价、BBI、白黄线、stoch 等，取决于触发的子策略），这样我不用再单独打开一个工具复核。
9. 作为选股使用者，我想把扫描结果导出为 CSV，这样我能贴到 Obsidian 或 Excel 里留存当日复盘。
10. 作为选股使用者，当我切换子策略勾选或组合方式时，我希望结果在当前会话里缓存不要每次都重跑全市场，这样点选对比更流畅。
11. 作为量化开发者（vibe-code 阶段），我想在 `substrategies/` 下新增一个 `.py` 文件、写一个 `BaseSubStrategy` 子类，重启 Streamlit 后子策略自动出现在 UI 多选框里，这样我不用改 UI 代码。
12. 作为量化开发者，我想给每个子策略定义"tag"（如 `entry` / `exit` / `bundle` / `atomic` / `形态` / `量能`），这样 UI 可以按 tag 分组显示。
13. 作为量化开发者，我想在 `monitors/` 下新增一个 `.py` 文件、写一个 `BaseMonitor` 子类就能复用给任意子策略，这样退出条件可被多个 bundle 共享。
14. 作为持仓管理者，我想在持仓 Tab 录入买入价、买入日期、关联的子策略列表、数量（可选）、备注（可选），这样这条持仓后续的监控条件能自动绑定。
15. 作为持仓管理者，我想持仓列表能持久化到磁盘（`portfolio.json`），这样我关 Streamlit、重开后数据还在。
16. 作为持仓管理者，我想能编辑和删除持仓，这样错录的数据可以修正。
17. 作为持仓管理者，我想点"刷新行情"按钮后每条持仓自动拉当日可得收盘数据，算出当前价、浮动盈亏百分比（若填了数量也显示绝对盈亏），这样我不用手动敲价格。
18. 作为持仓管理者，我想每条持仓根据绑定的子策略自动跑"退出条件监控"（b1 → close < BBI），破位时行变红 + 图标 + 汇总栏里计数加一，这样我能秒级看到哪些仓位出状况。
19. 作为持仓管理者，我想在持仓页面的顶部汇总栏看到"总持仓数 / 告警数 / 安全数 / 总浮动盈亏"，这样我不用逐行读表。
20. 作为持仓管理者，我想一条持仓可以绑定多个子策略，只要其中任一绑定策略的退出监控器破位即告警（OR 语义），这样安全阈值更严。
21. 作为持仓管理者，我想点击某条持仓行后下方展开一张 K 线图，标出买入日垂直虚线，叠加绑定策略的关键指标（b1 → BBI + 白线；danzhen20 → short/long stoch 面板；zhuan → 砖型图线），这样我能直观复核当前走势。
22. 作为持仓管理者，我想持仓绑定的策略若没有退出监控器（如 v1 的 danzhen20 / zhuan），UI 明确显示"无监控"而不是静默无告警，这样我知道哪些仓位是"裸仓"。
23. 作为本地用户，我想工具复用仓库里已有的 `tools/data_adapter/local_csv.py` 读 `D:/Git/QuanToolkit/data` 下的 CSV，这样不用再搭一份数据层。
24. 作为本地用户，我想在 `config.py` 里改数据目录和持仓存档路径，这样把数据挪到别处也能跑。
25. 作为本地用户，我想保留一条"接入实时行情"的扩展接口（但本期不实现），这样后续我加 tushare/akshare/xtQMT 实时源时不用改上层。
26. 作为本地用户，我想继续通过 `run.bat` 一键启动，这样保持和现在一致的入口。
27. 作为项目维护者，我想删掉 `kb_reader.py`、`scanner.py`、`signals.py` 和对应的知识库 Tab、旧的个股查看 Tab、旧的持仓 Tab，这样代码清爽不包含和新工具无关的组件；策略文档继续住在 Obsidian 里，工具不负责渲染。
28. 作为项目维护者，我想扫描引擎（`screener.py`）跟 Streamlit 解耦（纯函数 + 依赖注入 data_provider），这样我在命令行也能调用同一套扫描逻辑。
29. 作为项目维护者，我想 AND / OR 组合的语义有单测覆盖，这样以后重构不用担心回归。
30. 作为项目维护者，我想子策略注册表的"发现 + 评估"流程有单测覆盖（用构造的 fake 子策略 + 构造的 OHLCV），这样新增子策略时能跑单测验证接口契约没破。
31. 作为项目维护者，我想持仓监控的破位判断有单测覆盖，这样改动监控器时不会误报或漏报。
32. 作为项目维护者，我想持仓存储的增删改查有单测覆盖，这样换文件格式或者加字段时 JSON 兼容性不会悄悄破。
33. 作为使用者，当某只股票数据缺失或 CSV 损坏时，我希望工具跳过而不是崩溃，并在扫描日志里打印跳过数量，这样一两条坏数据不影响整体扫描。
34. 作为使用者，当某个子策略或监控器文件加载失败（语法错误、缺方法），我希望看到 UI 顶部一条明显 banner 标出失败项和原因，其他子策略照常工作，这样我 vibe-code 出错能立刻发现。

## Implementation Decisions

### v1 子策略清单

直接从现有 `scanner.py` / `signals.py` 迁移 3 个整套 bundle，不预先拆原子条件：

| id | 名称 | tag | 入场条件 | 退出监控 (v1) |
|---|---|---|---|---|
| `b1` | B1 候选池 | entry, bundle | close>BBI ∧ white_line 上行 ∧ 近 4 根有单根 `|open-close|/close > 0.03` | `close_below_bbi` |
| `danzhen20` | 单针探 20 | entry, bundle | short_stoch ≤ 20 ∧ long_stoch ≥ 60 | `None` |
| `zhuan` | 砖型图 | entry, bundle | 砖型图 XG 标志为 True | `None` |

### 模块划分

1. **子策略注册表（`substrategies/` 包，深模块）**
   - 每个子策略一个独立 `.py`，一个 `BaseSubStrategy` 子类。
   - `BaseSubStrategy` 类属性：`id: str`、`name: str`、`description: str`、`tags: list[str]`、`min_rows: int`、`exit_monitor_id: str | None`。
   - 方法：`evaluate(self, df) -> tuple[bool, dict]`，返回（命中？, 指标快照）。
   - 注册表：`substrategies/__init__.py` 负责自动发现。扫描包内所有 `.py`，import 后收集 `BaseSubStrategy` 的所有子类；文件加载失败则跳过并记录到 `registry.errors`（UI banner 消费）。
   - 对外 API：`list_substrategies() -> list[BaseSubStrategy]`、`get_substrategy(id) -> BaseSubStrategy`、`registry_errors() -> list[(file, error)]`。
   - 重复 id 检测：导入时若发现同 id 冲突，后加载的记到 errors，保留先加载的。
   - **架构支持原子粒度（后续 vibe-code 加原子条件时走同一接口），但 v1 只有 3 个 bundle。**

2. **监控器注册表（`monitors/` 包，深模块）**
   - 每个监控器一个独立 `.py`，一个 `BaseMonitor` 子类。
   - `BaseMonitor` 类属性：`id: str`、`description: str`。
   - 方法：`check(self, df, position) -> tuple[bool, str]`，返回（是否告警, 原因）。
   - 注册表同构：`list_monitors()`、`get_monitor(id)`、`registry_errors()`。
   - v1 唯一监控器：`monitors/close_below_bbi.py`（close < BBI 触发告警）。

3. **组合引擎 `screener.py`（深模块）**
   - 纯函数接口：`screen(substrategy_ids, mode, universe, date, data_provider) -> list[ScreeningResult]`
   - `ScreeningResult` 字段：`code`、`close`、`hit_ids`（命中的子策略 id 列表）、`hit_count`、`indicators_snapshot`（合并各子策略返回的快照，dict.update 风格后写覆盖先写；v1 bundle 之间快照 key 不重叠）。
   - 组合语义：AND = 命中集合 == 选中集合；OR = 命中集合 ∩ 选中集合 非空。
   - 空选择保护：`substrategy_ids == []` 直接返回 `[]`，不扫。
   - 股票池：通过 `tools/data_adapter/local_csv.get_stock_list`，主板默认；UI 层通过 `include_growth_boards` 开关决定是否扩展到 300/688/689。
   - 不依赖 Streamlit，可独立 import 跑。
   - **扫描缓存粒度 = `(code, sub_id, date)`**：第一次扫描时把每只股每个子策略的 `(hit, snapshot)` 放进 session-level dict；用户切换选中集或 AND/OR 时只做集合运算，不重算指标。缓存键含 `data_dir` mtime，数据目录更新则失效。

4. **持仓监控 `positions.py`（深模块）**
   - 纯函数接口：`monitor_positions(positions, data_provider, today) -> list[PositionStatus]`
   - `Position` 字段：`code: str`、`entry_date: str (YYYYMMDD)`、`cost_basis: float`、`strategy_ids: list[str]`、`quantity: float | None`、`notes: str`。
   - `PositionStatus` 字段：`code`、`current_price`、`pnl_pct`、`pnl_abs: float | None`（仅在 `quantity` 存在时计算）、`alerts: list[(monitor_id, reason)]`、`status: "ok"|"alert"|"unmonitored"`。
   - 对每条持仓，遍历 `strategy_ids`，查注册表拿到每个策略的 `exit_monitor_id`；对所有非 None 的监控器跑 `check(df, position)`，任一触发即 alert（OR 汇总）。所有监控器皆 None 时 `status="unmonitored"`。

5. **持仓存储 `storage.py`（深模块）**
   - JSON 文件，默认 `strategies/st_trading_system/portfolio.json`（`PORTFOLIO_PATH` 可改）。`.gitignore` 加入该路径。
   - 接口：`load_positions() -> list[Position]`、`save_positions(list[Position])`、`add_position(Position)`、`update_position(index, Position)`、`delete_position(index)`。
   - 原子写入：写入临时文件 `portfolio.json.tmp` 再 `os.replace` 为 `portfolio.json`。
   - 字段向前兼容：load 时缺失字段走默认值，不抛异常。
   - 文件不存在：`load_positions()` 返回 `[]`。

6. **数据源**
   - 复用 `tools/data_adapter/local_csv.py`。
   - 在本工具内加 Provider 接口 `LocalCSVProvider`：
     - `get_history(code, end_date, days) -> pd.DataFrame | None`
     - `get_latest(code) -> pd.DataFrame | None`（返回含最新可得 bar 的 df）
   - `screener` / `positions` 均通过参数注入 provider，单测可传 fake。
   - 实时行情留接口不实现；未来 `TushareProvider` 等实现同接口即可。

7. **UI `app.py`（重写）**
   - 两个 Tab：**选股**、**持仓**。
   - **选股 Tab**：
     - 子策略多选（按 tag 分组，显示 name + description），AND/OR 单选，日期选择（默认 today），`含创业板/科创板` 复选框，Run 按钮。
     - 结果 DataFrame：`code` | `hit_count` | `hit_ids`（策略徽章 chip 列表）| `close` | 指标快照展开列（按快照里实际 key 自动展开）。
     - 导出 CSV 按钮。
     - 顶部如有注册表错误，显示 banner。
   - **持仓 Tab**：
     - 汇总卡片条（总仓 / 告警 / 无监控 / 安全 / 总浮动盈亏%）。
     - 持仓表（Streamlit `data_editor` 或自定义）：可编辑 `code` / `entry_date` / `cost_basis` / `strategy_ids` (multiselect) / `quantity` / `notes`。新增 / 删除行。
     - Refresh 按钮：调 `monitor_positions`，刷新表中的 `current_price` / `pnl_pct` / `pnl_abs` / `status`。告警行背景高亮。
     - 点击某行 → 下方展开 Plotly K 线图，买入日垂直虚线，叠加绑定策略的指标（并集）。
     - 顶部如有注册表错误，显示 banner。
   - 沿用 `design.md` 的 Binance.US CSS；徽章样式对应策略 id（`strategy-badge.b1` 等）。
   - `run.bat` 保持不变。

### 清理

- **删除**：`kb_reader.py`、`scanner.py`、`signals.py`、`requirements.txt` 里的 `chardet`、`config.py` 中的 `KB_ZET_DIR` / `KB_MOBIUS_DIR`。
- **新增**：`config.py` 里的 `PORTFOLIO_PATH`。
- 不保留 `.bak` 副本——git 历史就够了。

### 约定

- 测试风格沿用 `strategies/st_b2/parity_test.py`：测试文件 colocated（如 `strategies/st_trading_system/test_screener.py`），函数名以 `test_` 开头，`if __name__ == "__main__"` 可 standalone 跑，亦兼容 `python -m pytest`。不引入 `pytest.ini`。
- 注册表发现时机：模块 import 时扫一次；v1 不做热加载，新增子策略/监控器需要重启 Streamlit。
- Plotly 图表样式沿用 `app.py` 现有的深色主题（`paper_bgcolor=_DARK_BG` 等）。
- 无 GitHub Issue 追踪；本 PRD 即实现依据。

## Testing Decisions

### 好测试的原则

- 只测对外行为（公开接口的输入→输出），不测私有函数和内部状态。
- 不使用模块内部 mock；依赖注入 data_provider，用构造的小 OHLCV DataFrame 做输入。
- 每个测试应当能在一句话里描述它在验证哪个事实。
- 遵循 `parity_test.py` 的 standalone-runnable 风格。

### 测试覆盖

1. **`substrategies/` 注册表（`test_substrategies.py`）**
   - `test_discovery_finds_all_v1_bundles`：启动后 `list_substrategies()` 含 `b1`、`danzhen20`、`zhuan`。
   - `test_b1_triggers_on_constructed_positive`：构造满足 3 条件的 DataFrame，`B1.evaluate` 返回 `(True, {...})`，snapshot 含 `bbi`、`white_line`、`close`。
   - `test_b1_rejects_on_constructed_negative`：分别构造违反每个条件的 3 组数据，`B1.evaluate` 返回 `(False, ...)`。
   - `test_danzhen20_trigger_and_reject`：同上。
   - `test_zhuan_trigger_and_reject`：同上。
   - `test_short_data_returns_false`：行数 < `min_rows` 时所有 bundle 返回 `(False, ...)`。
   - `test_duplicate_id_rejected`：构造两个 id 同名的临时子策略，第二个进 errors。

2. **`screener.py` 组合引擎（`test_screener.py`）**
   - `test_and_semantics`：用 fake provider + 2 个 fake 子策略，构造只有 1 只股两个都命中，AND 结果只含该股。
   - `test_or_semantics`：相同数据 OR 返回两只股各自命中的并集。
   - `test_hit_ids_correct`：每只股的 `hit_ids` 等于"命中集合 ∩ 选中集合"。
   - `test_empty_selection_returns_empty`：`substrategy_ids=[]` 返回 `[]`。
   - `test_bad_data_skipped`：fake provider 对某 code 返回 None，该 code 不出现在结果里，不抛异常。
   - `test_cache_reuses_evaluations`：同一 date 两次调用，第二次的 evaluate 调用次数为 0（用带计数器的 fake 子策略验证）。

3. **`monitors/` + `positions.py`（`test_positions.py`）**
   - `test_no_alert_when_above_bbi`：构造持仓 `code=X, strategy_ids=["b1"]` + 一个 close > BBI 的 df，`status == "ok"`、`alerts == []`。
   - `test_alert_when_close_below_bbi`：构造 close < BBI 的 df，`status == "alert"`、`alerts` 含 `("close_below_bbi", ...)`。
   - `test_unmonitored_when_no_exit_monitor`：持仓只绑 `danzhen20`，`status == "unmonitored"`、`alerts == []`。
   - `test_or_across_multiple_strategies`：持仓绑 `b1` + `danzhen20`，只要 b1 破位即 alert（OR）。
   - `test_pnl_pct_correct`：`cost=10, current=12` → `pnl_pct = 0.20`。
   - `test_pnl_abs_only_when_quantity`：`quantity=None` 时 `pnl_abs is None`；`quantity=100, cost=10, current=12` 时 `pnl_abs == 200`。

4. **`storage.py`（`test_storage.py`）**
   - `test_roundtrip`：save → load 得到等价列表。
   - `test_add_update_delete`：三个操作前后 load 的结果符合预期。
   - `test_missing_file_returns_empty`：不存在时 load 返回 `[]`。
   - `test_atomic_write_preserves_on_failure`：用 monkeypatch 让 `os.replace` 抛异常，原文件不被破坏。
   - `test_forward_compat_missing_field`：手写一份缺 `quantity` 字段的 JSON，`load_positions()` 返回的 Position 用默认值 None。

### 现有参考

- `strategies/st_b2/parity_test.py` 是现成的"构造输入 → 调函数 → 断言"范式。
- `tools/backtest_engine/` 下各模块独立且清晰接口，可参考 data_provider 注入风格。

## Out of Scope

- **不做实时行情接入**（只留 Provider 接口；CSV EOD 已满足当前需求）。
- **不做 Obsidian 知识库的嵌入浏览**（策略文档继续用 Obsidian 原生环境查看）。
- **不做历史信号回测**（后续如需可以加第三个 Tab，调用 `tools/backtest_engine/`，不在本期）。
- **不做用户登录、多用户、远程部署**（明确本地单机）。
- **不自动发现持仓**（用户手动录入；不接券商 API）。
- **不做盘中实时刷新**（每次 Refresh 按钮点击才刷新）。
- **不做新策略的图形化编辑器**（子策略一律靠在 Claude Code 里写代码新增）。
- **不改变底层数据目录结构或 CSV schema**。
- **不处理涨跌停 / 停牌 / 除权等边界**（沿用当前 CSV 里是什么就是什么）。
- **不做告警推送**（邮件 / Slack / 微信）；只在 UI 显示。
- **不做自定义股票池 / watch list**（v1 只有主板默认 + 创业板/科创板开关）。
- **不做选股 → 加仓的跨 Tab 跳转**（v1 用"复制代码-切 Tab-粘贴"）。
- **不做子策略热加载**（新增/修改子策略需要重启 Streamlit）。
- **不预先把 bundle 拆成原子条件**（v1 就 3 个整套；原子条件由后续 vibe-code 按需补）。
- **不持久化 PositionStatus 到 portfolio.json**（状态永远按需计算，只存用户录入字段）。
- **不引入 pytest 配置文件**（沿用现有 standalone test 风格）。

## Further Notes

- **策略文档源头**：用户把策略规则（入场条件、退出监控条件）写在 Obsidian 里，路径：
  - `D:/ObsidianDB/ZiJ/00_Inbox/zet`
  - `D:/ObsidianDB/ZiJ/Notion/黄金的mobius`
  - 工具实现时要对照这些文档落实子策略条件；PRD 不逐一罗列（那是实现阶段 vibe-code 的事）。
- **与 `REQUIREMENTS.md` 的关系**：`REQUIREMENTS.md` 是 xtQMT 内置脚本策略的约定，本工具是独立的 Streamlit 网页工具，不受 xtQMT 脚本规范约束，可以自由使用 pandas / numpy / streamlit / plotly 等库。
- **与 `strategies/st_b2*` 的关系**：这些是独立的回测脚本，不直接集成到本工具，但其 scan 逻辑可以被提取成未来的子策略（超出 v1 范围）。
- **后续 vibe-code 流程**：在 Claude Code 里描述"我要把 B1 的条件 3（近 4 根大阳）单独拆出来"，新建一个 `substrategies/big_candle.py`，写一个 `BaseSubStrategy` 子类，重启 Streamlit 后自动出现在 UI 里。
- **设计系统**：沿用 `design.md` 里定义的 Binance.US 风格，两个 Tab 的样式保持现有 CSS 的主题一致性。
