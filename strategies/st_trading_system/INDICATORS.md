# st_trading_system 指标总表

本文件用于固化当前项目里已经确认、并准备持续复用的常用指标定义。

目标只有两个：

1. 让后续策略讨论不必反复回 Obsidian 翻同一批笔记。
2. 明确“项目内字段/预置指标/图表显示”和“笔记里的口头叫法”之间的映射关系。

本文件只记录当前共识，不把还没钉死的推测性口径混进来。

## 资料来源

当前整理主要基于以下 Obsidian 笔记中的已确认内容：

- `D:\ObsidianDB\ZiJ\00_Inbox\zet\B1完美图形视觉标准（初稿）.md`
- `D:\ObsidianDB\ZiJ\00_Inbox\zet\zet策略优化补充（mobius对照）.md`
- `D:\ObsidianDB\ZiJ\00_Inbox\zet\zet量化策略候选.md`
- `D:\ObsidianDB\ZiJ\00_Inbox\zet\zet战法手册.md`
- `D:\ObsidianDB\ZiJ\00_Inbox\zet\逐份整理\直播回放_2025-06-01_22-50-00.md`
- `D:\ObsidianDB\ZiJ\00_Inbox\zet\逐份整理\zettaranc Z哥 B站充电直播回放2.md`

## 项目内指标清单

| 项目内 ID | 显示名 | 常见别名 | 图表位置 | 代码列 / 输出 |
| --- | --- | --- | --- | --- |
| `bbi` | BBI | Bull and Bear Index | 主图叠加 | `bbi` |
| `white_line` | 白线 | 散户线、`Z_短期趋势线` | 主图叠加 | `white_line` |
| `yellow_line` | 黄线 | 大哥线、长期资金线、`Z_多空线` | 主图叠加 | `yellow_line` |
| `danzhen_panel` | 单针下20/30 | 单针下20/30 副图 | 副图 | `danzhen_*` |
| `zhuan_panel` | 砖型图 | 砖型图副图 | 副图 | `signal_zhuan`、`xg` |

这些预置指标在代码中的注册位置：

- [indicator_presets.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicator_presets.py:10)
- [indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:19)

## 1. BBI

- 项目字段：`bbi`
- 图表位置：主图叠加
- 当前作用：主图趋势与持有锚点，常用于 `close > BBI`、`跌破 BBI` 等规则
- 项目公式：

```text
BBI = (MA3 + MA6 + MA12 + MA24) / 4
```

- 代码位置：[indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:19)
- 当前理解：
  - 它是价格级主图指标，不是 0-100 区间摆动指标。
  - 在 B1 和持仓管理里，BBI 更像结构支撑与止损参考。
  - 在项目现状里，BBI 已经是最稳定的工程锚点之一。

## 2. 白线

- 项目字段：`white_line`
- 图表位置：主图叠加
- Obsidian 常见叫法：`白线 = 散户线`
- 项目公式：

```text
白线 = EMA(EMA(C,10),10)
```

- 代码位置：[indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:38)
- 当前理解：
  - 它是短期趋势线，也是项目里最常用的“拴牛绳”代理字段。
  - 在 B1 语境里，价格围绕白线整理、跌破白线止损，是高频出现的执行语言。
  - 白线属于价格级主图指标，不是单针副图里的 0-100 红白黄线。

## 3. 黄线

- 项目字段：`yellow_line`
- 图表位置：主图叠加
- Obsidian 常见叫法：`黄线 = 大哥线 = 长期资金线`
- 项目公式：

```text
黄线 = (MA14 + MA28 + MA57 + MA114) / 4
```

- 代码位置：[indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:59)
- 当前理解：
  - 它比白线更慢，更多承担“大级别主线有没有坏”的判断。
  - 在持有和防卖飞语境里，常与白线一起组成“白线先看、黄线再看”的分层纪律。
  - 同样属于价格级主图指标，不要和单针副图里的 0-100 阈值硬并成一回事。

## 4. 单针下20/30副图

### 4.1 面板四线

- 项目字段：
  - `danzhen_short`
  - `danzhen_medium`
  - `danzhen_medium_long`
  - `danzhen_long`
- 图表位置：副图
- 当前配色约定：
  - 副图里的红线对应 `danzhen_long`
- 项目公式：

