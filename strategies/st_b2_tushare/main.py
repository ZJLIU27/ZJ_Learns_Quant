"""
st_b2_tushare - KDJ Reversal Stock Screening + Backtesting (Tushare Edition)

Data loading + backtesting engine. Strategy logic lives in strategies/st_b2/.
Uses local CSV data (or tushare API) to screen stocks and run trading simulation.

Strategy logic (from strategies/st_b2):
  - KDJ(9,3,3): J(T-1) < 20 AND J(T) <= 65
  - Daily return > 4%
  - Volume ratio >= 1.1
  - Universe: Main board A-shares only (excl. ChiNext, STAR)

Usage:
  python main.py                       # use config.json defaults
  python main.py --start 20240101 --end 20251231
  python main.py --config my_config.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import tushare as ts
except ImportError:
    ts = None

# Strategy module — add project root for package resolution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from strategies.st_b2.strategy import generate_signals, get_default_config as get_strategy_config
from tools.data_adapter.local_csv import load_market_data, get_stock_list as get_local_stock_list

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    # Override from CLI args (handled in main)
    return cfg


# ---------------------------------------------------------------------------
# Tushare Data Layer
# ---------------------------------------------------------------------------

MAIN_BOARD_PREFIXES = ("600", "601", "603", "605", "000", "001", "002")


def is_main_board(ts_code: str) -> bool:
    """Check if a ts_code (e.g. '000001.SZ') or plain code (e.g. '000001') belongs to main board."""
    code = ts_code.split(".")[0]
    if code.startswith(("300", "688", "689")):
        return False
    return code.startswith(MAIN_BOARD_PREFIXES)


def fetch_stock_list(pro) -> pd.DataFrame:
    """Fetch all listed A-shares, filtered to main board only."""
    df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry")
    df = df[df["ts_code"].apply(is_main_board)].reset_index(drop=True)
    return df


def fetch_daily_data(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily OHLCV for a single stock. Returns DataFrame sorted by date ascending."""
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def fetch_all_daily_data(
    pro, stock_list: pd.DataFrame, start_date: str, end_date: str, batch_size: int = 50
) -> dict[str, pd.DataFrame]:
    """Fetch daily data for all stocks. Returns {ts_code: DataFrame}.

    Uses batched calls with a small delay to respect tushare rate limits.
    """
    from time import sleep

    result = {}
    codes = stock_list["ts_code"].tolist()
    total = len(codes)
    print(f"Fetching daily data for {total} stocks ({start_date} ~ {end_date})...")

    for i, code in enumerate(codes):
        if (i + 1) % 200 == 0:
            print(f"  Progress: {i + 1}/{total}")
        try:
            df = fetch_daily_data(pro, code, start_date, end_date)
            if not df.empty:
                result[code] = df
        except Exception as e:
            # Skip individual failures (suspended, delisted, etc.)
            pass
        # Rate limit: tushare allows ~200 calls/min for paid users
        if (i + 1) % batch_size == 0:
            sleep(1)

    print(f"  Fetched data for {len(result)} stocks.")
    return result


# Data loading now lives in tools/data_adapter/local_csv.py


# ---------------------------------------------------------------------------
# Screening logic now lives in strategies/st_b2/strategy.py
# generate_signals() returns {trade_date: [{code, ...}]}; mapped to ts_code below


