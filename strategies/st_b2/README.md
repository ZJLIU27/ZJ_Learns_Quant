# st_b2

## Strategy Type
- xtQMT built-in stock picker script (no order placement).

## Formula Mapping
Source: `ref/st_b2.md`

1. `ZF`: `(CLOSE / REF(CLOSE,1) - 1) * 100 > 4`
2. `VOL_COND`: `VOL >= REF(VOL,1) * 1.1`
3. `J_NOW`: `J <= 65`
4. `J_PRE`: `REF(J,1) < 20`
5. Final: all conditions above are true.

KDJ is implemented with TongDaXin style:
- `RSV=(C-LLV(L,9))/(HHV(H,9)-LLV(L,9))*100`
- `K=SMA(RSV,3,1)`
- `D=SMA(K,3,1)`
- `J=3*K-2*D`

## Universe
- Main-board A shares only (`600/601/603/605/000/001/002`).
- ChiNext (`300*`) and STAR (`688*/689*`) are excluded.
- This also satisfies the baseline requirement to exclude ChiNext/STAR.

## Runtime Behavior
- `init()` loads universe and binds account `testS`.
- `handlebar()` runs once per trading day.
- On each new day `T+1`, it uses previous trading day `T` daily bars to compute candidates.
- Result is printed in logs:
  - candidate count
  - first 20 stock codes

## Files
- `main.py`: runnable xtQMT script.
