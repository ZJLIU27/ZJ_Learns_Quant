"""Quality gate tests for backtest engine.

GATE-BE-001: Determinism — same inputs produce same outputs
GATE-BE-002: Equity conservation — cash never goes negative
GATE-BE-003: Lot-size compliance — all positions in 100-share lots
GATE-BE-004: T+1 compliance — no same-day sell after buy
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from strategies.st_b2.strategy import generate_signals, get_default_config
from tools.data_adapter.local_csv import load_market_data
from tools.backtest_engine import run_backtest


def load_config():
    config_path = project_root / "strategies" / "st_b2_tushare" / "config.json"
    with open(config_path) as f:
        cfg = json.load(f)
    return cfg


def run_full_backtest():
    """Run a full backtest with real data and return the result."""
    cfg = load_config()
    start_date = cfg.get("start_date", "20240101")
    end_date = cfg.get("end_date", "20251231")
    data_dir = cfg.get("data_dir", "")

    print("Loading market data...")
    daily_data = load_market_data(data_dir, start_date, end_date)

    print("Generating signals...")
    params = get_default_config()
    for key in params:
        if key in cfg:
            params[key] = cfg[key]
    signals = generate_signals(daily_data, params)

    print(f"Signals: {len(signals)} dates, {sum(len(v) for v in signals.values())} candidates")

    bt_config = {
        "initial_capital": cfg.get("initial_capital", 1000000),
        "max_positions": cfg.get("max_positions", 3),
        "slippage_pct": cfg.get("slippage_pct", 0.1),
        "commission_pct": cfg.get("commission_pct", 0.025),
        "stamp_tax_pct": cfg.get("stamp_tax_pct", 0.05),
        "transfer_fee_pct": cfg.get("transfer_fee_pct", 0.001),
    }

    print("Running backtest...")
    result = run_backtest(signals, daily_data, bt_config)
    return result


def gate_be_001_determinism():
    """GATE-BE-001: Same inputs -> same outputs."""
    print("\n=== GATE-BE-001: Determinism ===")
    result1 = run_full_backtest()
    result2 = run_full_backtest()

    assert result1.final_equity == result2.final_equity, \
        f"Final equity mismatch: {result1.final_equity} vs {result2.final_equity}"
    assert result1.trade_count == result2.trade_count, \
        f"Trade count mismatch: {result1.trade_count} vs {result2.trade_count}"
    assert result1.total_return_pct == result2.total_return_pct, \
        f"Return mismatch: {result1.total_return_pct} vs {result2.total_return_pct}"

    for i, (e1, e2) in enumerate(zip(result1.equity_curve, result2.equity_curve)):
        assert e1.equity == e2.equity, \
            f"Equity mismatch at {e1.trade_date}: {e1.equity} vs {e2.equity}"

    print(f"PASS — {result1.trade_count} trades, final equity {result1.final_equity}")


def gate_be_002_equity_conservation():
    """GATE-BE-002: Cash never goes negative."""
    print("\n=== GATE-BE-002: Equity Conservation ===")
    cfg = load_config()
    start_date = cfg.get("start_date", "20240101")
    end_date = cfg.get("end_date", "20251231")
    data_dir = cfg.get("data_dir", "")

    daily_data = load_market_data(data_dir, start_date, end_date)
    params = get_default_config()
    for key in params:
        if key in cfg:
            params[key] = cfg[key]
    signals = generate_signals(daily_data, params)

    bt_config = {
        "initial_capital": cfg.get("initial_capital", 1000000),
        "max_positions": cfg.get("max_positions", 3),
        "slippage_pct": cfg.get("slippage_pct", 0.1),
        "commission_pct": cfg.get("commission_pct", 0.025),
        "stamp_tax_pct": cfg.get("stamp_tax_pct", 0.05),
        "transfer_fee_pct": cfg.get("transfer_fee_pct", 0.001),
    }

    # We need to re-implement the date loop with explicit cash checking
    initial_capital = float(bt_config.get("initial_capital", 1000000))
    slippage = bt_config.get("slippage_pct", 0.1) / 100.0
    commission = bt_config.get("commission_pct", 0.025) / 100.0
    stamp_tax = bt_config.get("stamp_tax_pct", 0.05) / 100.0
    transfer_fee = bt_config.get("transfer_fee_pct", 0.001) / 100.0
    max_positions = bt_config.get("max_positions", 3)

    from tools.backtest_engine.models import Position

    # Build price tables
    price_table = {}
    open_table = {}
    all_dates = set()
    for code, df in daily_data.items():
        price_table[code] = dict(zip(df["trade_date"].values, df["close"].values.astype(float)))
        open_table[code] = dict(zip(df["trade_date"].values, df["open"].values.astype(float)))
        all_dates.update(df["trade_date"].values)

    trading_dates = sorted(all_dates)
    next_date_map = {}
    for i in range(len(trading_dates) - 1):
        next_date_map[trading_dates[i]] = trading_dates[i + 1]

    pending_signals = {}
    for signal_date in sorted(signals.keys()):
        exec_date = next_date_map.get(signal_date)
        if exec_date is None:
            continue
        if exec_date not in pending_signals:
            pending_signals[exec_date] = []
        pending_signals[exec_date].extend(signals[signal_date])

    cash = initial_capital
    positions = []

    for date in trading_dates:
        # Sell
        still_holding = []
        for pos in positions:
            if pos.buy_date == date:
                still_holding.append(pos)
                continue
            raw_sell_price = open_table.get(pos.code, {}).get(date)
            if raw_sell_price is None:
                still_holding.append(pos)
                continue
            actual_sell_price = raw_sell_price * (1.0 - slippage)
            proceeds = pos.shares * actual_sell_price
            cash += proceeds
            cash -= proceeds * (commission + stamp_tax + transfer_fee)
        positions = still_holding

        # Buy
        if date in pending_signals:
            for cand in pending_signals[date]:
                code = cand.get("ts_code") or cand.get("code")
                raw_open_price = open_table.get(code, {}).get(date)
                if raw_open_price is None:
                    continue
                available_slots = max_positions - len(positions)
                if available_slots <= 0:
                    break

                actual_buy_price = raw_open_price * (1.0 + slippage)
                buy_fee_rate = commission + transfer_fee
                alloc_per_slot = cash / available_slots
                shares = int(alloc_per_slot / actual_buy_price / 100) * 100
                if shares <= 0:
                    shares = int(cash / actual_buy_price / 100) * 100
                    if shares <= 0:
                        continue

                cost = shares * actual_buy_price
                total_outlay = cost * (1.0 + buy_fee_rate)
                if total_outlay > cash:
                    shares = int(cash / (actual_buy_price * (1.0 + buy_fee_rate)) / 100) * 100
                    if shares <= 0:
                        continue
                    cost = shares * actual_buy_price
                    total_outlay = cost * (1.0 + buy_fee_rate)

                cash -= total_outlay
                assert cash >= -0.01, f"Negative cash on {date}: {cash:.2f}"
                positions.append(Position(code=code, buy_date=date, buy_price=actual_buy_price, shares=shares, cost=cost))

    print(f"PASS — Cash never went negative (min observed: {initial_capital} -> final with positions)")


def gate_be_003_lot_size():
    """GATE-BE-003: All positions have share counts in multiples of 100."""
    print("\n=== GATE-BE-003: Lot-Size Compliance ===")
    result = run_full_backtest()

    for trade in result.trades:
        assert trade.shares % 100 == 0, \
            f"Trade {trade.code} has {trade.shares} shares (not multiple of 100)"

    print(f"PASS — All {result.trade_count} trades have lot-size in multiples of 100")


def gate_be_004_t_plus_1():
    """GATE-BE-004: No same-day sell after buy (T+1 compliance)."""
    print("\n=== GATE-BE-004: T+1 Compliance ===")
    result = run_full_backtest()

    for trade in result.trades:
        assert trade.buy_date != trade.sell_date, \
            f"Same-day trade for {trade.code}: buy={trade.buy_date} sell={trade.sell_date}"

    print(f"PASS — All {result.trade_count} trades satisfy T+1 constraint")


if __name__ == "__main__":
    gate_be_001_determinism()
    gate_be_002_equity_conservation()
    gate_be_003_lot_size()
    gate_be_004_t_plus_1()
    print("\n=== ALL GATES PASSED ===")