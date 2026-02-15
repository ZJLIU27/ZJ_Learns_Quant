# st_dj20

## Strategy Type
- xtQMT built-in stock picker script (no order placement).

## Formula Mapping
Source: `ref/st_dj20.md`

1. `short = 100 * (C - LLV(L,3)) / (HHV(C,3) - LLV(L,3))`
2. `long = 100 * (C - LLV(L,21)) / (HHV(C,21) - LLV(L,21))`
3. `TJ1 = NOT(INBLOCK('创业板') OR INBLOCK('科创板'))`
4. Final: `long >= 70 AND (long - short) >= 20 AND TJ1`

When denominator is zero, the script treats the indicator value as `0`.

## Universe
- Main-board A shares only (`600/601/603/605/000/001/002`).
- ChiNext (`300*`) and STAR (`688*/689*`) are excluded.

## Runtime Behavior
- `init()` loads universe and binds account `testS`.
- `handlebar()` runs once per trading day.
- On each new day `T+1`, it uses previous trading day `T` daily bars to compute candidates.
- Result is printed in logs:
  - candidate count
  - first 20 stock codes

## Files
- `main.py`: runnable xtQMT script.
