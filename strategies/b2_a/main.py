#coding:gbk
"""
Strategy: b2_a

Rules (current):
- T is the last completed trading day.
- Daily filters on T and T-1:
  1) J(T-1) < 20 (KDJ)
  2) J(T) < 65 (KDJ)
  3) T daily return > 4%
  4) T volume >= 1.5 * T-1 volume
  5) T upper shadow < 20% of full candle range
- Graphic features are fully applied in selection layer on T-day 1m bars:
  parallel -> first cannon -> pullback -> second-cannon rebound.
- At T+1 09:35: from passed candidates, pick top 3 by volume ratio (>5).
- Entry: buy selected top3 at 09:35; failed orders retry next minute.
"""

import datetime

try:
    from xtquant import xtdata
except Exception:
    xtdata = None


# QMT ContextInfo variables roll back after handlebar; use global state.
class G:
    pass


g = G()

STRATEGY_NAME = "b2_a"

# --- Config (confirm/adjust with final rules) ---
DAILY_KDJ_N = 9
KDJ_INIT = 50.0

J_T_MINUS1_MAX = 20.0
J_T_MAX = 65.0
DAILY_RETURN_MIN = 0.04
DAILY_VOLUME_RATIO_MIN = 1.5
UPPER_SHADOW_MAX_RATIO = 0.20

VOLUME_RATIO_MIN = 5.0
VOLUME_RATIO_WINDOW_START = datetime.time(9, 30)
VOLUME_RATIO_WINDOW_END = datetime.time(9, 35)
TRADING_MINUTES_PER_DAY = 240.0
WATCHLIST_SIZE = 3
WATCHLIST_TIME = datetime.time(9, 35)

MINUTE_BAR_PERIOD = "1m"
BATCH_FETCH_CHUNK_SIZE = 200

TICK_SIZE = 0.01

# b2_a intraday entry pattern:
# wait parallel MA5/MA10 -> first cannon -> pullback -> second cannon.
PARALLEL_LOOKBACK = 10
PARALLEL_MAX_MA_GAP_RATIO = 0.005
PARALLEL_MAX_MA5_SLOPE_RATIO = 0.003
PARALLEL_MAX_MA10_SLOPE_RATIO = 0.003
PARALLEL_MAX_RANGE_RATIO = 0.04

FIRST_CANNON_BODY_MIN_RATIO = 0.60
FIRST_CANNON_VOL_MA_MULT = 1.80

PULLBACK_MIN_BARS = 1
PULLBACK_MAX_BARS = 4
PULLBACK_MA10_TOLERANCE = 0.003
PULLBACK_MAX_RETRACE_FIRST_BODY = 0.50
PULLBACK_MAX_BAR_VOL_RATIO = 1.00

SECOND_CANNON_MIN_FIRST_VOL_RATIO = 0.80
SECOND_CANNON_VOL_MA_MULT = 1.00
REBOUND_LOOKBACK = 5
REBOUND_LOCAL_LOW_TICKS = 1.0

ORDER_CASH = 20000.0
ENABLE_TRADING = True  # exit rules defined, ready for trading (adapters required)

TAKE_PROFIT_1 = 0.03
TAKE_PROFIT_2 = 0.10
TAKE_PROFIT_SELL_RATIO = 1.0 / 3.0
STOP_CHECK_TIME = datetime.time(14, 45)

ACCOUNT_ID = ""  # leave empty to use built-in `account` from QMT
ACCOUNT_TYPE = "stock"

BUY_OP = 23
SELL_OP = 24
ORDER_TYPE_BUY_AMOUNT = 1102  # by amount (RMB)
ORDER_TYPE_SELL_SHARES = 1101  # by shares
ORDER_PRICE_TYPE = 5  # latest price
ORDER_PRICE = 0
QUICK_TRADE = 2  # immediate order even if not last bar
FORCE_MAIN_BOARD_UNIVERSE = True
MIN_UNIVERSE_SIZE = 100
UNIVERSE_SECTOR_NAMES = (
    "\u6caa\u6df1A\u80a1",  # HS A-share
    "A\u80a1",              # A-share
)


# --- QMT API adapters ---

def get_universe(context):
    """Return list of stock codes in universe.

    Priority:
    1) Main-board full universe from sector list (preferred)
    2) Context-provided universe (backtest settings)
    3) Current chart symbol
    """
    # 1) Try full A-share sector first
    sector_codes = _get_main_board_universe_from_sector(context)

    # 2) Context universe
    ctx_codes = []
    if hasattr(context, "get_universe"):
        try:
            data = context.get_universe()
            if data:
                ctx_codes = list(data)
        except Exception:
            pass

    # 3) Current chart symbol
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
        _log(
            "universe_source=sector size={0} (ctx_size={1})".format(
                len(sector_codes), len(ctx_codes)
            )
        )
        return sector_codes

    _log("universe_source=context size={0}".format(len(ctx_codes)))
    return ctx_codes


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


def _get_main_board_universe_from_sector(context):
    """Load A-share list from sector APIs (context/global/xtdata)."""
    all_codes = []

    # context method in some QMT runtimes
    if hasattr(context, "get_stock_list_in_sector"):
        for name in UNIVERSE_SECTOR_NAMES:
            try:
                codes = context.get_stock_list_in_sector(name)
                if codes:
                    all_codes.extend(list(codes))
            except Exception:
                pass

    # global helper in some QMT runtimes
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

    # xtdata fallback
    if xtdata is not None:
        for name in UNIVERSE_SECTOR_NAMES:
            try:
                codes = xtdata.get_stock_list_in_sector(name)
                if codes:
                    all_codes.extend(list(codes))
            except Exception:
                pass

    return all_codes


def fetch_daily_bars(context, code, end_date, count):
    """Return list of daily bars up to end_date (inclusive), ascending by date.

    Each bar is a dict with keys: date, open, high, low, close, volume
    date: "YYYYMMDD"
    """
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


