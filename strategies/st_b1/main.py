#coding:gbk
"""
Stock picker: st_b1 (TongDaXin formula -> xtQMT)

Formula:
M1:=14; M2:=28; M3:=57; M4:=114;
short_line := EMA(EMA(C,10),10);
duokong_line := (MA(C,14)+MA(C,28)+MA(C,57)+MA(C,114))/4;
RSV := (C-LLV(L,9))/(HHV(H,9)-LLV(L,9))*100;
K := SMA(RSV,3,1); D := SMA(K,3,1); J := 3*K-2*D;

COND1: J < 20
COND2: C > duokong_line
COND3: C < short_line
COND4: short_line > duokong_line
COND5: MIN(C,O)-L > H-MAX(C,O) OR ABS( (MIN(C,O)-L) - (H-MAX(C,O)) ) < 0.1
COND6: exclude STAR + Beijing exchange
COND7: float market value > 50 (100 million RMB)
XG: COND1 AND COND2 AND COND3 AND COND4 AND COND5 AND COND6 AND COND7
"""

import datetime

try:
    from xtquant import xtdata
except Exception:
    xtdata = None


class G:
    pass


g = G()

STRATEGY_NAME = "st_b1"
ACCOUNT_ID = "testS"
ACCOUNT_TYPE = "stock"

M1 = 14
M2 = 28
M3 = 57
M4 = 114

EMA_N = 10
KDJ_N = 9
KDJ_INIT = 50.0

SHADOW_ABS_DIFF_MAX = 0.1
FLOAT_MV_MIN_100M = 50.0
DAILY_BAR_COUNT = 180

BATCH_FETCH_CHUNK_SIZE = 200
MAX_LOG_CODES = 20

FORCE_MAIN_BOARD_UNIVERSE = True
MIN_UNIVERSE_SIZE = 100
UNIVERSE_SECTOR_NAMES = (
    "\u6caa\u6df1A\u80a1",
    "A\u80a1",
)

# Try these names for float market value.
FLOAT_MV_FIELD_CANDIDATES = (
    "float_mv",
    "float_market_value",
    "negotiable_mv",
    "circulating_market_value",
)
FLOAT_MV_KEY_CANDIDATES = (
    "float_mv",
    "float_market_value",
    "negotiable_mv",
    "circulating_market_value",
    "floatmktvalue",
    "marketvalue",
    "mktcapfloat",
    "liutongshizhi",
)
FLOAT_SHARES_KEY_CANDIDATES = (
    "float_share",
    "float_shares",
    "negotiable_shares",
    "circulating_shares",
    "floatcapital",
    "liutongguben",
)


def init(context):
    g.account_id = ACCOUNT_ID or globals().get("account", "")
    if g.account_id and hasattr(context, "set_account"):
        try:
            context.set_account(g.account_id)
        except Exception:
            _log("set_account failed; continue")

    g.universe = get_universe(context)
    if g.universe and hasattr(context, "set_universe"):
        try:
            context.set_universe(g.universe)
        except Exception:
            pass

    g.last_run_trade_date = ""
    g.latest_candidates = []
    g.float_mv_cache = {}
    g.float_mv_cache_date = ""
    g.logged_once = set()

    _log("init done, universe={0}".format(len(g.universe)))


def handlebar(context):
    now = _get_current_dt(context)
    if now is None:
        return

    trade_date = now.strftime("%Y%m%d")
    if g.last_run_trade_date == trade_date:
        return
    g.last_run_trade_date = trade_date

    if not g.universe:
        g.universe = get_universe(context)

    t_date = get_trading_calendar_prev_date(context, trade_date)
    g.float_mv_cache = {}
    g.float_mv_cache_date = t_date

    candidates = build_candidates(context, t_date)
    g.latest_candidates = candidates

    _log(
        "selection trade_date={0} formula_date={1} candidates={2}".format(
            trade_date, t_date, len(candidates)
        )
    )
    if candidates:
        _log("codes={0}".format(",".join(candidates[:MAX_LOG_CODES])))