# ---------------------------------------------------------------------------
# Backtest Engine - Complete Trading Simulation
#   Supports three variants for A/B comparison:
#     A: Biased (signal-day close, no costs) — original behavior
#     B: T+1 only (next-day open, no costs)
#     C: T+1 + full costs (next-day open + slippage/commission/stamp_tax/transfer_fee)
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Simulates real trading with capital allocation, position management, T+1 selling.

    variant:
      "biased"  — buy at signal-day close, no costs (original behavior)
      "t1_only" — buy at next-day open (T+1), no costs
      "t1_cost" — buy at next-day open (T+1), with full A-share costs
    """

    def __init__(self, config: dict, variant: str = "t1_cost"):
        self.initial_capital = config.get("initial_capital", 1000000)
        self.max_positions = config.get("max_positions", 3)
        self.variant = variant
        # Cost parameters (only used when variant == "t1_cost")
        self.slippage_pct = config.get("slippage_pct", 0.1) / 100.0
        self.commission_pct = config.get("commission_pct", 0.025) / 100.0
        self.stamp_tax_pct = config.get("stamp_tax_pct", 0.05) / 100.0
        self.transfer_fee_pct = config.get("transfer_fee_pct", 0.001) / 100.0
        self.reset()

    def reset(self):
        """Reset engine state for a fresh run."""
        self.cash = float(self.initial_capital)
        self.positions: list[dict] = []
        self.closed_trades: list[dict] = []
        self.equity_curve: list[dict] = []

    def _apply_buy_cost(self, price: float) -> float:
        """Apply buy-side costs: slippage markup + commission + transfer fee."""
        if self.variant != "t1_cost":
            return price
        buy_price = price * (1.0 + self.slippage_pct)
        return buy_price

    def _apply_sell_cost(self, price: float) -> float:
        """Apply sell-side costs: slippage markdown. Commission/stamp_tax/transfer_fee deducted from cash."""
        if self.variant != "t1_cost":
            return price
        sell_price = price * (1.0 - self.slippage_pct)
        return sell_price

    def _deduct_buy_fees(self, amount: float):
        """Deduct commission + transfer_fee from cash on buy."""
        if self.variant != "t1_cost":
            return
        self.cash -= amount * (self.commission_pct + self.transfer_fee_pct)

    def _deduct_sell_fees(self, amount: float):
        """Deduct commission + stamp_tax + transfer_fee from cash on sell."""
        if self.variant != "t1_cost":
            return
        self.cash -= amount * (self.commission_pct + self.stamp_tax_pct + self.transfer_fee_pct)

    def _buy(self, code: str, price: float, trade_date: str) -> bool:
        """Buy a stock. Equal-weight allocation from available cash."""
        available_slots = self.max_positions - len(self.positions)
        if available_slots <= 0:
            return False

        actual_price = self._apply_buy_cost(price)

        # Allocate: available cash / remaining slots
        alloc_per_slot = self.cash / available_slots
        # Round down to nearest 100 shares (A-share lot size)
        shares = int(alloc_per_slot / actual_price / 100) * 100
        if shares <= 0:
            # Try with all cash
            shares = int(self.cash / actual_price / 100) * 100
            if shares <= 0:
                return False

        cost = shares * actual_price
        if cost > self.cash:
            shares = int(self.cash / actual_price / 100) * 100
            if shares <= 0:
                return False
            cost = shares * actual_price

        self.cash -= cost
        self._deduct_buy_fees(cost)

        self.positions.append({
            "ts_code": code,
            "buy_date": trade_date,
            "buy_price": actual_price,
            "buy_raw_price": price,  # price before slippage
            "shares": shares,
            "cost": cost,
        })
        return True

    def _sell_all(self, price_lookup: dict[str, float], trade_date: str):
        """Sell all positions. T+1 rule: only sell positions bought before today."""
        still_holding = []
        for pos in self.positions:
            # T+1: can't sell on buy day
            if pos["buy_date"] == trade_date:
                still_holding.append(pos)
                continue

            raw_price = price_lookup.get(pos["ts_code"])
            if raw_price is None:
                # Can't find price, keep holding
                still_holding.append(pos)
                continue

            actual_sell_price = self._apply_sell_cost(raw_price)
            proceeds = pos["shares"] * actual_sell_price
            self.cash += proceeds
            self._deduct_sell_fees(proceeds)

            ret_pct = (actual_sell_price / pos["buy_price"] - 1.0) * 100.0

            self.closed_trades.append({
                "ts_code": pos["ts_code"],
                "buy_date": pos["buy_date"],
                "buy_price": pos["buy_price"],
                "sell_date": trade_date,
                "sell_price": actual_sell_price,
                "shares": pos["shares"],
                "return_pct": round(ret_pct, 2),
                "pnl": round(proceeds - pos["cost"], 2),
            })
        self.positions = still_holding

    def run(self, screening_results: dict[str, list[dict]], daily_data: dict[str, pd.DataFrame]):
        """Run backtest over all screening dates.

        For 'biased' variant: buy at signal-day close, sell at close.
        For 't1_only'/'t1_cost' variant: buy at next-day open, sell at open.
        """
        # Build price tables
        # close_table for biased variant, open_table for T+1 variants
        price_table: dict[str, dict[str, float]] = {}  # close prices
        open_table: dict[str, dict[str, float]] = {}    # open prices
        all_trade_dates = set()
        for code, df in daily_data.items():
            price_table[code] = dict(zip(df["trade_date"].values, df["close"].values.astype(float)))
            open_table[code] = dict(zip(df["trade_date"].values, df["open"].values.astype(float)))
            all_trade_dates.update(df["trade_date"].values)

        if not all_trade_dates:
            print("No trading dates found in data.")
            return

        sorted_trade_dates = sorted(all_trade_dates)
        # Build mapping: date -> next trading date for T+1 execution
        next_date_map = {}
        for i in range(len(sorted_trade_dates) - 1):
            next_date_map[sorted_trade_dates[i]] = sorted_trade_dates[i + 1]

        if self.variant == "biased":
            # Original biased behavior: buy at signal-day close, sell at close
            all_dates = sorted(screening_results.keys())
            if not all_dates:
                print("No screening results to backtest.")
                return

            actual_last_date = max(all_trade_dates) if all_trade_dates else all_dates[-1]
            prev_date = None

            for date in all_dates:
                # Step 1: Sell all positions at today's close price
                if prev_date is not None and self.positions:
                    sell_prices = {}
                    for pos in self.positions:
                        p = price_table.get(pos["ts_code"], {}).get(date)
                        if p is not None:
                            sell_prices[pos["ts_code"]] = p
                    self._sell_all(sell_prices, date)

                # Step 2: Buy from today's candidates at today's close price
                candidates = screening_results[date]
                available_slots = self.max_positions - len(self.positions)
                for cand in candidates[:available_slots]:
                    code = cand["ts_code"]
                    price = price_table.get(code, {}).get(date)
                    if price is not None:
                        self._buy(code, price, date)

                # Record equity
                total_equity = self.cash
                for pos in self.positions:
                    p = price_table.get(pos["ts_code"], {}).get(date, pos["buy_price"])
                    total_equity += pos["shares"] * p
                self.equity_curve.append({
                    "trade_date": date,
                    "equity": round(total_equity, 2),
                    "cash": round(self.cash, 2),
                    "positions": len(self.positions),
                })
                prev_date = date

            # Sell remaining positions at actual last trading date
            if self.positions:
                last_date = actual_last_date
                sell_prices = {}
                for pos in self.positions:
                    p = price_table.get(pos["ts_code"], {}).get(last_date, pos["buy_price"])
                    sell_prices[pos["ts_code"]] = p
                self._sell_all(sell_prices, last_date)

        else:
            # T+1 variants: buy at next-day open, sell at open
            # Build pending signal queue: signal_date -> T+1 execution_date
            pending_signals: dict[str, list[dict]] = {}
            signal_dates = sorted(screening_results.keys())
            discarded = 0
            for signal_date in signal_dates:
                exec_date = next_date_map.get(signal_date)
                if exec_date is None:
                    # No T+1 date available (last trading date), discard signal
                    discarded += 1
                    continue
                if exec_date not in pending_signals:
                    pending_signals[exec_date] = []
                pending_signals[exec_date].extend(screening_results[signal_date])

            if discarded > 0:
                print(f"  Discarded {discarded} signals with no T+1 execution date")

            # Iterate over ALL trading dates (not just signal dates)
            actual_last_date = sorted_trade_dates[-1]
            prev_date = None

            for date in sorted_trade_dates:
                # Step 1: Sell all positions at today's open price
                if prev_date is not None and self.positions:
                    sell_prices = {}
                    for pos in self.positions:
                        if pos["buy_date"] == date:
                            continue  # T+1: can't sell on buy day
                        p = open_table.get(pos["ts_code"], {}).get(date)
                        if p is not None:
                            sell_prices[pos["ts_code"]] = p
                    self._sell_all(sell_prices, date)

                # Step 2: Buy from pending signals at today's open price
                if date in pending_signals:
                    candidates = pending_signals[date]
                    available_slots = self.max_positions - len(self.positions)
                    for cand in candidates[:available_slots]:
                        code = cand["ts_code"]
                        open_price = open_table.get(code, {}).get(date)
                        if open_price is not None:
                            self._buy(code, open_price, date)

                # Record equity
                total_equity = self.cash
                for pos in self.positions:
                    p = price_table.get(pos["ts_code"], {}).get(date, pos["buy_price"])
                    total_equity += pos["shares"] * p
                self.equity_curve.append({
                    "trade_date": date,
                    "equity": round(total_equity, 2),
                    "cash": round(self.cash, 2),
                    "positions": len(self.positions),
                })
                prev_date = date

            # Final liquidation at last trading date's close
            if self.positions and self.equity_curve:
                last_date = actual_last_date
                sell_prices = {}
                for pos in self.positions:
                    p = price_table.get(pos["ts_code"], {}).get(last_date, pos["buy_price"])
                    if p is not None:
                        sell_prices[pos["ts_code"]] = p
                if sell_prices:
                    self._sell_all(sell_prices, last_date)

    def compute_stats(self) -> dict:
        """Compute backtest summary statistics."""
        if not self.closed_trades:
            final_equity = self.equity_curve[-1]["equity"] if self.equity_curve else self.cash
            return {
                "total_return_pct": 0.0,
                "win_rate": 0.0,
                "max_drawdown_pct": 0.0,
                "trade_count": 0,
                "final_equity": round(final_equity, 2),
            }

        returns = [t["return_pct"] for t in self.closed_trades]
        wins = sum(1 for r in returns if r > 0)

        # Total return from equity curve
        final_equity = self.equity_curve[-1]["equity"] if self.equity_curve else self.cash
        total_return = (final_equity / self.initial_capital - 1.0) * 100.0

        # Max drawdown from equity curve
        max_drawdown = 0.0
        if self.equity_curve:
            peak = self.equity_curve[0]["equity"]
            for snap in self.equity_curve:
                if snap["equity"] > peak:
                    peak = snap["equity"]
                dd = (peak - snap["equity"]) / peak * 100.0
                if dd > max_drawdown:
                    max_drawdown = dd

        return {
            "total_return_pct": round(total_return, 2),
            "win_rate": round(wins / len(returns) * 100.0, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "trade_count": len(self.closed_trades),
            "final_equity": round(final_equity, 2),
            "avg_return_pct": round(np.mean(returns), 2),
            "median_return_pct": round(np.median(returns), 2),
        }


# ---------------------------------------------------------------------------
# A/B Comparison
# ---------------------------------------------------------------------------

def run_ab_comparison(cfg: dict, screening_results: dict, daily_data: dict) -> dict:
    """Run 3 backtest variants and produce A/B comparison.

    Returns dict with keys 'biased', 't1_only', 't1_cost', each containing stats dict.
    """
    variants = [
        ("biased", "A: Biased (signal-day close, no costs)"),
        ("t1_only", "B: T+1 only (next-day open, no costs)"),
        ("t1_cost", "C: T+1 + full costs (next-day open + all A-share costs)"),
    ]

    results = {}
    for variant, label in variants:
        print(f"\n--- Running variant {label} ---")
        engine = BacktestEngine(cfg, variant=variant)
        engine.run(screening_results, daily_data)
        stats = engine.compute_stats()
        results[variant] = {
            "label": label,
            "stats": stats,
            "engine": engine,
        }
        print(f"  Return: {stats['total_return_pct']:.2f}%  |  Drawdown: {stats['max_drawdown_pct']:.2f}%  |  "
              f"Trades: {stats['trade_count']}  |  Win Rate: {stats['win_rate']:.2f}%")

    return results


def save_ab_comparison(results: dict, output_dir: str):
    """Save A/B comparison as markdown table."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    lines = [
        "# A/B Comparison: Future Function Fix Impact",
        "",
        "| Variant | Total Return | Max Drawdown | Trade Count | Win Rate |",
        "|---------|-------------|--------------|-------------|----------|",
    ]
    for key in ["biased", "t1_only", "t1_cost"]:
        r = results[key]
        s = r["stats"]
        trade_count = s["trade_count"]
        win_rate = f"{s['win_rate']:.2f}%"
        total_ret = f"{s['total_return_pct']:.2f}%"
        max_dd = f"{s['max_drawdown_pct']:.2f}%"
        lines.append(f"| {r['label']} | {total_ret} | {max_dd} | {trade_count} | {win_rate} |")

    lines.append("")
    lines.append("## Cost Model Parameters")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append("| Slippage | 0.1% |")
    lines.append("| Commission | 0.025% |")
    lines.append("| Stamp Tax (sell only) | 0.05% |")
    lines.append("| Transfer Fee | 0.001% |")
    lines.append("| Round-trip cost (~) | 0.352% |")
    lines.append("")
    lines.append("## Key Findings")
    lines.append("")
    lines.append("- Variant A uses **signal-day close price** as buy price (look-ahead bias)")
    lines.append("- Variant B uses **next-day open price** (T+1 execution, no costs)")
    lines.append("- Variant C uses **next-day open price + all A-share transaction costs**")
    lines.append("- The gap between A and C represents the true impact of the future function fix")
    lines.append("")

    md_text = "\n".join(lines)
    ab_path = out_path / "ab_comparison.md"
    with open(ab_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"\nA/B comparison saved to: {ab_path}")
    return md_text


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(engine: BacktestEngine, screening_results: dict, output_dir: str, variant_label: str = ""):
    """Save trade records CSV and summary stats."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Trade records CSV
    if engine.closed_trades:
        trades_df = pd.DataFrame(engine.closed_trades)
        suffix = f"_{variant_label}" if variant_label else ""
        trades_path = out_path / f"trades{suffix}_{timestamp}.csv"
        trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
        print(f"Trade records saved to: {trades_path}")

    # Equity curve CSV
    if engine.equity_curve:
        eq_df = pd.DataFrame(engine.equity_curve)
        suffix = f"_{variant_label}" if variant_label else ""
        eq_path = out_path / f"equity{suffix}_{timestamp}.csv"
        eq_df.to_csv(eq_path, index=False, encoding="utf-8-sig")
        print(f"Equity curve saved to: {eq_path}")

    # Screening summary CSV
    rows = []
    for date, candidates in screening_results.items():
        for rank, c in enumerate(candidates, 1):
            rows.append({"trade_date": date, "rank": rank, **c})
    if rows:
        screen_df = pd.DataFrame(rows)
        screen_path = out_path / f"screening_{timestamp}.csv"
        screen_df.to_csv(screen_path, index=False, encoding="utf-8-sig")
        print(f"Screening results saved to: {screen_path}")

    # Summary stats
    stats = engine.compute_stats()
    title = f"st_b2 Tushare Backtest Summary ({variant_label})" if variant_label else "st_b2 Tushare Backtest Summary"
    summary_lines = [
        "=" * 50,
        f"  {title}",
        "=" * 50,
        f"  Initial Capital:    {engine.initial_capital:>15,.0f}",
        f"  Final Equity:       {stats['final_equity']:>15,.2f}",
        f"  Total Return:       {stats['total_return_pct']:>14.2f}%",
        f"  Max Drawdown:       {stats['max_drawdown_pct']:>14.2f}%",
        f"  Trade Count:        {stats['trade_count']:>15d}",
        f"  Win Rate:           {stats['win_rate']:>14.2f}%",
        f"  Avg Return/Trade:   {stats['avg_return_pct']:>14.2f}%",
        f"  Median Return:      {stats['median_return_pct']:>14.2f}%",
        "=" * 50,
    ]
    summary_text = "\n".join(summary_lines)
    print(summary_text)

    suffix = f"_{variant_label}" if variant_label else ""
    summary_path = out_path / f"summary{suffix}_{timestamp}.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text + "\n")
    print(f"Summary saved to: {summary_path}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="st_b2 KDJ Reversal Screening + Backtest (Tushare)")
    parser.add_argument("--config", type=str, default=None, help="Path to config.json")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYYMMDD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYYMMDD)")
    parser.add_argument("--capital", type=float, default=None, help="Initial capital")
    parser.add_argument("--max-positions", type=int, default=None, help="Max concurrent positions")
    parser.add_argument("--token", type=str, default=None, help="Tushare API token")
    parser.add_argument("--variant", type=str, default="t1_cost",
                        choices=["biased", "t1_only", "t1_cost", "ab"],
                        help="Backtest variant: biased, t1_only, t1_cost, or ab (A/B comparison)")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)

    # Apply CLI overrides
    if args.token:
        cfg["tushare_token"] = args.token
    if args.start:
        cfg["start_date"] = args.start
    if args.end:
        cfg["end_date"] = args.end
    if args.capital:
        cfg["initial_capital"] = args.capital
    if args.max_positions:
        cfg["max_positions"] = args.max_positions

    start_date = cfg.get("start_date", "20240101")
    end_date = cfg.get("end_date", "20251231")

    # Step 1: Load data (prefer local, fallback to tushare API)
    data_dir = cfg.get("data_dir", "")
    if data_dir:
        print(f"Using local data from: {data_dir}")
        daily_data = load_market_data(data_dir, start_date, end_date)
    else:
        token = cfg.get("tushare_token", "")
        if not token or token == "YOUR_TUSHARE_TOKEN_HERE":
            print("Error: Set data_dir in config.json for local data, or set tushare_token for API mode")
            sys.exit(1)
        if ts is None:
            print("Error: tushare not installed. Run: pip install tushare")
            sys.exit(1)

        print(f"Initializing tushare (token: {token[:8]}...)")
        pro = ts.pro_api(token)

        print("Fetching stock list...")
        stock_list = fetch_stock_list(pro)
        print(f"  Main board A-shares: {len(stock_list)} stocks")

        daily_data = fetch_all_daily_data(pro, stock_list, start_date, end_date)

    # Step 2: Run screening using strategy module
    print("Running st_b2 screening...")
    strategy_params = get_strategy_config()
    # Override with config values if present
    for key in strategy_params:
        if key in cfg:
            strategy_params[key] = cfg[key]

    screen_raw = generate_signals(daily_data, strategy_params)
    # Map "code" field to "ts_code" for BacktestEngine compatibility
    screening_results = {}
    for date, candidates in screen_raw.items():
        screening_results[date] = [
            {**c, "ts_code": c["code"]} for c in candidates
        ]
    total_candidates = sum(len(v) for v in screening_results.values())
    print(f"  Found {total_candidates} candidates across {len(screening_results)} trading days")

    # Step 3: Run backtest
    output_dir = cfg.get("output_dir", "output")
    output_path = str(Path(__file__).parent / output_dir)

    if args.variant == "ab":
        # A/B comparison mode: run all 3 variants
        print("\n=== A/B Comparison Mode ===")
        ab_results = run_ab_comparison(cfg, screening_results, daily_data)

        # Save detailed results for each variant
        for variant_key, variant_label_short in [("biased", "biased"), ("t1_only", "t1_only"), ("t1_cost", "t1_cost")]:
            save_results(ab_results[variant_key]["engine"], screening_results, output_path, variant_label=variant_label_short)

        # Save A/B comparison markdown
        save_ab_comparison(ab_results, output_path)
    else:
        # Single variant mode
        print(f"\nRunning backtest (variant: {args.variant})...")
        engine = BacktestEngine(cfg, variant=args.variant)
        engine.run(screening_results, daily_data)
        save_results(engine, screening_results, output_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
