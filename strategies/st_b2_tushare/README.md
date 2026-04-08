# st_b2_tushare - KDJ Reversal Screening + Backtest

基于 tushare 日线数据的独立选股与回测工具，与 QMT 完全解耦。

## 策略逻辑

st_b2 KDJ 反转选股（与 QMT 版 `strategies/st_b2` 逻辑一致）：

1. KDJ(9,3,3)：前一日 J < 20，当日 J <= 65
2. 当日涨幅 > 4%
3. 量比 >= 1.1（当日成交量 / 前一日成交量）
4. 标的：沪深主板 A 股（排除创业板 300、科创板 688/689）

## 安装依赖

```bash
pip install tushare pandas numpy
```

## 配置

编辑 `config.json`：

```json
{
    "data_dir": "D:/Git/QuanToolkit/data",
    "tushare_token": "你的token"
}
```

**优先使用本地数据**：设置 `data_dir` 后直接从本地 CSV 文件加载，无需 tushare API 调用。如需从 API 拉取数据，将 `data_dir` 留空并设置 `tushare_token`。

本地数据格式要求：每只股票一个 CSV 文件（如 `000001.csv`），列名 `date,open,close,high,low,volume`，日期格式 `YYYY-MM-DD`。

### 配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `data_dir` | - | 本地日线数据目录（优先于 API） |
| `tushare_token` | - | tushare API token（API 模式时必填） |
| `start_date` | 20240101 | 回测起始日期 |
| `end_date` | 20251231 | 回测结束日期 |
| `initial_capital` | 1000000 | 初始资金（元） |
| `max_positions` | 3 | 最大同时持仓数 |
| `kdj_n` | 9 | KDJ 周期 |
| `kdj_init` | 50.0 | KDJ 初始 K/D 值 |
| `j_pre_max` | 20.0 | 前一日 J 值上限 |
| `j_now_max` | 65.0 | 当日 J 值上限 |
| `daily_return_min_pct` | 4.0 | 最低日涨幅(%) |
| `vol_ratio_min` | 1.1 | 最低量比 |
| `output_dir` | output | 输出目录 |

## 运行

```bash
# 使用 config.json 默认参数
python main.py

# 命令行覆盖参数
python main.py --start 20240101 --end 20251231 --capital 500000 --max-positions 5

# 指定配置文件
python main.py --config my_config.json

# 命令行传入 token
python main.py --token YOUR_TOKEN
```

## 输出

运行后在 `output/` 目录生成以下文件（带时间戳）：

| 文件 | 说明 |
|------|------|
| `trades_*.csv` | 每笔交易明细（买入/卖出日期、价格、收益率、盈亏） |
| `equity_*.csv` | 每日权益曲线（日期、总权益、现金、持仓数） |
| `screening_*.csv` | 每日选股结果（日期、排名、股票代码、涨幅、量比、J值） |
| `summary_*.txt` | 回测统计摘要 |

### 统计指标

- **总收益率**：期末权益 / 初始资金 - 1
- **最大回撤**：权益曲线峰值到谷底的最大跌幅
- **胜率**：盈利交易数 / 总交易数
- **平均/中位数收益**：每笔交易的收益分布

## 回测引擎说明

采用完整交易模拟模式：

- 每日先卖出所有持仓（T+1 规则自动满足）
- 从当日选股结果中按涨幅排名取前 N 只买入
- 等权分配资金（可用资金 / 剩余仓位），按 100 股整手买入
- 资金回收后可在后续交易日再利用

## 后续迭代

- [ ] AI 辅助参数优化
- [ ] 更多策略支持（st_b1, st_dj20 等）
- [ ] 止损/止盈卖出规则
- [ ] 定时任务脚本
