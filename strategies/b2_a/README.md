# b2_a

## Summary
- Universe: China A-share main board only (exclude ChiNext and STAR).
- Selection: daily bars (T is the last completed trading day).
- Execution: day-bar compatible; build watchlist each trading day (09:35 or fallback in coarse bars).
- Entry model: buy top 3 candidates after full daily graphic-pattern filter and daily volume-ratio ranking.

## Rules
Daily filters on T and T-1:
1. J(T-1) < 20 (KDJ)
2. J(T) < 65 (KDJ)
3. T daily return > 4%
4. T volume >= 1.5 * T-1 volume
5. T upper shadow < 20% of full candle range

Intraday at T+1:
6. Graphic-pattern filter is applied in selection layer (on T-day daily bars):
   - Parallel zone: MA5/MA10 close and flat.
   - First cannon: breakout bullish bar with strong volume.
   - Pullback: 1-6 bars, only require close not below Zhixing long/short line
     (`(MA14+MA28+MA57+MA114)/4`), while still recording pullback range and shrink-volume signal.
   - Second-cannon rebound: rebound inflection up (`prev2_close > prev_close < current_close`).
7. Rank candidates by daily volume ratio:
   - `volume(T) / avg volume(T-1..T-5)`.
8. Select top 3 by this ranking, then place buy orders at 09:35.
   - In non-intraday bar backtests, strategy uses fallback trigger on first bar of day.
   - If a 1-minute order fails, retry on next minute with latest price.

Exit rules:
9. 14:45: if current price < entry-day stop anchor, stop loss (sell all).
   - For 09:35 direct entry, anchor defaults to buy price.
10. If position return > 3%, sell 1/3. If return > 10%, sell another 1/3.
11. 14:45: if today is down and today's volume > yesterday and > 5-day avg, clear.

## Files
- `main.py`: strategy script for xtQMT (uses `get_market_data_ex`, `get_trade_detail_data`, `passorder`, etc.).

## QMT Notes
- Set the trading account in QMT; the script will use built-in `account` if `ACCOUNT_ID` is empty.
- Ensure daily and 1m data are available for the backtest universe.
- Strategy state is stored in a global `g` object (to avoid ContextInfo variable rollback across `handlebar`).
