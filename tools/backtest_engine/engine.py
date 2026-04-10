"""Independent backtest engine with T+1 execution and A-share cost model.

Pipeline: signals -> pending queue -> date loop (sell -> buy -> snapshot) -> BacktestResult

Signal interface: {trade_date: [{code, ...}]} — any strategy producing this format works.
Market data interface: {code: DataFrame(trade_date, open, high, low, close, vol)}

Cost model (A-share):
  Buy side:  price * (1 + slippage), deduct commission + transfer_fee
  Sell side: price * (1 - slippage), deduct commission + stamp_tax + transfer_fee
"""

import pandas as pd

from .models import BacktestResult, EquitySnapshot, Position, Trade
from .stats import calc_avg_return, calc_max_drawdown, calc_median_return, calc_total_return, calc_win_rate


def run_backtest(
    signals: dict[str, list[dict]],
    market_data: dict[str, pd.DataFrame],
    config: dict,
    trading_dates: list[str] | None = None,
) -> BacktestResult:
    """Run backtest with T+1 execution and A-share cost model.

    Args:
        signals: {trade_date: [{code, ...}]} from any strategy.
        market_data: {code: DataFrame(trade_date, open, high, low, close, vol)}.
        config: Backtest configuration with keys:
            initial_capital (default 1000000)
            max_positions (default 3)
            slippage_pct (default 0.1) — as percentage, e.g. 0.1 means 0.1%
            commission_pct (default 0.025)
            stamp_tax_pct (default 0.05)
            transfer_fee_pct (default 0.001)
        trading_dates: Optional sorted list of trading dates.
            If None, extracted from market_data.

    Returns:
        BacktestResult with trades, equity_curve, and computed statistics.
    """
    # Config
    initial_capital = float(config.get("initial_capital", 1000000))
    max_positions = config.get("max_positions", 3)
    slippage = config.get("slippage_pct", 0.1) / 100.0
    commission = config.get("commission_pct", 0.025) / 100.0
    stamp_tax = config.get("stamp_tax_pct", 0.05) / 100.0
    transfer_fee = config.get("transfer_fee_pct", 0.001) / 100.0

    # Build price tables
    price_table: dict[str, dict[str, float]] = {}   # code -> {date: close}
    open_table: dict[str, dict[str, float]] = {}     # code -> {date: open}
    all_dates: set[str] = set()
    for code, df in market_data.items():
        price_table[code] = dict(zip(df["trade_date"].values, df["close"].values.astype(float)))
        open_table[code] = dict(zip(df["trade_date"].values, df["open"].values.astype(float)))
        all_dates.update(df["trade_date"].values)

    if not all_dates:
        return BacktestResult(
            initial_capital=initial_capital, final_equity=initial_capital,
            total_return_pct=0.0, max_drawdown_pct=0.0, win_rate=0.0,
            trade_count=0, avg_return_pct=0.0, median_return_pct=0.0,
        )

    # Build sorted trading dates and next-date map
    if trading_dates is None:
        trading_dates = sorted(all_dates)
    next_date_map = {}
    for i in range(len(trading_dates) - 1):
        next_date_map[trading_dates[i]] = trading_dates[i + 1]

    # Build pending signal queue: execution_date -> [candidates]
    pending_signals: dict[str, list[dict]] = {}
    for signal_date in sorted(signals.keys()):
        exec_date = next_date_map.get(signal_date)
        if exec_date is None:
            continue  # No T+1 date available
        if exec_date not in pending_signals:
            pending_signals[exec_date] = []
        pending_signals[exec_date].extend(signals[signal_date])

    # Initialize state
    cash = initial_capital
    positions: list[Position] = []
    closed_trades: list[Trade] = []
    equity_curve: list[EquitySnapshot] = []

    # Date loop
    for date in trading_dates:
        # Step 1: Sell all positions at today's open price (T+1: not on buy day)
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
            # Deduct sell-side fees
            cash -= proceeds * (commission + stamp_tax + transfer_fee)

            gross_ret = (raw_sell_price / pos.buy_price - 1.0) * 100.0
            net_ret = (actual_sell_price / pos.buy_price - 1.0) * 100.0
            cost_pct = ((commission + stamp_tax + transfer_fee) + slippage * 2) * 100.0

            closed_trades.append(Trade(
                code=pos.code,
                buy_date=pos.buy_date,
                buy_price=pos.buy_price,
                sell_date=date,
                sell_price=actual_sell_price,
                shares=pos.shares,
                gross_return_pct=round(gross_ret, 2),
                net_return_pct=round(net_ret, 2),
                cost_pct=round(cost_pct, 2),
            ))
        positions = still_holding

        # Step 2: Buy from pending signals at today's open price
        if date in pending_signals:
            candidates = pending_signals[date]
            for cand in candidates:
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

                positions.append(Position(
                    code=code,
                    buy_date=date,
                    buy_price=actual_buy_price,
                    shares=shares,
                    cost=cost,
                ))

        # Step 3: Snapshot equity
        total_equity = cash
        for pos in positions:
            close_price = price_table.get(pos.code, {}).get(date, pos.buy_price)
            total_equity += pos.shares * close_price

        equity_curve.append(EquitySnapshot(
            trade_date=date,
            equity=round(total_equity, 2),
            cash=round(cash, 2),
            positions=len(positions),
        ))

    # Final liquidation at last trading date's close
    if positions and equity_curve:
        last_date = trading_dates[-1]
        for pos in positions:
            raw_close = price_table.get(pos.code, {}).get(last_date, pos.buy_price)
            if raw_close is not None:
                actual_sell_price = raw_close * (1.0 - slippage)
                proceeds = pos.shares * actual_sell_price
                cash += proceeds
                cash -= proceeds * (commission + stamp_tax + transfer_fee)

                # Only record trade if it satisfies T+1 (bought before last date)
                if pos.buy_date != last_date:
                    gross_ret = (raw_close / pos.buy_price - 1.0) * 100.0
                    net_ret = (actual_sell_price / pos.buy_price - 1.0) * 100.0
                    cost_pct = ((commission + stamp_tax + transfer_fee) + slippage * 2) * 100.0

                    closed_trades.append(Trade(
                        code=pos.code,
                        buy_date=pos.buy_date,
                        buy_price=pos.buy_price,
                        sell_date=last_date,
                        sell_price=actual_sell_price,
                        shares=pos.shares,
                        gross_return_pct=round(gross_ret, 2),
                        net_return_pct=round(net_ret, 2),
                        cost_pct=round(cost_pct, 2),
                    ))

    # Compute final equity
    final_equity = equity_curve[-1].equity if equity_curve else cash
    # Adjust final equity for any positions liquidated at end
    if positions and equity_curve:
        final_equity = round(cash, 2)

    return BacktestResult(
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return_pct=calc_total_return(initial_capital, final_equity),
        max_drawdown_pct=calc_max_drawdown(equity_curve),
        win_rate=calc_win_rate(closed_trades),
        trade_count=len(closed_trades),
        avg_return_pct=calc_avg_return(closed_trades),
        median_return_pct=calc_median_return(closed_trades),
        trades=closed_trades,
        equity_curve=equity_curve,
    )