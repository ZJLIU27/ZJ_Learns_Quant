# 基础要求（xtQMT 内置脚本）

## 背景与适用范围
本文档用于统一所有策略实现的基础约束，适用于在 xtQMT 客户端内直接运行的策略脚本。

## 运行环境要求
- 必须为 xtQMT 客户端内置脚本运行方式（非外部 Python 连接 MiniQMT）。

## 脚本格式与最小规范
- 脚本首行需包含 `#coding:gbk`。
- 必须包含 `init()` 与 `handlebar()`。
- `handlebar()` 按每根 K 线触发；实时行情下最后一根 K 线会随 tick 反复触发。
- 仅使用 QMT 内置 API + Python 标准库；如需第三方库必须单独说明并确认。

## 标的范围
- 沪深 A 股。
- 排除创业板与科创板。

## 目录与交付约定
- 每个策略独立文件夹。
- 默认根目录：`/Users/liuzijian/git/ZJ_Learns_Quant/strategies/<strategy_name>/`。
- 最少包含：`main.py` 与 `README.md`。

## 策略细节声明
- 具体规则、参数、风控由单独策略说明给出。

## 参考文档
- 迅投知识库《使用说明》：[docs.thinktrader.net](https://docs.thinktrader.net/pages/91d44f/)
- 迅投知识库《使用须知》：[dict.thinktrader.net](https://dict.thinktrader.net/innerApi/user_attention.html)
