"""
st_b2_tushare - KDJ Reversal Stock Screening + Backtesting (Tushare Edition)

Independent research tool, decoupled from QMT.
Uses tushare daily data to screen stocks and run complete trading simulation.

Strategy logic (ported from strategies/st_b2):
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


# ---------------------------------------------------------------------------
# Local Data Layer (CSV files from tushare export)
# ---------------------------------------------------------------------------

def load_local_data(data_dir: str, start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """Load daily data from local CSV files.

    Expected structure: data_dir/<code>.csv (e.g. 000001.csv)
    Expected columns: date,open,close,high,low,volume
    Date format: YYYY-MM-DD (auto-converted to YYYYMMDD)

    Returns {stock_code: DataFrame} with columns normalized to match tushare format.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        print(f"Error: data directory not found: {data_dir}")
        sys.exit(1)

    start_fmt = start_date  # YYYYMMDD
    end_fmt = end_date

    result = {}
    csv_files = sorted(data_path.glob("*.csv"))
    print(f"Loading local data from {data_dir} ({len(csv_files)} files)...")

    for csv_file in csv_files:
        code = csv_file.stem  # e.g. "000001"

        # Filter to main board only
        if not is_main_board(code):
            continue

        try:
            df = pd.read_csv(csv_file, dtype={"date": str})
        except Exception:
            continue

        if df.empty:
            continue

        # Normalize columns: date → trade_date (YYYYMMDD), volume → vol
        df = df.rename(columns={"date": "trade_date", "volume": "vol"})

        # Convert date format YYYY-MM-DD → YYYYMMDD
        df["trade_date"] = df["trade_date"].str.replace("-", "")

        # Filter by date range
        df = df[(df["trade_date"] >= start_fmt) & (df["trade_date"] <= end_fmt)]
        df = df.sort_values("trade_date").reset_index(drop=True)

        if not df.empty:
            result[code] = df

    print(f"  Loaded {len(result)} main board stocks.")
    return result


# ---------------------------------------------------------------------------
# KDJ Indicator (ported from strategies/st_b2/main.py)
# ---------------------------------------------------------------------------