def build_candidates(context, t_date):
    candidates = []
    stats = {
        "total": len(g.universe),
        "bars_short": 0,
        "kdj_fail": 0,
        "price_duokong_fail": 0,
        "price_short_fail": 0,
        "line_order_fail": 0,
        "shadow_fail": 0,
        "float_mv_missing": 0,
        "float_mv_fail": 0,
    }

    daily_batch = fetch_daily_bars_batch(context, g.universe, t_date, DAILY_BAR_COUNT)
    min_bars = max(M4, KDJ_N + 2, EMA_N * 3)

    for code in g.universe:
        bars = daily_batch.get(code)
        if not bars:
            bars = fetch_daily_bars(context, code, t_date, DAILY_BAR_COUNT)
        if len(bars) < min_bars:
            stats["bars_short"] += 1
            continue

        closes = [b["close"] for b in bars]
        bar_t = bars[-1]

        short_line = calc_double_ema_last(closes, EMA_N)
        ma1 = calc_ma_last(closes, M1)
        ma2 = calc_ma_last(closes, M2)
        ma3 = calc_ma_last(closes, M3)
        ma4 = calc_ma_last(closes, M4)
        if (
            short_line is None
            or ma1 is None
            or ma2 is None
            or ma3 is None
            or ma4 is None
        ):
            stats["bars_short"] += 1
            continue
        duokong_line = (ma1 + ma2 + ma3 + ma4) / 4.0

        _, _, j_list = compute_kdj(bars, KDJ_N, KDJ_INIT, KDJ_INIT)
        if not j_list or j_list[-1] >= 20.0:
            stats["kdj_fail"] += 1
            continue

        c = bar_t["close"]
        o = bar_t["open"]
        h = bar_t["high"]
        l = bar_t["low"]

        if c <= duokong_line:
            stats["price_duokong_fail"] += 1
            continue
        if c >= short_line:
            stats["price_short_fail"] += 1
            continue
        if short_line <= duokong_line:
            stats["line_order_fail"] += 1
            continue

        lower_shadow = min(c, o) - l
        upper_shadow = h - max(c, o)
        shadow_ok = (lower_shadow > upper_shadow) or (
            abs(lower_shadow - upper_shadow) < SHADOW_ABS_DIFF_MAX
        )
        if not shadow_ok:
            stats["shadow_fail"] += 1
            continue

        float_mv_100m = get_float_mv_100m(context, code, t_date, c)
        if float_mv_100m is None:
            stats["float_mv_missing"] += 1
            continue
        if float_mv_100m <= FLOAT_MV_MIN_100M:
            stats["float_mv_fail"] += 1
            continue

        candidates.append(code)

    _log(
        "filter_stats total={0} bars_short={1} kdj_fail={2} price_duokong_fail={3} "
        "price_short_fail={4} line_order_fail={5} shadow_fail={6} "
        "float_mv_missing={7} float_mv_fail={8} pass={9}".format(
            stats["total"],
            stats["bars_short"],
            stats["kdj_fail"],
            stats["price_duokong_fail"],
            stats["price_short_fail"],
            stats["line_order_fail"],
            stats["shadow_fail"],
            stats["float_mv_missing"],
            stats["float_mv_fail"],
            len(candidates),
        )
    )
    return candidates


def get_float_mv_100m(context, code, trade_date, close_price):
    key = "{0}|{1}".format(code, trade_date)
    if key in g.float_mv_cache:
        return g.float_mv_cache[key]

    # 1) Try market-data extended fields.
    value = _try_float_mv_from_market_data(context, code, trade_date)
    if value is not None:
        g.float_mv_cache[key] = value
        return value

    # 2) Try instrument detail.
    value = _try_float_mv_from_detail(code, close_price)
    g.float_mv_cache[key] = value
    return value


def _try_float_mv_from_market_data(context, code, trade_date):
    end_date = _normalize_trade_date(trade_date)
    end_candidates = [end_date, end_date + "150000", end_date + "235959", ""]

    for field in FLOAT_MV_FIELD_CANDIDATES:
        for end_ts in end_candidates:
            try:
                data = context.get_market_data_ex(
                    [field],
                    [code],
                    period="1d",
                    start_time="",
                    end_time=end_ts,
                    count=1,
                    dividend_type="none",
                    fill_data=True,
                    subscribe=False,
                )
            except Exception:
                continue

            try:
                df = data.get(code)
            except Exception:
                df = None
            if df is None or df.empty:
                continue

            value = None
            try:
                if field in df.columns:
                    value = _to_float(df[field].iloc[-1])
            except Exception:
                value = None

            if value is None:
                try:
                    row = df.iloc[-1]
                    value = _to_float(row.get(field))
                except Exception:
                    value = None

            value = normalize_mv_to_100m(value)
            if value is not None:
                return value
    return None