```text
短 = 100 * (C - LLV(L,3)) / (HHV(C,3) - LLV(L,3))
中 = 100 * (C - LLV(L,10)) / (HHV(C,10) - LLV(L,10))
中长 = 100 * (C - LLV(L,20)) / (HHV(C,20) - LLV(L,20))
长 = 100 * (C - LLV(L,21)) / (HHV(C,21) - LLV(L,21))
```

- 代码位置：[indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:196)
- 当前理解：
  - 这四条线是单针副图自己的参考线，数值区间是 0-100。
  - 它们不是主图白线/黄线的同义替换。
  - 后续所有单针相关规则，都应优先明确是“主图白黄线”还是“单针副图四线”。

### 4.2 已落地的单针信号柱

- `danzhen_four_line_zero`
  - 语义：四线都极低，当前阈值是 `<= 6`
- `danzhen_short_below_20`
  - 语义：短线低位，当前工程口径是 `短 <= 20 且 长 >= 60`
- `danzhen_short_cross_long`
  - 语义：短线上穿长线，且长线仍在低位
- `danzhen_short_cross_medium`
  - 语义：短线上穿中线，且中线仍在低位

这些信号柱当前主要用于副图可视化和后续规则拆解，不代表它们全部都已经被定义为正式策略入口。

### 4.3 当前已确认的单针策略主信号

目前项目里关于 `danzhen20` 的最新共识，正式按 `单针下20/30` 的双版本状态信号处理：

- 默认版本：`单针下30`
- 严格版本：`单针下20`
- 两个版本都要求：
  - `短 = danzhen_short`
  - `长 = danzhen_long`
  - `白线 = white_line`
  - `黄线 = yellow_line`

当前选股口径：

```text
单针下30 = 短 <= 30 且 长 >= 80 且 白线 > 黄线
单针下20 = 短 <= 20 且 长 >= 80 且 白线 > 黄线
```

补充约束：

- 这是状态信号，不是首次触发信号。
- 连续多天满足条件，就连续多天都算信号。
- 结果中需要区分 `单针下20` 和 `单针下30` 两种命中版本。

## 5. 砖型图

- 项目字段：
  - `var6a`
  - `signal_zhuan`
  - `xg`
- 图表位置：副图
- 当前工程含义：
  - `signal_zhuan` 是可视化主线
  - `xg` 是当前代码里的起涨触发标记
- 项目公式链条摘要：

```text
VAR1A -> VAR2A
VAR3A -> VAR4A -> VAR5A
VAR6A = VAR5A - VAR2A
砖型图主线 = IF(VAR6A > 4, VAR6A - 4, 0)
XG = 主线进入新一段上升的起点
```

- 代码位置：[indicators.py](/D:/Git/ZJ_Learns_Quant/strategies/st_trading_system/indicators.py:125)
- 当前理解：
  - 砖型图是一套独立副图策略，不并入 B1，也不并入单针下20。
  - 当前工程已能计算和画图，但后续是否继续细分买点、持有和退出，还要单独讨论。

## 6. 当前只作为辅助概念的东西

### 双线归零

- 当前状态：辅助结构，不单独立法
- 当前理解：
  - 它是帮助判断“洗盘后又来一个新买点”的辅助结构。
  - 可以作为 B1 或单针体系的过滤器，但不建议脱离主图结构单独交易。

### 深V

- 当前状态：图形子形态，不单独立法
- 当前理解：
  - 深V 属于单针下20/30 体系里的图形说明。
  - 后续如果要做样本标注，可以单独做 tag，但不建议先把它写成独立策略类。

### 勾到大负值

- 当前状态：重要辅助概念，但项目里还没有稳定公式落地
- 当前理解：
  - 它在笔记和直播里非常常见，也经常和 B1、补票战法一起出现。
  - 目前还缺一份我们已经完全确认、并能稳定回测的工程定义，所以暂时不放进“当前已实现指标主清单”。

## 7. 项目内的使用边界

- 主图价格级指标：
  - `bbi`
  - `white_line`
  - `yellow_line`
- 副图 0-100 指标：
  - `danzhen_short`
  - `danzhen_medium`
  - `danzhen_medium_long`
  - `danzhen_long`
- 独立副图策略：
  - `signal_zhuan`

后续讨论任何规则时，都必须先说清楚到底引用的是哪一层：

1. 主图价格级指标
2. 单针副图 0-100 四线
3. 砖型图副图
4. 纯图形概念或执行纪律

不先分层，后面的策略定义一定会乱。
