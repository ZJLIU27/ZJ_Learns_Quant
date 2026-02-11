# b2_basic

## Summary
- Universe: China A-share main board only (exclude ChiNext and STAR).
- Selection: daily bars (T is the last completed trading day).
- Execution: minute bars, watchlist at 09:35.
- Transaction cost: 2.5 RMB per 10,000 RMB notional, minimum 5 RMB per order.

## Current Rules (as provided)
Daily filters on T and T-1:
1. J(T-1) < 20 (KDJ)
2. J(T) < 65 (KDJ)
3. T daily return > 4%
4. T volume >= 1.5 * T-1 volume
5. T upper shadow < 20% of full candle range

Intraday at T+1 09:35:
6. From candidates, pick top 3 by volume ratio (>20) and in a downtrend.
   - Volume ratio = current cumulative volume / avg cumulative volume
     at the same time over past 5 trading days.
7. Buy when price rises >= 3 ticks from intraday low.
   - If price jumps above 4 ticks, still buy at current price.
   - If a 1-minute order fails, retry on next minute with latest price.

Exit rules:
8. 14:45: if current price < buy-day low, stop loss (sell all).
9. If position return > 3%, sell 1/3. If return > 10%, sell another 1/3.
10. 14:45: if today is down and today's volume > yesterday and > 5-day avg, clear.

## Files
- `main.py`: strategy script for xtQMT (uses `get_market_data_ex`, `get_trade_detail_data`, `passorder`, etc.).

## Open Questions (need your confirmation)
1. Tick size: assume 0.01 RMB for all A-shares?
2. Backtest settings: start/end date, initial capital, slippage, benchmark.

## Backtest Settings (pending)
- Start date / end date
- Initial capital
- Slippage
- Benchmark

## QMT Notes
- Set the trading account in QMT; the script will use built-in `account` if `ACCOUNT_ID` is empty.
- Ensure daily and 1m data are available for the backtest universe.
- Strategy state is stored in a global `g` object (to avoid ContextInfo variable rollback across `handlebar`).