def _try_float_mv_from_detail(code, close_price):
    detail = None
    if xtdata is not None and hasattr(xtdata, "get_instrument_detail"):
        try:
            detail = xtdata.get_instrument_detail(code)
        except Exception:
            detail = None

    if detail is None and "get_instrument_detail" in globals():
        func = globals().get("get_instrument_detail")
        if callable(func):
            try:
                detail = func(code)
            except Exception:
                detail = None

    if not isinstance(detail, dict):
        return None

    mv_val = extract_number_by_keys(detail, FLOAT_MV_KEY_CANDIDATES)
    mv_val = normalize_mv_to_100m(mv_val)
    if mv_val is not None:
        return mv_val

    shares = extract_number_by_keys(detail, FLOAT_SHARES_KEY_CANDIDATES)
    if shares is None or close_price <= 0:
        _log_once(
            "float_mv_missing_path",
            "float market value unavailable via market_data and instrument_detail",
        )
        return None

    # Heuristic: some APIs store float shares in 10k-share units.
    if shares < 1e7:
        shares = shares * 10000.0

    mv = shares * close_price
    value = normalize_mv_to_100m(mv)
    if value is None:
        _log_once(
            "float_mv_missing_path",
            "float market value unavailable via market_data and instrument_detail",
        )
    return value


def normalize_mv_to_100m(value):
    value = _to_float(value)
    if value is None or value <= 0:
        return None

    # Already in 100 million RMB, usually small.
    if value < 10000.0:
        return value

    # Value in 10k RMB.
    if value < 100000000.0:
        return value / 10000.0

    # Value in RMB.
    return value / 100000000.0


def extract_number_by_keys(data, key_candidates):
    if not isinstance(data, dict):
        return None

    # Exact key match first.
    for k in key_candidates:
        if k in data:
            value = _to_float(data.get(k))
            if value is not None:
                return value

    # Fuzzy key match.
    lower_map = {}
    for key, value in data.items():
        try:
            lower_map[str(key).lower()] = value
        except Exception:
            continue

    for k in key_candidates:
        target = str(k).lower()
        for key, value in lower_map.items():
            if target == key or target in key:
                number = _to_float(value)
                if number is not None:
                    return number
    return None


def _to_float(value):
    try:
        if value is None:
            return None
        s = str(value).replace(",", "").strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def calc_ma_last(values, window):
    if len(values) < window or window <= 0:
        return None
    segment = values[-window:]
    return sum(segment) / float(window)


def calc_double_ema_last(values, n):
    ema1 = ema_series(values, n)
    if not ema1:
        return None
    ema2 = ema_series(ema1, n)
    if not ema2:
        return None
    return ema2[-1]


def ema_series(values, n):
    if not values or n <= 0:
        return []

    alpha = 2.0 / (n + 1.0)
    out = []
    prev = None
    for v in values:
        v = float(v)
        if prev is None:
            cur = v
        else:
            cur = alpha * v + (1.0 - alpha) * prev
        out.append(cur)
        prev = cur
    return out


def compute_kdj(bars, n, k_init, d_init):
    k_list = []
    d_list = []
    j_list = []

    k_prev = k_init
    d_prev = d_init
    for i in range(len(bars)):
        start = max(0, i - n + 1)
        window = bars[start : i + 1]

        low_n = min(b["low"] for b in window)
        high_n = max(b["high"] for b in window)
        if high_n == low_n:
            rsv = 0.0
        else:
            rsv = (bars[i]["close"] - low_n) / (high_n - low_n) * 100.0

        k = (2.0 * k_prev + rsv) / 3.0
        d = (2.0 * d_prev + k) / 3.0
        j = 3.0 * k - 2.0 * d

        k_list.append(k)
        d_list.append(d)
        j_list.append(j)

        k_prev = k
        d_prev = d

    return k_list, d_list, j_list