def compute_kdj(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    n: int = 9,
    k_init: float = 50.0,
    d_init: float = 50.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute KDJ indicator arrays.

    Returns (K, D, J) arrays, same length as input.
    Formula matches TongDaXin SMA convention:
      RSV = (CLOSE - LLV(LOW,N)) / (HHV(HIGH,N) - LLV(LOW,N)) * 100
      K = SMA(RSV, 3, 1)  i.e.  K = (2*K_prev + RSV) / 3
      D = SMA(K, 3, 1)    i.e.  D = (2*D_prev + K) / 3
      J = 3*K - 2*D
    """
    length = len(closes)
    k_arr = np.zeros(length)
    d_arr = np.zeros(length)
    j_arr = np.zeros(length)

    k_prev = k_init
    d_prev = d_init

    for i in range(length):
        start = max(0, i - n + 1)
        low_n = np.min(lows[start : i + 1])
        high_n = np.max(highs[start : i + 1])

        if high_n == low_n:
            rsv = 0.0
        else:
            rsv = (closes[i] - low_n) / (high_n - low_n) * 100.0

        k = (2.0 * k_prev + rsv) / 3.0
        d = (2.0 * d_prev + k) / 3.0
        j = 3.0 * k - 2.0 * d

        k_arr[i] = k
        d_arr[i] = d
        j_arr[i] = j

        k_prev = k
        d_prev = d

    return k_arr, d_arr, j_arr


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

def screen_stocks(
    daily_data: dict[str, pd.DataFrame],
    kdj_n: int,
    kdj_init: float,
    j_pre_max: float,
    j_now_max: float,
    daily_return_min_pct: float,
    vol_ratio_min: float,
) -> dict[str, list[dict]]:
    """Run st_b2 screening on all stocks.

    Returns {trade_date: [stock_info_dict, ...]} for each date with candidates.
    """
    min_bars = kdj_n + 2  # Need at least N+2 bars for KDJ + previous J

    # Collect all trade dates
    all_dates = set()
    for df in daily_data.values():
        all_dates.update(df["trade_date"].tolist())
    all_dates = sorted(all_dates)

    # Pre-compute per-stock data: index by trade_date for fast lookup
    stock_data = {}
    for code, df in daily_data.items():
        if len(df) < min_bars:
            continue
        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        vols = df["vol"].values.astype(float)
        dates = df["trade_date"].values

        k_arr, d_arr, j_arr = compute_kdj(closes, highs, lows, kdj_n, kdj_init)

        # Build per-date lookup: only store where we have enough history
        for i in range(min_bars - 1, len(df)):
            date = dates[i]
            prev_close = closes[i - 1]
            if prev_close <= 0:
                continue
            daily_ret = (closes[i] / prev_close - 1.0) * 100.0
            vol_ratio = vols[i] / vols[i - 1] if vols[i - 1] > 0 else 0.0

            # Apply screening conditions
            if j_arr[i - 1] >= j_pre_max:
                continue
            if j_arr[i] > j_now_max:
                continue
            if daily_ret <= daily_return_min_pct:
                continue
            if vol_ratio < vol_ratio_min:
                continue

            if date not in stock_data:
                stock_data[date] = []
            stock_data[date].append({
                "ts_code": code,
                "close": float(closes[i]),
                "daily_return_pct": round(daily_ret, 2),
                "vol_ratio": round(vol_ratio, 2),
                "j_now": round(float(j_arr[i]), 2),
                "j_prev": round(float(j_arr[i - 1]), 2),
            })

    # Sort candidates by daily return (descending) per date
    result = {}
    for date in sorted(stock_data.keys()):
        candidates = sorted(stock_data[date], key=lambda x: x["daily_return_pct"], reverse=True)
        result[date] = candidates

    return result


# ---------------------------------------------------------------------------
# Backtest Engine - Complete Trading Simulation
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Simulates real trading with capital allocation, position management, T+1 selling."""

    def __init__(self, config: dict):
        self.initial_capital = config.get("initial_capital", 1000000)
        self.max_positions = config.get("max_positions", 3)
        self.cash = float(self.initial_capital)
        self.positions: list[dict] = []  # active positions
        self.closed_trades: list[dict] = []  # completed trades
        self.equity_curve: list[dict] = []  # daily equity snapshot

    def _buy(self, code: str, price: float, trade_date: str) -> bool:
        """Buy a stock. Equal-weight allocation from available cash."""
        available_slots = self.max_positions - len(self.positions)
        if available_slots <= 0:
            return False

        # Allocate: available cash / remaining slots
        alloc_per_slot = self.cash / available_slots
        # Round down to nearest 100 shares (A-share lot size)
        shares = int(alloc_per_slot / price / 100) * 100
        if shares <= 0:
            return False

        cost = shares * price
        if cost > self.cash:
            shares = int(self.cash / price / 100) * 100
            if shares <= 0:
                return False
            cost = shares * price

        self.cash -= cost
        self.positions.append({
            "ts_code": code,
            "buy_date": trade_date,
            "buy_price": price,
            "shares": shares,
            "cost": cost,
        })
        return True

    def _sell_all(self, price_lookup: dict[str, float], trade_date: str):
        """Sell all positions (T+1 rule: only sell positions bought before today)."""
        still_holding = []
        for pos in self.positions:
            # T+1: can't sell on buy day (but in daily simulation, sell happens next day anyway)
            price = price_lookup.get(pos["ts_code"])
            if price is None:
                # Can't find price, keep holding
                still_holding.append(pos)
                continue

            proceeds = pos["shares"] * price
            self.cash += proceeds
            ret_pct = (price / pos["buy_price"] - 1.0) * 100.0

            self.closed_trades.append({
                "ts_code": pos["ts_code"],
                "buy_date": pos["buy_date"],
                "buy_price": pos["buy_price"],
                "sell_date": trade_date,
                "sell_price": price,
                "shares": pos["shares"],
                "return_pct": round(ret_pct, 2),
                "pnl": round(proceeds - pos["cost"], 2),
            })
        self.positions = still_holding

    def run(self, screening_results: dict[str, list[dict]], daily_data: dict[str, pd.DataFrame]):
        """Run backtest over all screening dates.

        Flow per trade_date:
          1. Sell all existing positions at today's open (simplified: use close)
          2. Check today's screening candidates
          3. Buy top candidates (up to max_positions)
        """
        all_dates = sorted(screening_results.keys())
        if not all_dates:
            print("No screening results to backtest.")
            return

        # Build price lookup: {ts_code: {trade_date: close_price}}
        price_table: dict[str, dict[str, float]] = {}
        all_trade_dates = set()
        for code, df in daily_data.items():
            price_table[code] = dict(zip(df["trade_date"].values, df["close"].values.astype(float)))
            all_trade_dates.update(df["trade_date"].values)

        # Determine the actual last trading date for final liquidation
        actual_last_date = max(all_trade_dates) if all_trade_dates else all_dates[-1]

        prev_date = None
        for date in all_dates:
            # Step 1: Sell all positions from previous day
            if prev_date is not None and self.positions:
                sell_prices = {}
                for pos in self.positions:
                    p = price_table.get(pos["ts_code"], {}).get(date)
                    if p is not None:
                        sell_prices[pos["ts_code"]] = p
                self._sell_all(sell_prices, date)

            # Step 2: Buy from today's candidates
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

        # Sell remaining positions at actual last trading date (not last screening date)
        if self.positions:
            last_date = actual_last_date
            sell_prices = {}
            for pos in self.positions:
                p = price_table.get(pos["ts_code"], {}).get(last_date, pos["buy_price"])
                sell_prices[pos["ts_code"]] = p
            self._sell_all(sell_prices, last_date)

    def compute_stats(self) -> dict:
        """Compute backtest summary statistics."""
        if not self.closed_trades:
            return {
                "total_return_pct": 0.0,
                "win_rate": 0.0,
                "max_drawdown_pct": 0.0,
                "trade_count": 0,
                "final_equity": self.cash,
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
# Output
# ---------------------------------------------------------------------------

def save_results(engine: BacktestEngine, screening_results: dict, output_dir: str):
    """Save trade records CSV and summary stats."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Trade records CSV
    if engine.closed_trades:
        trades_df = pd.DataFrame(engine.closed_trades)
        trades_path = out_path / f"trades_{timestamp}.csv"
        trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
        print(f"Trade records saved to: {trades_path}")

    # Equity curve CSV
    if engine.equity_curve:
        eq_df = pd.DataFrame(engine.equity_curve)
        eq_path = out_path / f"equity_{timestamp}.csv"
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
    summary_lines = [
        "=" * 50,
        "  st_b2 Tushare Backtest Summary",
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

    summary_path = out_path / f"summary_{timestamp}.txt"
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
        daily_data = load_local_data(data_dir, start_date, end_date)
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

    # Step 3: Run screening
    print("Running st_b2 screening...")
    screening_results = screen_stocks(
        daily_data=daily_data,
        kdj_n=cfg.get("kdj_n", 9),
        kdj_init=cfg.get("kdj_init", 50.0),
        j_pre_max=cfg.get("j_pre_max", 20.0),
        j_now_max=cfg.get("j_now_max", 65.0),
        daily_return_min_pct=cfg.get("daily_return_min_pct", 4.0),
        vol_ratio_min=cfg.get("vol_ratio_min", 1.1),
    )
    total_candidates = sum(len(v) for v in screening_results.values())
    print(f"  Found {total_candidates} candidates across {len(screening_results)} trading days")

    # Step 4: Run backtest
    print("Running backtest simulation...")
    engine = BacktestEngine(cfg)
    engine.run(screening_results, daily_data)

    # Step 5: Save results
    output_dir = cfg.get("output_dir", "output")
    output_path = str(Path(__file__).parent / output_dir)
    save_results(engine, screening_results, output_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
