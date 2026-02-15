# st_b1

## Strategy Type
- xtQMT built-in stock picker script (no order placement).

## Formula Mapping
Source: `ref/st_b1.md`

1. `M1=14, M2=28, M3=57, M4=114`
2. `short_line = EMA(EMA(C,10),10)`
3. `duokong_line = (MA(C,14)+MA(C,28)+MA(C,57)+MA(C,114))/4`
4. KDJ:
   - `RSV=(C-LLV(L,9))/(HHV(H,9)-LLV(L,9))*100`
   - `K=SMA(RSV,3,1)`
   - `D=SMA(K,3,1)`
   - `J=3*K-2*D`
5. Conditions:
   - `J < 20`
   - `C > duokong_line`
   - `C < short_line`
   - `short_line > duokong_line`
   - `MIN(C,O)-L > H-MAX(C,O)` OR abs diff `< 0.1`
   - exclude STAR and Beijing exchange
   - float market value `> 50` (100 million RMB)

## Universe
- Main-board A shares only (`600/601/603/605/000/001/002`).
- ChiNext (`300*`) and STAR (`688*/689*`) are excluded.
- Beijing exchange is also excluded by prefix filter.

## Float Market Value
- The script tries multiple data paths:
  1. `get_market_data_ex` extended fields (if available).
  2. `xtdata.get_instrument_detail` keys.
  3. `float_shares * close` fallback (heuristic unit handling).
- If float market value cannot be obtained for a stock, that stock is filtered out (strict mode, matches formula intent).

## Runtime Behavior
- `init()` loads universe and binds account `testS`.
- `handlebar()` runs once per trading day.
- On each new day `T+1`, it uses previous trading day `T` daily bars to compute candidates.
- Result is printed in logs:
  - candidate count
  - first 20 stock codes
  - filter stats including float market value missing/fail counts

## Files
- `main.py`: runnable xtQMT script.
