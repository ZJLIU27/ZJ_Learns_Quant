# b2_a

## Summary
- Universe: China A-share main board only (exclude ChiNext and STAR).
- Selection: daily bars (T is the last completed trading day).
- Execution: minute bars, watchlist uses all daily candidates (no 09:35 volume-ratio filter).
- Entry model: parallel MA5/MA10 -> first cannon -> pullback -> below avg-price line rebound.

## Rules
Daily filters on T and T-1:
1. J(T-1) < 20 (KDJ)
2. J(T) < 65 (KDJ)
3. T daily return > 4%
4. T volume >= 1.5 * T-1 volume
5. T upper shadow < 20% of full candle range

Intraday at T+1:
6. Watchlist uses all daily candidates directly (no early-session volume-ratio ranking).
7. Entry pattern (1m bars):
   - Parallel zone: MA5 and MA10 stay close and flat in recent window.
   - First cannon: bullish breakout candle with volume >= 1.8 * volume MA5.
   - Pullback: 1-4 bars, cannot break MA10 tolerance and cannot retrace more than
     50% of first-cannon body; pullback volume should be no larger than first cannon.
   - Entry timing: price is still below intraday avg-price line, and the intraday
     line starts rebound (inflection): `prev2_close > prev_close < current_close`,
     where `prev_close` is near the recent local low; with
     volume >= 0.8 * first-cannon volume and > volume MA5.
   - If a buy order fails, retry on next minute with latest price.

Exit rules:
8. 14:45: if current price < pullback low at entry, stop loss (sell all).
9. If position return > 3%, sell 1/3. If return > 10%, sell another 1/3.
10. 14:45: if today is down and today's volume > yesterday and > 5-day avg, clear.

## Files
- `main.py`: strategy script for xtQMT (uses `get_market_data_ex`, `get_trade_detail_data`, `passorder`, etc.).

## QMT Notes
- Set the trading account in QMT; the script will use built-in `account` if `ACCOUNT_ID` is empty.
- Ensure daily and 1m data are available for the backtest universe.
- Strategy state is stored in a global `g` object (to avoid ContextInfo variable rollback across `handlebar`).
