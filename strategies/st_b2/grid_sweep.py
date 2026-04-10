"""Parameter grid sweep for st_b2 strategy.

Implements IMPL-005: sweep KDJ parameters to find better configurations
when the default config produces returns < 20%.
"""

import json
import sys
from itertools import product
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from strategies.st_b2.strategy import generate_signals, get_default_config
from tools.data_adapter.local_csv import load_market_data
from tools.backtest_engine import run_backtest


def load_config():
    config_path = project_root / "strategies" / "st_b2_tushare" / "config.json"
    with open(config_path) as f:
        return json.load(f)


def run_sweep():
    cfg = load_config()
    start_date = cfg.get("start_date", "20240101")
    end_date = cfg.get("end_date", "20251231")
    data_dir = cfg.get("data_dir", "")

    print("Loading market data...", flush=True)
    daily_data = load_market_data(data_dir, start_date, end_date)
    print(f"Loaded {len(daily_data)} stocks", flush=True)

    # Parameter grid — reduced to practical size for faster sweep
    param_grid = {
        "j_pre_max": [15.0, 20.0, 30.0],
        "j_now_max": [55.0, 65.0, 80.0],
        "daily_return_min_pct": [2.0, 4.0, 6.0],
        "vol_ratio_min": [0.8, 1.0, 1.5],
        "max_positions": [3, 5, 10],
    }

    bt_config = {
        "initial_capital": cfg.get("initial_capital", 1000000),
        "slippage_pct": cfg.get("slippage_pct", 0.1),
        "commission_pct": cfg.get("commission_pct", 0.025),
        "stamp_tax_pct": cfg.get("stamp_tax_pct", 0.05),
        "transfer_fee_pct": cfg.get("transfer_fee_pct", 0.001),
    }

    # Generate all combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    total = 1
    for v in values:
        total *= len(v)
    print(f"Grid: {total} combinations", flush=True)

    results = []
    for i, combo in enumerate(product(*values)):
        params = get_default_config()
        for k, v in zip(keys, combo):
            params[k] = v

        bt_cfg = dict(bt_config)
        bt_cfg["max_positions"] = params["max_positions"]

        signals = generate_signals(daily_data, params)
        total_candidates = sum(len(v) for v in signals.values())

        if total_candidates == 0:
            continue

        result = run_backtest(signals, daily_data, bt_cfg)

        results.append({
            "j_pre_max": params["j_pre_max"],
            "j_now_max": params["j_now_max"],
            "daily_return_min_pct": params["daily_return_min_pct"],
            "vol_ratio_min": params["vol_ratio_min"],
            "max_positions": bt_cfg["max_positions"],
            "total_return_pct": result.total_return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "trade_count": result.trade_count,
            "avg_return_pct": result.avg_return_pct,
            "median_return_pct": result.median_return_pct,
            "final_equity": result.final_equity,
            "signal_count": total_candidates,
        })

        if (i + 1) % 20 == 0:
            print(f"  [{i + 1}/{total}] ...", flush=True)

    # Sort by total_return_pct descending
    results.sort(key=lambda x: x["total_return_pct"], reverse=True)

    # Print top 20
    print(f"\n{'Rank':<5} {'Return%':<10} {'MDD%':<10} {'WinRate%':<10} {'Trades':<8} {'AvgRet%':<10} {'Jpre':<8} {'Jnow':<8} {'dRet%':<8} {'VR':<6} {'Pos':<5} {'Signals':<10}")
    print("-" * 120)
    for i, r in enumerate(results[:20]):
        print(f"{i+1:<5} {r['total_return_pct']:<10.2f} {r['max_drawdown_pct']:<10.2f} {r['win_rate']:<10.2f} {r['trade_count']:<8} {r['avg_return_pct']:<10.2f} {r['j_pre_max']:<8} {r['j_now_max']:<8} {r['daily_return_min_pct']:<8} {r['vol_ratio_min']:<6} {r['max_positions']:<5} {r['signal_count']:<10}")

    # Also print stats summary
    if results:
        best = results[0]
        print(f"\nBest config: return={best['total_return_pct']}%, MDD={best['max_drawdown_pct']}%, win={best['win_rate']}%")
        print(f"  j_pre_max={best['j_pre_max']}, j_now_max={best['j_now_max']}")
        print(f"  daily_return_min_pct={best['daily_return_min_pct']}, vol_ratio_min={best['vol_ratio_min']}")
        print(f"  max_positions={best['max_positions']}, trades={best['trade_count']}")

        positive_count = sum(1 for r in results if r["total_return_pct"] > 0)
        print(f"\nPositive returns: {positive_count}/{len(results)} configurations")

    # Save full results to JSON
    output_path = project_root / "output" / "grid_sweep_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {output_path}")

    return results


if __name__ == "__main__":
    run_sweep()