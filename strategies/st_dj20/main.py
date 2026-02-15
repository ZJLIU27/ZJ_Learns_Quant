#coding:gbk
"""
Stock picker: st_dj20 (TongDaXin formula -> xtQMT)

Formula:
short := 100*(C-LLV(L,3))/(HHV(C,3)-LLV(L,3));
long := 100*(C-LLV(L,21))/(HHV(C,21)-LLV(L,21));
TJ1 := NOT(INBLOCK('ChiNext') OR INBLOCK('STAR'));
XG: long >= 70 AND long-short >= 20 AND TJ1;
"""

import datetime

try:
    from xtquant import xtdata
except Exception:
    xtdata = None


class G:
    pass


g = G()

STRATEGY_NAME = "st_dj20"
ACCOUNT_ID = "testS"
ACCOUNT_TYPE = "stock"

SHORT_WINDOW = 3
LONG_WINDOW = 21
LONG_MIN = 70.0
DELTA_MIN = 20.0
DAILY_BAR_COUNT = 40

BATCH_FETCH_CHUNK_SIZE = 200
MAX_LOG_CODES = 20

FORCE_MAIN_BOARD_UNIVERSE = True
MIN_UNIVERSE_SIZE = 100
UNIVERSE_SECTOR_NAMES = (
    "\u6caa\u6df1A\u80a1",
    "A\u80a1",
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
        "long_fail": 0,
        "delta_fail": 0,
    }

    daily_batch = fetch_daily_bars_batch(context, g.universe, t_date, DAILY_BAR_COUNT)
    for code in g.universe:
        bars = daily_batch.get(code)
        if not bars:
            bars = fetch_daily_bars(context, code, t_date, DAILY_BAR_COUNT)
        if len(bars) < LONG_WINDOW:
            stats["bars_short"] += 1
            continue

        closes = [b["close"] for b in bars]
        lows = [b["low"] for b in bars]

        short_val = calc_tdx_value(closes, lows, SHORT_WINDOW)
        long_val = calc_tdx_value(closes, lows, LONG_WINDOW)
        if short_val is None or long_val is None:
            stats["bars_short"] += 1
            continue

        if long_val < LONG_MIN:
            stats["long_fail"] += 1
            continue

        if (long_val - short_val) < DELTA_MIN:
            stats["delta_fail"] += 1
            continue

        candidates.append(code)

    _log(
        "filter_stats total={0} bars_short={1} long_fail={2} delta_fail={3} pass={4}".format(
            stats["total"],
            stats["bars_short"],
            stats["long_fail"],
            stats["delta_fail"],
            len(candidates),
        )
    )
    return candidates


def calc_tdx_value(closes, lows, window):
    if len(closes) < window or len(lows) < window:
        return None
    c = closes[-1]
    llv = min(lows[-window:])
    hhv = max(closes[-window:])
    den = hhv - llv
    if den <= 0:
        return 0.0
    return 100.0 * (c - llv) / den


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