def fetch_daily_bars_batch(context, codes, end_date, count):
    """Batch fetch daily bars for codes.

    Return: dict(code -> bars list)
    """
    result = {}
    if not codes:
        return result

    end_date = _normalize_trade_date(end_date)
    if not end_date:
        return result

    end_candidates = [end_date, end_date + "150000", end_date + "235959", ""]
    data = {}
    for end_ts in end_candidates:
        try:
            data = context.get_market_data_ex(
                ["open", "high", "low", "close", "volume"],
                list(codes),
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
        return result

    for code in codes:
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


def fetch_minute_bars(context, code, trade_date, end_time, count):
    """Return list of minute bars for trade_date up to end_time (inclusive).

    Each bar is a dict with keys: time, open, high, low, close, volume
    time: "HH:MM"
    """
    trade_date = _normalize_trade_date(trade_date)
    if not trade_date:
        return []

    end_hhmm = "".join(ch for ch in str(end_time) if ch.isdigit())[:4]
    if len(end_hhmm) != 4:
        end_hhmm = "1500"
    end_ts = trade_date + end_hhmm + "00"
    start_ts_day = trade_date + "090000"

    # Historical minute bars in backtest are more stable with subscribe=False
    # and explicit same-day start/end range.
    query_plan = [
        {"start_time": start_ts_day, "end_time": end_ts, "subscribe": False, "count": max(count, 480)},
        {"start_time": start_ts_day, "end_time": end_ts, "subscribe": True, "count": max(count, 480)},
        {"start_time": "", "end_time": end_ts, "subscribe": False, "count": count},
        {"start_time": "", "end_time": end_ts, "subscribe": True, "count": count},
    ]

    df = None
    for q in query_plan:
        try:
            data = context.get_market_data_ex(
                ["open", "high", "low", "close", "volume"],
                [code],
                period="1m",
                start_time=q["start_time"],
                end_time=q["end_time"],
                count=q["count"],
                dividend_type="none",
                fill_data=True,
                subscribe=q["subscribe"],
            )
            cur = data.get(code)
            if cur is not None and (not cur.empty):
                df = cur
                break
        except Exception:
            continue

    if df is None or df.empty:
        return []

    return _minute_df_to_bars(df, trade_date, end_hhmm)


def fetch_minute_bars_batch(context, codes, trade_date, end_time, count):
    """Batch fetch minute bars for codes on trade_date up to end_time.

    Return: dict(code -> bars list)
    """
    result = {}
    if not codes:
        return result

    trade_date = _normalize_trade_date(trade_date)
    if not trade_date:
        return result

    end_hhmm = "".join(ch for ch in str(end_time) if ch.isdigit())[:4]
    if len(end_hhmm) != 4:
        end_hhmm = "1500"
    end_ts = trade_date + end_hhmm + "00"
    start_ts_day = trade_date + "090000"

    query_plan = [
        {"start_time": start_ts_day, "end_time": end_ts, "subscribe": False, "count": max(count, 480)},
        {"start_time": start_ts_day, "end_time": end_ts, "subscribe": True, "count": max(count, 480)},
        {"start_time": "", "end_time": end_ts, "subscribe": False, "count": count},
        {"start_time": "", "end_time": end_ts, "subscribe": True, "count": count},
    ]

    for batch_codes in _chunked_unique_codes(codes, BATCH_FETCH_CHUNK_SIZE):
        pending = set(batch_codes)
        for q in query_plan:
            if not pending:
                break
            try:
                data = context.get_market_data_ex(
                    ["open", "high", "low", "close", "volume"],
                    list(pending),
                    period="1m",
                    start_time=q["start_time"],
                    end_time=q["end_time"],
                    count=q["count"],
                    dividend_type="none",
                    fill_data=True,
                    subscribe=q["subscribe"],
                )
            except Exception:
                continue
            if not data:
                continue
            hit_codes = []
            for code in pending:
                try:
                    df = data.get(code)
                except Exception:
                    df = None
                if df is None or df.empty:
                    continue
                bars = _minute_df_to_bars(df, trade_date, end_hhmm)
                if bars:
                    result[code] = bars
                    hit_codes.append(code)
            for code in hit_codes:
                pending.discard(code)

    return result


def get_current_price(context, code):
    """Return current price for code."""
    now = _get_current_dt(context)
    if now is None:
        return None
    end_ts = now.strftime("%Y%m%d%H%M%S")
    data = context.get_market_data_ex(
        ["close"],
        [code],
        period="1m",
        start_time="",
        end_time=end_ts,
        count=1,
        dividend_type="none",
        fill_data=True,
        subscribe=True,
    )
    df = data.get(code)
    if df is None or df.empty:
        return None
    return float(df["close"].iloc[-1])


def place_buy_order(context, code, cash_amount):
    """Place a buy order using cash_amount.

    Return True if order accepted, False if failed.
    """
    account_id = _get_account_id(context)
    if not account_id:
        return False
    try:
        passorder(
            BUY_OP,
            ORDER_TYPE_BUY_AMOUNT,
            account_id,
            code,
            ORDER_PRICE_TYPE,
            ORDER_PRICE,
            cash_amount,
            "",
            QUICK_TRADE,
            "",
            context,
        )
        return True
    except Exception:
        return False


def get_available_cash(context):
    """Return available cash."""
    account_id = _get_account_id(context)
    if not account_id:
        return 0.0
    try:
        accounts = get_trade_detail_data(account_id, ACCOUNT_TYPE, "account")
    except Exception:
        return 0.0
    if not accounts:
        return 0.0
    return float(accounts[0].m_dAvailable)


def get_positions(context):
    """Return current positions as dict: code -> position quantity."""
    account_id = _get_account_id(context)
    if not account_id:
        return {}
    try:
        positions = get_trade_detail_data(account_id, ACCOUNT_TYPE, "position")
    except Exception:
        return {}
    pos = {}
    for p in positions:
        code = p.m_strInstrumentID + "." + p.m_strExchangeID
        qty = int(getattr(p, "m_nCanUseVolume", p.m_nVolume))
        pos[code] = qty
    return pos

def get_position_cost(context, code):
    """Return average cost price for a position, or None if unavailable."""
    account_id = _get_account_id(context)
    if not account_id:
        return None
    try:
        positions = get_trade_detail_data(account_id, ACCOUNT_TYPE, "position")
    except Exception:
        return None
    for p in positions:
        pos_code = p.m_strInstrumentID + "." + p.m_strExchangeID
        if pos_code == code:
            return float(getattr(p, "m_dOpenPrice", 0.0)) or None
    return None


def place_sell_order(context, code, quantity):
    """Place a sell order using quantity.

    Return True if order accepted, False if failed.
    """
    account_id = _get_account_id(context)
    if not account_id:
        return False
    try:
        passorder(
            SELL_OP,
            ORDER_TYPE_SELL_SHARES,
            account_id,
            code,
            ORDER_PRICE_TYPE,
            ORDER_PRICE,
            quantity,
            "",
            QUICK_TRADE,
            "",
            context,
        )
        return True
    except Exception:
        return False


def get_trading_calendar_prev_date(context, date_str):
    """Return previous trading date for date_str (YYYYMMDD).

    Default fallback only skips weekends; replace with QMT trading calendar.
    """
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


# --- Strategy lifecycle ---

def init(context):
    """Initialize strategy."""
    # set account if provided (optional)
    g.account_id = _get_account_id(context)
    account_id = g.account_id
    if account_id and hasattr(context, "set_account"):
        try:
            context.set_account(account_id)
        except Exception:
            _log("set_account failed; continue without explicit account binding")

    g.universe = []
    g.trade_date = None
    g.daily_candidates = []
    g.watchlist = []
    g.watchlist_built = False
    g.entry_patterns = {}
    g.bought = set()
    g.pending_buy = {}
    g.pending_buy_stop_low = {}
    g.entry_submitted = set()
    g.entry_check_stats = {}
    g.entry_price = {}
    g.buy_day_low = {}
    g.buy_date = {}
    g.take_profit_state = {}
    g.exit_checked = None
    g.logged_once = set()

    # initialize universe
    try:
        g.universe = get_universe(context)
        if g.universe and hasattr(context, "set_universe"):
            context.set_universe(g.universe)
    except Exception:
        g.universe = []

    _log("init done, universe size={0}".format(len(g.universe)))
    if g.universe:
        sample = ",".join(g.universe[:5])
        _log("universe sample={0}".format(sample))
    if not g.universe:
        _log("universe is empty; backtest may stop immediately")


def handlebar(context):
    """Called on each minute bar."""
    now = _get_current_dt(context)
    if now is None:
        return

    trade_date = now.strftime("%Y%m%d")

    # New trading day initialization
    if g.trade_date != trade_date:
        g.trade_date = trade_date
        g.watchlist_built = False
        g.watchlist = []
        g.entry_patterns = {}
        g.bought = set()
        g.pending_buy = {}
        g.pending_buy_stop_low = {}
        g.entry_submitted = set()
        g.entry_check_stats = {}
        g.logged_once = set()

        t_date = get_trading_calendar_prev_date(context, trade_date)
        g.daily_candidates = build_daily_candidates(context, t_date)
        _log(
            "new day={0}, prev_day={1}, candidates={2}".format(
                trade_date, t_date, len(g.daily_candidates)
            )
        )

    # Build watchlist at 09:35 using volume-ratio top3.
    if (not g.watchlist_built) and now.time() >= WATCHLIST_TIME:
        g.watchlist = build_watchlist(context, trade_date, now)
        g.watchlist_built = True
        _log("watchlist built size={0}".format(len(g.watchlist)))
        if g.watchlist:
            _log("watchlist sample={0}".format(",".join(g.watchlist[:5])))

    # At/after 09:35, place entry for selected top3 once; failed orders retry next minute.
    for code in g.watchlist:
        try:
            price = get_current_price(context, code)
        except Exception:
            continue
        if price is None:
            continue

        if code in g.bought:
            continue

        st = g.entry_check_stats.get(code)
        if st is None:
            st = {"checks": 0, "hits": 0}
            g.entry_check_stats[code] = st

        if (
            now.time() >= WATCHLIST_TIME
            and code not in g.entry_submitted
            and code not in g.pending_buy
        ):
            st["checks"] += 1
            st["hits"] += 1
            g.entry_submitted.add(code)
            _try_place_buy(context, code, price, now)

        # If prior buy failed, retry at next minute with latest price
        if code in g.pending_buy and now >= g.pending_buy[code]:
            _try_place_buy(
                context,
                code,
                price,
                now,
                stop_low=g.pending_buy_stop_low.get(code),
            )

    # Profit-taking checks (any time)
    _check_take_profit(context, now)

    # Stop-loss and volume-based exit checks at 14:45
    if now.time() >= STOP_CHECK_TIME and g.exit_checked != trade_date:
        _log_end_of_day_entry_stats(trade_date)
        _check_stop_rules(context, trade_date, now)
        g.exit_checked = trade_date


# --- Core logic ---

def build_daily_candidates(context, t_date):
    candidates = []
    stats = {
        "total": 0,
        "batch_hit": 0,
        "single_fallback_hit": 0,
        "bars_short": 0,
        "kdj_t1_fail": 0,
        "kdj_t_fail": 0,
        "ret_fail": 0,
        "vol_fail": 0,
        "upper_shadow_fail": 0,
    }
    stats["total"] = len(g.universe)
    short_samples = []
    daily_batch = {}
    try:
        daily_batch = fetch_daily_bars_batch(context, g.universe, t_date, DAILY_KDJ_N + 2)
    except Exception:
        daily_batch = {}
    _log("daily_batch_fetch date={0} hit={1}".format(t_date, len(daily_batch)))

    for code in g.universe:
        if not is_main_board_a_share(code):
            continue

        bars = daily_batch.get(code, [])
        if bars:
            stats["batch_hit"] += 1
        else:
            try:
                bars = fetch_daily_bars(context, code, t_date, DAILY_KDJ_N + 2)
            except Exception:
                bars = []
            if bars:
                stats["single_fallback_hit"] += 1

        if len(bars) < DAILY_KDJ_N + 2:
            stats["bars_short"] += 1
            if len(short_samples) < 3:
                short_samples.append("{0}:{1}".format(code, len(bars)))
            continue

        bar_t_minus1 = bars[-2]
        bar_t = bars[-1]

        k_list, d_list, j_list = compute_kdj(bars, DAILY_KDJ_N, KDJ_INIT, KDJ_INIT)
        if len(j_list) < 2:
            continue

        j_t_minus1 = j_list[-2]
        j_t = j_list[-1]

        if j_t_minus1 >= J_T_MINUS1_MAX:
            stats["kdj_t1_fail"] += 1
            continue
        if j_t >= J_T_MAX:
            stats["kdj_t_fail"] += 1
            continue

        if not daily_return_ok(bar_t_minus1, bar_t):
            stats["ret_fail"] += 1
            continue
        prev_vol = bar_t_minus1["volume"]
        if prev_vol <= 0 or bar_t["volume"] < (prev_vol * DAILY_VOLUME_RATIO_MIN):
            stats["vol_fail"] += 1
            continue
        if upper_shadow_ratio(bar_t) >= UPPER_SHADOW_MAX_RATIO:
            stats["upper_shadow_fail"] += 1
            continue

        candidates.append(code)

    _log(
        "daily_filter_stats total={0} batch_hit={1} fallback_hit={2} bars_short={3} "
        "kdj_t1_fail={4} kdj_t_fail={5} ret_fail={6} vol_fail={7} upper_shadow_fail={8} pass={9}".format(
            stats["total"],
            stats["batch_hit"],
            stats["single_fallback_hit"],
            stats["bars_short"],
            stats["kdj_t1_fail"],
            stats["kdj_t_fail"],
            stats["ret_fail"],
            stats["vol_fail"],
            stats["upper_shadow_fail"],
            len(candidates),
        )
    )
    if short_samples:
        _log("bars_short_samples t_date={0} {1}".format(t_date, ",".join(short_samples)))
    return candidates


def build_watchlist(context, trade_date, now):
    ranked = []
    stats = {
        "total_candidates": len(g.daily_candidates),
        "vol_ratio_none": 0,
        "vol_ratio_low": 0,
        "pattern_fail": 0,
    }
    pattern_date = get_trading_calendar_prev_date(context, trade_date)
    prev_dates = get_prev_trading_dates(context, trade_date, 5)
    prefetch = _prefetch_volume_ratio_data(context, g.daily_candidates, trade_date, now, prev_dates)
    _log("graphic_pattern_date={0}".format(pattern_date))
    _log(
        "volume_ratio_window={0}-{1}".format(
            VOLUME_RATIO_WINDOW_START.strftime("%H:%M"),
            VOLUME_RATIO_WINDOW_END.strftime("%H:%M"),
        )
    )
    for code in g.daily_candidates:
        decided, vol_ratio = _calc_volume_ratio_prefetched(
            code=code,
            prev_dates=prev_dates,
            elapsed_minutes=prefetch.get("elapsed_minutes", 0.0),
            window_start=prefetch.get("window_start", ""),
            window_end=prefetch.get("window_end", ""),
            today_bars_by_code=prefetch.get("today_bars_by_code", {}),
            hist_bars_by_date=prefetch.get("hist_bars_by_date", {}),
            today_prefetch_ok=prefetch.get("today_prefetch_ok", False),
            hist_prefetch_ok_by_date=prefetch.get("hist_prefetch_ok_by_date", {}),
        )
        if not decided:
            vol_ratio = calc_volume_ratio(context, code, trade_date, now)
        if vol_ratio is None:
            stats["vol_ratio_none"] += 1
            continue
        if vol_ratio <= VOLUME_RATIO_MIN:
            stats["vol_ratio_low"] += 1
            continue
        if not _match_graphic_pattern_on_date(context, code, pattern_date):
            stats["pattern_fail"] += 1
            continue
        ranked.append((code, vol_ratio))

    ranked.sort(key=lambda x: x[1], reverse=True)
    watchlist = [code for code, _ in ranked[:WATCHLIST_SIZE]]
    _log(
        "watchlist_stats total_candidates={0} vol_ratio_none={1} vol_ratio_low={2} "
        "pattern_fail={3} passed={4} selected={5}".format(
            stats["total_candidates"],
            stats["vol_ratio_none"],
            stats["vol_ratio_low"],
            stats["pattern_fail"],
            len(ranked),
            len(watchlist),
        )
    )
    if ranked:
        top = ",".join(["{0}:{1:.2f}".format(c, v) for c, v in ranked[:5]])
        _log("watchlist_rank_top={0}".format(top))
    return watchlist


def _process_b2_a_entry(context, code, trade_date, now, price):
    """Evaluate b2_a entry state machine and place order on second cannon."""
    try:
        bars = fetch_minute_bars(context, code, trade_date, now.strftime("%H:%M"), 320)
    except Exception:
        return False
    if not bars:
        return False

    state = g.entry_patterns.get(code)
    if state is None:
        state = {}
        _reset_entry_pattern_state(state, "")

    triggered = False
    for idx, bar in enumerate(bars):
        hhmm = bar.get("time", "")
        if (not hhmm) or hhmm <= state.get("last_bar_time", ""):
            continue

        if state.get("stage") == "wait_first":
            ok, zone_high = _is_first_cannon_bar(bars, idx)
            if ok:
                state["stage"] = "wait_pullback"
                state["first_idx"] = idx
                state["first_zone_high"] = zone_high
                state["first_open"] = float(bar["open"])
                state["first_close"] = float(bar["close"])
                state["first_high"] = float(bar["high"])
                state["first_low"] = float(bar["low"])
                state["first_volume"] = float(bar["volume"])
                state["pullback_low"] = None
                state["pullback_high"] = None
                state["pullback_has_shrink"] = False
        else:
            gap = idx - int(state.get("first_idx", -1))
            if gap <= 0:
                state["last_bar_time"] = hhmm
                continue

            ma10 = _ma_on_close(bars, idx, 10)
            if ma10 is not None and ma10 > 0:
                if float(bar["low"]) < ma10 * (1.0 - PULLBACK_MA10_TOLERANCE):
                    _reset_entry_pattern_state(state, hhmm)
                    continue

            first_body = max(float(state.get("first_close", 0.0)) - float(state.get("first_open", 0.0)), TICK_SIZE)
            max_retrace_low = float(state.get("first_close", 0.0)) - first_body * PULLBACK_MAX_RETRACE_FIRST_BODY
            if float(bar["low"]) < max_retrace_low:
                _reset_entry_pattern_state(state, hhmm)
                continue

            if gap > (PULLBACK_MAX_BARS + 1):
                _reset_entry_pattern_state(state, hhmm)
                continue

            min_gap_for_second = PULLBACK_MIN_BARS + 1
            if gap >= min_gap_for_second and _is_second_cannon_bar(bars, idx, state):
                stop_low = state.get("pullback_low")
                if stop_low is None:
                    stop_low = float(bar["low"])
                _try_place_buy(context, code, price, now, stop_low=stop_low)
                triggered = True
                _reset_entry_pattern_state(state, hhmm)
                state["last_bar_time"] = hhmm
                break

            if gap <= PULLBACK_MAX_BARS:
                pullback_low = state.get("pullback_low")
                pullback_high = state.get("pullback_high")
                if pullback_low is None or float(bar["low"]) < pullback_low:
                    state["pullback_low"] = float(bar["low"])
                if pullback_high is None or float(bar["high"]) > pullback_high:
                    state["pullback_high"] = float(bar["high"])

                first_volume = float(state.get("first_volume", 0.0))
                if first_volume > 0 and float(bar["volume"]) <= first_volume * PULLBACK_MAX_BAR_VOL_RATIO:
                    state["pullback_has_shrink"] = True

        state["last_bar_time"] = hhmm

    g.entry_patterns[code] = state
    return triggered


def _match_graphic_pattern_on_date(context, code, trade_date):
    """Return True if full b2_a graphic pattern appears on a given trade date."""
    try:
        bars = fetch_minute_bars(context, code, trade_date, "15:00", 600)
    except Exception:
        return False
    if not bars:
        return False
    return _match_graphic_pattern_on_bars(bars)


def _match_graphic_pattern_on_bars(bars):
    """Detect: parallel -> first cannon -> pullback -> second-cannon rebound."""
    state = {}
    _reset_entry_pattern_state(state, "")

    for idx, bar in enumerate(bars):
        hhmm = bar.get("time", "")
        if not hhmm:
            continue

        if state.get("stage") == "wait_first":
            ok, zone_high = _is_first_cannon_bar(bars, idx)
            if ok:
                state["stage"] = "wait_pullback"
                state["first_idx"] = idx
                state["first_zone_high"] = zone_high
                state["first_open"] = float(bar["open"])
                state["first_close"] = float(bar["close"])
                state["first_high"] = float(bar["high"])
                state["first_low"] = float(bar["low"])
                state["first_volume"] = float(bar["volume"])
                state["pullback_low"] = None
                state["pullback_high"] = None
                state["pullback_has_shrink"] = False
            state["last_bar_time"] = hhmm
            continue

        gap = idx - int(state.get("first_idx", -1))
        if gap <= 0:
            state["last_bar_time"] = hhmm
            continue

        ma10 = _ma_on_close(bars, idx, 10)
        if ma10 is not None and ma10 > 0:
            if float(bar["low"]) < ma10 * (1.0 - PULLBACK_MA10_TOLERANCE):
                _reset_entry_pattern_state(state, hhmm)
                continue

        first_body = max(float(state.get("first_close", 0.0)) - float(state.get("first_open", 0.0)), TICK_SIZE)
        max_retrace_low = float(state.get("first_close", 0.0)) - first_body * PULLBACK_MAX_RETRACE_FIRST_BODY
        if float(bar["low"]) < max_retrace_low:
            _reset_entry_pattern_state(state, hhmm)
            continue

        if gap > (PULLBACK_MAX_BARS + 1):
            _reset_entry_pattern_state(state, hhmm)
            continue

        min_gap_for_second = PULLBACK_MIN_BARS + 1
        if gap >= min_gap_for_second and _is_second_cannon_bar(bars, idx, state):
            return True

        if gap <= PULLBACK_MAX_BARS:
            pullback_low = state.get("pullback_low")
            pullback_high = state.get("pullback_high")
            if pullback_low is None or float(bar["low"]) < pullback_low:
                state["pullback_low"] = float(bar["low"])
            if pullback_high is None or float(bar["high"]) > pullback_high:
                state["pullback_high"] = float(bar["high"])

            first_volume = float(state.get("first_volume", 0.0))
            if first_volume > 0 and float(bar["volume"]) <= first_volume * PULLBACK_MAX_BAR_VOL_RATIO:
                state["pullback_has_shrink"] = True

        state["last_bar_time"] = hhmm

    return False


def _reset_entry_pattern_state(state, last_bar_time):
    state.clear()
    state.update(
        {
            "stage": "wait_first",
            "last_bar_time": last_bar_time,
            "first_idx": -1,
            "first_zone_high": 0.0,
            "first_open": 0.0,
            "first_close": 0.0,
            "first_high": 0.0,
            "first_low": 0.0,
            "first_volume": 0.0,
            "pullback_low": None,
            "pullback_high": None,
            "pullback_has_shrink": False,
        }
    )


def _is_first_cannon_bar(bars, idx):
    if idx <= 0:
        return False, 0.0

    bar = bars[idx]
    open_ = float(bar["open"])
    close = float(bar["close"])
    high = float(bar["high"])
    low = float(bar["low"])
    if close <= open_:
        return False, 0.0

    total = high - low
    if total <= 0:
        return False, 0.0
    body = close - open_
    if (body / total) < FIRST_CANNON_BODY_MIN_RATIO:
        return False, 0.0

    vol_ma = _ma_on_volume(bars, idx - 1, 5)
    if vol_ma is None or vol_ma <= 0:
        return False, 0.0
    if float(bar["volume"]) < vol_ma * FIRST_CANNON_VOL_MA_MULT:
        return False, 0.0

    parallel_ok, zone_high = _parallel_context_ok(bars, idx - 1)
    if not parallel_ok:
        return False, 0.0
    if close <= (zone_high + TICK_SIZE):
        return False, 0.0
    return True, zone_high


def _is_second_cannon_bar(bars, idx, state):
    if idx <= 1:
        return False
    pullback_low = state.get("pullback_low")
    pullback_high = state.get("pullback_high")
    if pullback_low is None or pullback_high is None:
        return False
    if not state.get("pullback_has_shrink", False):
        return False

    first_volume = float(state.get("first_volume", 0.0))
    if first_volume <= 0:
        return False

    bar = bars[idx]
    close = float(bar["close"])
    prev2_close = float(bars[idx - 2]["close"])
    prev_close = float(bars[idx - 1]["close"])
    avg_line = _intraday_avg_price_line(bars, idx)
    if avg_line is None:
        return False
    # Entry timing: still below intraday average-price line and intraday line starts rebounding.
    if close >= avg_line:
        return False
    if prev_close >= avg_line:
        return False
    # Rebound inflection on intraday line: down then up.
    if prev_close >= (prev2_close - TICK_SIZE):
        return False
    if close <= (prev_close + TICK_SIZE):
        return False
    # Previous bar should be near local low in recent minutes.
    start = max(0, idx - REBOUND_LOOKBACK)
    recent_min = min(float(bars[i]["close"]) for i in range(start, idx))
    if prev_close > (recent_min + REBOUND_LOCAL_LOW_TICKS * TICK_SIZE):
        return False

    vol_ma = _ma_on_volume(bars, idx - 1, 5)
    if vol_ma is None or vol_ma <= 0:
        return False

    volume = float(bar["volume"])
    if volume < first_volume * SECOND_CANNON_MIN_FIRST_VOL_RATIO:
        return False
    if volume <= vol_ma * SECOND_CANNON_VOL_MA_MULT:
        return False
    return True


def _parallel_context_ok(bars, end_idx):
    start_idx = end_idx - PARALLEL_LOOKBACK + 1
    if start_idx < 0:
        return False, 0.0

    ma5_vals = []
    ma10_vals = []
    zone_high = None
    zone_low = None

    for i in range(start_idx, end_idx + 1):
        ma5 = _ma_on_close(bars, i, 5)
        ma10 = _ma_on_close(bars, i, 10)
        if ma5 is None or ma10 is None or ma10 <= 0:
            return False, 0.0

        gap = abs(ma5 - ma10) / ma10
        if gap > PARALLEL_MAX_MA_GAP_RATIO:
            return False, 0.0

        ma5_vals.append(ma5)
        ma10_vals.append(ma10)

        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        zone_high = high if zone_high is None else max(zone_high, high)
        zone_low = low if zone_low is None else min(zone_low, low)

    if not ma5_vals or not ma10_vals:
        return False, 0.0
    if zone_low is None or zone_high is None or zone_low <= 0:
        return False, 0.0

    ma5_base = max(abs(ma5_vals[0]), TICK_SIZE)
    ma10_base = max(abs(ma10_vals[0]), TICK_SIZE)
    ma5_slope = abs(ma5_vals[-1] - ma5_vals[0]) / ma5_base
    ma10_slope = abs(ma10_vals[-1] - ma10_vals[0]) / ma10_base
    if ma5_slope > PARALLEL_MAX_MA5_SLOPE_RATIO:
        return False, 0.0
    if ma10_slope > PARALLEL_MAX_MA10_SLOPE_RATIO:
        return False, 0.0

    range_ratio = (zone_high - zone_low) / zone_low
    if range_ratio > PARALLEL_MAX_RANGE_RATIO:
        return False, 0.0
    return True, zone_high


def _ma_on_close(bars, end_idx, period):
    if end_idx < 0:
        return None
    start_idx = end_idx - period + 1
    if start_idx < 0:
        return None
    total = 0.0
    for i in range(start_idx, end_idx + 1):
        total += float(bars[i]["close"])
    return total / float(period)


def _ma_on_volume(bars, end_idx, period):
    if end_idx < 0:
        return None
    start_idx = end_idx - period + 1
    if start_idx < 0:
        return None
    total = 0.0
    for i in range(start_idx, end_idx + 1):
        total += float(bars[i]["volume"])
    return total / float(period)


def _intraday_avg_price_line(bars, end_idx):
    if end_idx < 0:
        return None
    amount_sum = 0.0
    volume_sum = 0.0
    for i in range(0, end_idx + 1):
        volume = float(bars[i]["volume"])
        if volume <= 0:
            continue
        price = float(bars[i]["close"])
        amount_sum += price * volume
        volume_sum += volume
    if volume_sum <= 0:
        return None
    return amount_sum / volume_sum


def _try_place_buy(context, code, price, now, stop_low=None):
    if not ENABLE_TRADING:
        _log_once(
            "{0}|{1}|trading_disabled".format(now.strftime("%Y%m%d"), code),
            "skip buy {0}: ENABLE_TRADING is False".format(code),
        )
        return

    account_id = _get_account_id(context)
    if not account_id:
        _log_once(
            "{0}|{1}|no_account".format(now.strftime("%Y%m%d"), code),
            "skip buy {0}: account id is empty".format(code),
        )
        return

    cash = None
    try:
        cash = get_available_cash(context)
    except Exception:
        _log_once(
            "{0}|{1}|cash_error".format(now.strftime("%Y%m%d"), code),
            "skip buy {0}: get_available_cash failed".format(code),
        )
        return

    if not cash or cash <= 0:
        _log_once(
            "{0}|{1}|no_cash".format(now.strftime("%Y%m%d"), code),
            "skip buy {0}: available cash <= 0".format(code),
        )
        return

    order_cash = min(cash, ORDER_CASH)
    try:
        ok = place_buy_order(context, code, order_cash)
    except Exception:
        ok = False

    if ok:
        g.bought.add(code)
        _log("buy order accepted code={0} cash={1:.2f}".format(code, order_cash))
        if code in g.pending_buy:
            del g.pending_buy[code]
        if code in g.pending_buy_stop_low:
            del g.pending_buy_stop_low[code]
        if code not in g.entry_price:
            g.entry_price[code] = price
        if stop_low is not None:
            g.buy_day_low[code] = float(stop_low)
        elif code not in g.buy_day_low:
            g.buy_day_low[code] = price
        if code not in g.buy_date:
            g.buy_date[code] = now.strftime("%Y%m%d")
        if code not in g.take_profit_state:
            g.take_profit_state[code] = 0
    else:
        # Retry on next minute bar with latest price
        next_retry = now + datetime.timedelta(minutes=1)
        g.pending_buy[code] = next_retry
        if stop_low is not None:
            g.pending_buy_stop_low[code] = float(stop_low)
        _log_once(
            "{0}|{1}|order_fail".format(now.strftime("%Y%m%d"), code),
            "buy order rejected code={0}, will retry".format(code),
        )


def _check_take_profit(context, now):
    try:
        positions = get_positions(context)
    except Exception:
        return

    if not positions:
        return

    for code, qty in positions.items():
        if qty <= 0:
            continue

        try:
            price = get_current_price(context, code)
        except Exception:
            continue
        if price is None:
            continue

        cost = g.entry_price.get(code)
        if cost is None:
            cost = get_position_cost(context, code)
        if cost is None or cost <= 0:
            continue

        ret = (price / cost) - 1.0
        stage = g.take_profit_state.get(code, 0)

        if stage < 1 and ret >= TAKE_PROFIT_1:
            _sell_ratio(context, code, qty, TAKE_PROFIT_SELL_RATIO)
            g.take_profit_state[code] = 1
            continue

        if stage < 2 and ret >= TAKE_PROFIT_2:
            _sell_ratio(context, code, qty, TAKE_PROFIT_SELL_RATIO)
            g.take_profit_state[code] = 2


def _check_stop_rules(context, trade_date, now):
    try:
        positions = get_positions(context)
    except Exception:
        return

    if not positions:
        return

    for code, qty in positions.items():
        if qty <= 0:
            continue

        # Rule 1: stop loss if current price < buy day low
        try:
            price = get_current_price(context, code)
        except Exception:
            continue
        if price is None:
            continue

        buy_low = g.buy_day_low.get(code)
        if buy_low is not None and price < buy_low:
            _sell_all(context, code, qty)
            continue

        # Rule 3: if today down, and today's volume > yesterday and > avg5, then clear
        if is_today_down_and_volume_expand(context, code, trade_date, now):
            _sell_all(context, code, qty)


def _sell_ratio(context, code, qty, ratio):
    sell_qty = int(qty * ratio)
    if sell_qty <= 0:
        return
    try:
        place_sell_order(context, code, sell_qty)
    except Exception:
        pass


def _sell_all(context, code, qty):
    if qty <= 0:
        return
    try:
        place_sell_order(context, code, qty)
    except Exception:
        pass


def daily_return_ok(bar_prev, bar_curr):
    prev_close = bar_prev["close"]
    curr_close = bar_curr["close"]
    if prev_close <= 0:
        return False
    return (curr_close / prev_close - 1.0) > DAILY_RETURN_MIN


def upper_shadow_ratio(bar):
    high = bar["high"]
    low = bar["low"]
    open_ = bar["open"]
    close = bar["close"]

    total = high - low
    if total <= 0:
        return 0.0

    upper = high - max(open_, close)
    return upper / total


def compute_kdj(bars, n, k_init, d_init):
    """Compute K, D, J series for bars (ascending).

    bars: list of dicts with keys high, low, close
    """
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

        k = (2.0 / 3.0) * k_prev + (1.0 / 3.0) * rsv
        d = (2.0 / 3.0) * d_prev + (1.0 / 3.0) * k
        j = 3.0 * k - 2.0 * d

        k_list.append(k)
        d_list.append(d)
        j_list.append(j)

        k_prev = k
        d_prev = d

    return k_list, d_list, j_list


def calc_volume_ratio(context, code, trade_date, now):
    """Calculate volume ratio using per-minute volume.

    Formula:
      ratio = (today cumulative volume / elapsed minutes)
              / (avg full-day per-minute volume over past 5 trading days)
    """
    window_start = VOLUME_RATIO_WINDOW_START.strftime("%H:%M")
    now_hhmm = now.strftime("%H:%M") if now else VOLUME_RATIO_WINDOW_END.strftime("%H:%M")
    if now_hhmm < window_start:
        now_hhmm = window_start
    window_end = min(now_hhmm, VOLUME_RATIO_WINDOW_END.strftime("%H:%M"))
    elapsed_minutes = _elapsed_minutes_between_hhmm(window_start, window_end)
    if elapsed_minutes <= 0:
        _log("vol_ratio_debug code={0} date={1} elapsed_minutes=0 window={2}-{3}".format(
            code, trade_date, window_start, window_end))
        return None

    try:
        bars = fetch_minute_bars(context, code, trade_date, window_end, 300)
    except Exception:
        _log("vol_ratio_debug code={0} date={1} ERROR fetching today bars".format(code, trade_date))
        return None

    if not bars:
        _log("vol_ratio_debug code={0} date={1} today_bars=EMPTY".format(code, trade_date))
        return None

    today_cum = _sum_window_volume(bars, window_start, window_end)
    if today_cum <= 0:
        _log("vol_ratio_debug code={0} date={1} today_cum=0 (bars_count={2} window={3}-{4})".format(
            code, trade_date, len(bars), window_start, window_end))
        return None
    today_per_min = today_cum / elapsed_minutes

    prev_dates = get_prev_trading_dates(context, trade_date, 5)
    if len(prev_dates) < 5:
        _log("vol_ratio_debug code={0} date={1} prev_dates_count={2} (need 5)".format(
            code, trade_date, len(prev_dates)))
        return None

    hist_per_min_list = []
    cum_detail = []
    for d in prev_dates:
        try:
            d_bars = fetch_minute_bars(context, code, d, "15:00", 600)
        except Exception:
            cum_detail.append("{0}=ERR".format(d))
            continue
        if not d_bars:
            cum_detail.append("{0}=EMPTY".format(d))
            continue
        d_total = _sum_continuous_session_volume(d_bars)
        d_per_min = d_total / TRADING_MINUTES_PER_DAY if TRADING_MINUTES_PER_DAY > 0 else 0.0
        cum_detail.append(
            "{0}={1:.0f}/{2:.0f}m={3:.2f}".format(d, d_total, TRADING_MINUTES_PER_DAY, d_per_min)
        )
        if d_total > 0:
            hist_per_min_list.append(d_per_min)

    if len(hist_per_min_list) < 5:
        _log("vol_ratio_debug code={0} date={1} today_cum={2:.0f} hist_valid={3}/5 hist=[{4}]".format(
            code, trade_date, today_cum, len(hist_per_min_list), ",".join(cum_detail)))
        return None

    avg_prev_per_min = sum(hist_per_min_list) / 5.0
    if avg_prev_per_min <= 0:
        _log("vol_ratio_debug code={0} date={1} today_cum={2:.0f} avg_prev=0".format(
            code, trade_date, today_cum))
        return None

    ratio = today_per_min / avg_prev_per_min
    _log(
        "vol_ratio_debug code={0} date={1} today={2:.0f}/{3:.1f}m={4:.2f} "
        "avg_prev_per_min(full_day)={5:.2f} ratio={6:.2f} hist=[{7}]".format(
            code,
            trade_date,
            today_cum,
            elapsed_minutes,
            today_per_min,
            avg_prev_per_min,
            ratio,
            ",".join(cum_detail),
        )
    )
    return ratio


def _prefetch_volume_ratio_data(context, codes, trade_date, now, prev_dates):
    window_start = VOLUME_RATIO_WINDOW_START.strftime("%H:%M")
    now_hhmm = now.strftime("%H:%M") if now else VOLUME_RATIO_WINDOW_END.strftime("%H:%M")
    if now_hhmm < window_start:
        now_hhmm = window_start
    window_end = min(now_hhmm, VOLUME_RATIO_WINDOW_END.strftime("%H:%M"))
    elapsed_minutes = _elapsed_minutes_between_hhmm(window_start, window_end)

    data = {
        "window_start": window_start,
        "window_end": window_end,
        "elapsed_minutes": elapsed_minutes,
        "today_bars_by_code": {},
        "hist_bars_by_date": {},
        "today_prefetch_ok": False,
        "hist_prefetch_ok_by_date": {},
    }
    if elapsed_minutes <= 0 or not codes:
        return data

    try:
        data["today_bars_by_code"] = fetch_minute_bars_batch(context, codes, trade_date, window_end, 300)
        data["today_prefetch_ok"] = True
    except Exception:
        data["today_bars_by_code"] = {}
        data["today_prefetch_ok"] = False

    for d in prev_dates[:5]:
        try:
            bars_by_code = fetch_minute_bars_batch(context, codes, d, "15:00", 600)
            data["hist_prefetch_ok_by_date"][d] = True
        except Exception:
            bars_by_code = {}
            data["hist_prefetch_ok_by_date"][d] = False
        data["hist_bars_by_date"][d] = bars_by_code
    return data


def _calc_volume_ratio_prefetched(
    code,
    prev_dates,
    elapsed_minutes,
    window_start,
    window_end,
    today_bars_by_code,
    hist_bars_by_date,
    today_prefetch_ok,
    hist_prefetch_ok_by_date,
):
    if elapsed_minutes <= 0:
        return True, None
    if len(prev_dates) < 5:
        return True, None
    if not today_prefetch_ok:
        return False, None

    bars = today_bars_by_code.get(code, [])
    if not bars:
        return True, None
    today_cum = _sum_window_volume(bars, window_start, window_end)
    if today_cum <= 0:
        return True, None
    today_per_min = today_cum / elapsed_minutes

    hist_per_min_list = []
    for d in prev_dates[:5]:
        if not hist_prefetch_ok_by_date.get(d, False):
            return False, None
        d_bars = hist_bars_by_date.get(d, {}).get(code, [])
        if not d_bars:
            continue
        d_total = _sum_continuous_session_volume(d_bars)
        d_per_min = d_total / TRADING_MINUTES_PER_DAY if TRADING_MINUTES_PER_DAY > 0 else 0.0
        if d_total > 0:
            hist_per_min_list.append(d_per_min)

    if len(hist_per_min_list) < 5:
        return True, None
    avg_prev_per_min = sum(hist_per_min_list) / 5.0
    if avg_prev_per_min <= 0:
        return True, None
    return True, (today_per_min / avg_prev_per_min)


def is_downtrend(context, code, trade_date, now):
    """Placeholder for downtrend definition.

    Default: current price < today open price.
    """
    try:
        bars = fetch_minute_bars(context, code, trade_date, now.strftime("%H:%M"), 240)
    except Exception:
        return False

    if not bars:
        return False

    current_price = bars[-1]["close"]
    open_price = bars[0]["open"]
    return current_price < open_price


def is_today_down_and_volume_expand(context, code, trade_date, now):
    t_date = get_trading_calendar_prev_date(context, trade_date)
    try:
        daily = fetch_daily_bars(context, code, t_date, 6)
    except Exception:
        return False

    if len(daily) < 6:
        return False

    prev_close = daily[-1]["close"]
    prev_volume = daily[-1]["volume"]
    avg5 = sum(b["volume"] for b in daily[-6:-1]) / 5.0

    try:
        current_price = get_current_price(context, code)
    except Exception:
        return False

    if current_price >= prev_close:
        return False

    # today's cumulative volume
    try:
        bars = fetch_minute_bars(context, code, trade_date, now.strftime("%H:%M"), 240)
    except Exception:
        return False

    if not bars:
        return False

    today_cum = sum(b["volume"] for b in bars)
    return today_cum > prev_volume and today_cum > avg5


# --- Helpers ---

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

    # Prefer QMT helper if available.
    if "timetag_to_datetime" in globals():
        try:
            ts = timetag_to_datetime(timetag, "%Y%m%d%H%M%S")
            return datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")
        except Exception:
            pass

    s = str(timetag).strip()
    digits = "".join(ch for ch in s if ch.isdigit())

    # Common format: YYYYMMDDHHMMSS
    if len(digits) >= 14:
        try:
            return datetime.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        except Exception:
            pass

    # Epoch milliseconds
    if len(digits) == 13:
        try:
            return datetime.datetime.fromtimestamp(int(digits) / 1000.0)
        except Exception:
            pass

    # Epoch seconds
    if len(digits) == 10:
        try:
            return datetime.datetime.fromtimestamp(int(digits))
        except Exception:
            pass

    return None


def is_main_board_a_share(stock_code):
    """Return True if stock_code is main-board A-share (exclude ChiNext/STAR).
    Expected formats: "600000.SH", "000001.SZ", etc.
    """
    if not stock_code:
        return False

    code = stock_code.split(".")[0]

    # Exclude ChiNext (300*) and STAR (688*, 689*)
    if code.startswith("300") or code.startswith("688") or code.startswith("689"):
        return False

    # Main board prefixes: SH 600/601/603/605, SZ 000/001/002
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
    """Normalize symbol to 6-digit + .SH/.SZ if possible."""
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


def get_prev_trading_dates(context, date_str, count):
    date_str = _normalize_trade_date(date_str)
    if not date_str:
        return []

    try:
        dates = context.get_trading_dates("SH", "", date_str, count + 1, "1d")
        if len(dates) >= count + 1:
            return [_normalize_trade_date(d) for d in dates[-count - 1 : -1]]
    except Exception:
        pass

    dates = []
    cur = date_str
    for _ in range(count):
        cur = get_trading_calendar_prev_date(context, cur)
        dates.append(cur)
    return dates


def _get_account_id(context):
    if getattr(g, "account_id", ""):
        return g.account_id
    if ACCOUNT_ID:
        return ACCOUNT_ID
    return globals().get("account", "")


def _sum_window_volume(bars, start_hhmm, end_hhmm):
    total = 0.0
    for b in bars:
        t = b.get("time", "")
        if t and start_hhmm <= t <= end_hhmm:
            try:
                total += float(b.get("volume", 0.0))
            except Exception:
                continue
    return total


def _sum_continuous_session_volume(bars):
    total = 0.0
    for b in bars:
        t = b.get("time", "")
        if _is_continuous_auction_time(t):
            try:
                total += float(b.get("volume", 0.0))
            except Exception:
                continue
    return total


def _is_continuous_auction_time(hhmm):
    if not hhmm:
        return False
    return ("09:30" <= hhmm <= "11:30") or ("13:00" <= hhmm <= "15:00")


def _elapsed_minutes_between_hhmm(start_hhmm, end_hhmm):
    try:
        sh, sm = int(start_hhmm[:2]), int(start_hhmm[3:5])
        eh, em = int(end_hhmm[:2]), int(end_hhmm[3:5])
    except Exception:
        return 0.0

    start_m = sh * 60 + sm
    end_m = eh * 60 + em
    if end_m <= start_m:
        return 0.0
    return float(end_m - start_m)


def _extract_yyyymmdd_hhmm(index_value):
    """Parse various QMT/pandas index formats to (YYYYMMDD, HHMM)."""
    s = str(index_value).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 12:
        return digits[:8], digits[8:12]
    if len(digits) >= 8:
        return digits[:8], ""
    return "", ""


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


def _minute_df_to_bars(df, trade_date, end_hhmm):
    bars = []
    try:
        iterator = df.iterrows()
    except Exception:
        return bars

    for idx, row in iterator:
        d, hhmm = _extract_yyyymmdd_hhmm(idx)
        if d != trade_date or (hhmm and hhmm > end_hhmm):
            continue
        if not hhmm:
            continue
        try:
            bars.append(
                {
                    "time": hhmm[:2] + ":" + hhmm[2:],
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


def _log_end_of_day_entry_stats(trade_date):
    if not g.watchlist:
        _log("entry_stats day={0} watchlist_empty".format(trade_date))
        return

    parts = []
    for code in g.watchlist[:10]:
        st = g.entry_check_stats.get(code, {})
        checks = int(st.get("checks", 0))
        hits = int(st.get("hits", 0))
        parts.append("{0}:{1}/{2}".format(code, hits, checks))

    _log(
        "entry_stats day={0} bought={1} trigger_hits/checks {2}".format(
            trade_date, len(g.bought), ",".join(parts)
        )
    )


def _normalize_trade_date(value):
    """Normalize date-like value to YYYYMMDD."""
    if value is None:
        return ""

    s = str(value).strip()
    if not s:
        return ""

    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""

    # epoch milliseconds
    if len(digits) == 13:
        try:
            return datetime.datetime.fromtimestamp(int(digits) / 1000.0).strftime("%Y%m%d")
        except Exception:
            return ""

    # epoch seconds
    if len(digits) == 10:
        try:
            return datetime.datetime.fromtimestamp(int(digits)).strftime("%Y%m%d")
        except Exception:
            return ""

    # datetime-like string
    if len(digits) >= 8:
        return digits[:8]

    return ""


def _log(msg):
    try:
        print("[{0}] {1}".format(STRATEGY_NAME, msg))
    except Exception:
        pass


def _log_once(key, msg):
    try:
        logged = getattr(g, "logged_once", None)
        if logged is None:
            g.logged_once = set()
            logged = g.logged_once
        if key in logged:
            return
        logged.add(key)
    except Exception:
        pass
    _log(msg)