def get_universe(context):
    sector_codes = _get_main_board_universe_from_sector(context)

    ctx_codes = []
    if hasattr(context, "get_universe"):
        try:
            data = context.get_universe()
            if data:
                ctx_codes = list(data)
        except Exception:
            pass

    if not ctx_codes:
        for attr in ("stock_code", "stockcode", "stock", "symbol", "code"):
            val = getattr(context, attr, "")
            if val:
                ctx_codes = [val]
                break

    sector_codes = _normalize_main_board_codes(sector_codes)
    ctx_codes = _normalize_main_board_codes(ctx_codes)

    use_sector = False
    if sector_codes:
        if FORCE_MAIN_BOARD_UNIVERSE:
            use_sector = True
        elif len(ctx_codes) < MIN_UNIVERSE_SIZE:
            use_sector = True
        elif len(sector_codes) > len(ctx_codes):
            use_sector = True

    if use_sector:
        _log("universe_source=sector size={0}".format(len(sector_codes)))
        return sector_codes

    _log("universe_source=context size={0}".format(len(ctx_codes)))
    return ctx_codes


def _get_main_board_universe_from_sector(context):
    all_codes = []

    if hasattr(context, "get_stock_list_in_sector"):
        for name in UNIVERSE_SECTOR_NAMES:
            try:
                codes = context.get_stock_list_in_sector(name)
                if codes:
                    all_codes.extend(list(codes))
            except Exception:
                pass

    if "get_stock_list_in_sector" in globals():
        func = globals().get("get_stock_list_in_sector")
        if callable(func):
            for name in UNIVERSE_SECTOR_NAMES:
                try:
                    codes = func(name)
                    if codes:
                        all_codes.extend(list(codes))
                except Exception:
                    pass

    if xtdata is not None:
        for name in UNIVERSE_SECTOR_NAMES:
            try:
                codes = xtdata.get_stock_list_in_sector(name)
                if codes:
                    all_codes.extend(list(codes))
            except Exception:
                pass

    return all_codes


def _normalize_main_board_codes(codes):
    normalized = []
    seen = set()
    for c in codes or []:
        n = normalize_stock_code(c)
        if not n or (n in seen):
            continue
        if not is_main_board_a_share(n):
            continue
        seen.add(n)
        normalized.append(n)
    return normalized


def fetch_daily_bars_batch(context, codes, end_date, count):
    result = {}
    end_date = _normalize_trade_date(end_date)
    if not end_date:
        return result

    end_candidates = [end_date, end_date + "150000", end_date + "235959", ""]
    for batch_codes in _chunked_unique_codes(codes, BATCH_FETCH_CHUNK_SIZE):
        data = {}
        for end_ts in end_candidates:
            try:
                data = context.get_market_data_ex(
                    ["open", "high", "low", "close", "volume"],
                    list(batch_codes),
                    period="1d",
                    start_time="",
                    end_time=end_ts,
                    count=count,
                    dividend_type="none",
                    fill_data=True,
                    subscribe=True,
                )
                if data:
                    break
            except Exception:
                data = {}
        if not data:
            continue
        for code in batch_codes:
            try:
                df = data.get(code)
                if df is None or df.empty:
                    continue
                bars = _daily_df_to_bars(df)
                if bars:
                    result[code] = bars
            except Exception:
                continue
    return result


def fetch_daily_bars(context, code, end_date, count):
    end_date = _normalize_trade_date(end_date)
    end_candidates = [end_date, end_date + "150000", end_date + "235959", ""]

    df = None
    for end_ts in end_candidates:
        try:
            data = context.get_market_data_ex(
                ["open", "high", "low", "close", "volume"],
                [code],
                period="1d",
                start_time="",
                end_time=end_ts,
                count=count,
                dividend_type="none",
                fill_data=True,
                subscribe=True,
            )
            cur = data.get(code)
            if cur is not None and (not cur.empty):
                df = cur
                break
        except Exception:
            continue
    if df is None or df.empty:
        return []
    return _daily_df_to_bars(df)


def get_trading_calendar_prev_date(context, date_str):
    date_str = _normalize_trade_date(date_str)
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y%m%d")

    try:
        dates = context.get_trading_dates("SH", "", date_str, 2, "1d")
        if len(dates) >= 2:
            return _normalize_trade_date(dates[-2])
    except Exception:
        pass

    dt = datetime.datetime.strptime(date_str, "%Y%m%d").date()
    dt -= datetime.timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= datetime.timedelta(days=1)
    return dt.strftime("%Y%m%d")


def _get_current_dt(context):
    try:
        barpos = getattr(context, "barpos", None)
        timetag = context.get_bar_timetag(barpos)
        dt = _parse_timetag(timetag)
        if dt is not None:
            return dt
    except Exception:
        pass
    return datetime.datetime.now()


def _parse_timetag(timetag):
    if not timetag:
        return None

    if "timetag_to_datetime" in globals():
        try:
            ts = timetag_to_datetime(timetag, "%Y%m%d%H%M%S")
            return datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")
        except Exception:
            pass

    digits = "".join(ch for ch in str(timetag).strip() if ch.isdigit())
    if len(digits) >= 14:
        try:
            return datetime.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        except Exception:
            pass
    if len(digits) == 13:
        try:
            return datetime.datetime.fromtimestamp(int(digits) / 1000.0)
        except Exception:
            pass
    if len(digits) == 10:
        try:
            return datetime.datetime.fromtimestamp(int(digits))
        except Exception:
            pass
    return None


def is_main_board_a_share(stock_code):
    if not stock_code:
        return False
    code = stock_code.split(".")[0]
    if code.startswith("300") or code.startswith("688") or code.startswith("689"):
        return False
    return (
        code.startswith("600")
        or code.startswith("601")
        or code.startswith("603")
        or code.startswith("605")
        or code.startswith("000")
        or code.startswith("001")
        or code.startswith("002")
    )


def normalize_stock_code(stock_code):
    if not stock_code:
        return ""
    s = str(stock_code).strip().upper()
    if not s:
        return ""

    if "." in s:
        left, right = s.split(".", 1)
        if len(left) == 6 and right in ("SH", "SZ"):
            return left + "." + right
        if len(left) == 6 and right in ("XSHG", "SSE"):
            return left + ".SH"
        if len(left) == 6 and right in ("XSHE", "SZSE"):
            return left + ".SZ"
        if len(right) == 6 and left in ("SH", "SSE", "XSHG"):
            return right + ".SH"
        if len(right) == 6 and left in ("SZ", "SZSE", "XSHE"):
            return right + ".SZ"
        return s

    if len(s) == 6 and s.isdigit():
        if s.startswith(("600", "601", "603", "605", "688", "689")):
            return s + ".SH"
        return s + ".SZ"
    return s


def _chunked_unique_codes(codes, chunk_size):
    uniq = []
    seen = set()
    for c in codes or []:
        n = normalize_stock_code(c)
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(n)

    if chunk_size <= 0:
        chunk_size = len(uniq) or 1
    for i in range(0, len(uniq), chunk_size):
        yield uniq[i : i + chunk_size]


def _daily_df_to_bars(df):
    bars = []
    try:
        iterator = df.iterrows()
    except Exception:
        return bars

    for idx, row in iterator:
        date_str = str(idx)
        digits = "".join(ch for ch in date_str if ch.isdigit())
        if len(digits) >= 8:
            date_str = digits[:8]
        else:
            date_str = ""
        try:
            bars.append(
                {
                    "date": date_str,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
        except Exception:
            continue
    return bars


def _normalize_trade_date(value):
    if value is None:
        return ""
    s = str(value).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 13:
        try:
            return datetime.datetime.fromtimestamp(int(digits) / 1000.0).strftime("%Y%m%d")
        except Exception:
            return ""
    if len(digits) == 10:
        try:
            return datetime.datetime.fromtimestamp(int(digits)).strftime("%Y%m%d")
        except Exception:
            return ""
    if len(digits) >= 8:
        return digits[:8]
    return ""


def _log(msg):
    try:
        print("[{0}] {1}".format(STRATEGY_NAME, msg))
    except Exception:
        pass


def _log_once(key, msg):
    if key in g.logged_once:
        return
    g.logged_once.add(key)
    _log(msg)
