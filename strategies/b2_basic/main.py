#coding:gbk
"""
Strategy: b2_basic

Rules (current):
- T is the last completed trading day.
- Daily filters on T and T-1:
  1) J(T-1) < 20 (KDJ)
  2) J(T) < 65 (KDJ)
  3) T daily return > 4%
  4) T volume > T-1 volume
  5) T upper shadow < 20% of full candle range
- At T+1 09:35: from candidates, pick top 3 by volume ratio (>20) in a downtrend.
- Entry: buy when price rises >= 3 ticks from the intraday low.
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

STRATEGY_NAME = "b2_basic"

# --- Config (confirm/adjust with final rules) ---
DAILY_KDJ_N = 9
KDJ_INIT = 50.0

J_T_MINUS1_MAX = 20.0
J_T_MAX = 65.0
DAILY_RETURN_MIN = 0.04
UPPER_SHADOW_MAX_RATIO = 0.20

VOLUME_RATIO_MIN = 20.0
WATCHLIST_SIZE = 3
WATCHLIST_TIME = datetime.time(9, 35)

MINUTE_BAR_PERIOD = "1m"

ENTRY_TICK_MIN = 3
ENTRY_TICK_MAX = None  # if price jumps above 4 ticks, still buy
TICK_SIZE = 0.01

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
                subscribe=False,
            )
            cur = data.get(code)
            if cur is not None and (not cur.empty):
                df = cur
                break
        except Exception:
            continue
    if df is None or df.empty:
        return []

    bars = []
    for idx, row in df.iterrows():
        date_str = str(idx)[:8]
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
    return bars


def fetch_minute_bars(context, code, trade_date, end_time, count):
    """Return list of minute bars for trade_date up to end_time (inclusive).

    Each bar is a dict with keys: time, open, high, low, close, volume
    time: "HH:MM"
    """
    trade_date = _normalize_trade_date(trade_date)
    if not trade_date:
        return []

    end_ts = trade_date + end_time.replace(":", "") + "00"
    data = context.get_market_data_ex(
        ["open", "high", "low", "close", "volume"],
        [code],
        period="1m",
        start_time="",
        end_time=end_ts,
        count=count,
        dividend_type="none",
        fill_data=True,
        subscribe=True,
    )
    df = data.get(code)
    if df is None or df.empty:
        return []

    bars = []
    for idx, row in df.iterrows():
        idx_str = str(idx)
        if not idx_str.startswith(trade_date):
            continue
        time_str = idx_str[8:12]
        bars.append(
            {
                "time": time_str[:2] + ":" + time_str[2:],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return bars


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
    g.intraday_low = {}
    g.bought = set()
    g.pending_buy = {}
    g.entry_price = {}
    g.buy_day_low = {}
    g.buy_date = {}
    g.take_profit_state = {}
    g.exit_checked = None

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
        g.intraday_low = {}
        g.bought = set()

        t_date = get_trading_calendar_prev_date(context, trade_date)
        g.daily_candidates = build_daily_candidates(context, t_date)
        _log(
            "new day={0}, prev_day={1}, candidates={2}".format(
                trade_date, t_date, len(g.daily_candidates)
            )
        )

    # Build watchlist at 09:35
    if (not g.watchlist_built) and now.time() >= WATCHLIST_TIME:
        g.watchlist = build_watchlist(context, trade_date, now)
        g.watchlist_built = True

    # Monitor watchlist for entry and retry pending orders
    for code in g.watchlist:
        try:
            price = get_current_price(context, code)
        except Exception:
            continue
        if price is None:
            continue

        update_intraday_low(context, code, price)
        _update_buy_day_low(context, code, trade_date)

        if code in g.bought:
            continue

        if should_buy_from_low(context, code, price):
            _try_place_buy(context, code, price, now)

        # If prior buy failed, retry at next minute with latest price
        if code in g.pending_buy and now >= g.pending_buy[code]:
            _try_place_buy(context, code, price, now)

    # Profit-taking checks (any time)
    _check_take_profit(context, now)

    # Stop-loss and volume-based exit checks at 14:45
    if now.time() >= STOP_CHECK_TIME and g.exit_checked != trade_date:
        _check_stop_rules(context, trade_date, now)
        g.exit_checked = trade_date


# --- Core logic ---

def build_daily_candidates(context, t_date):
    candidates = []
    stats = {
        "total": 0,
        "bars_short": 0,
        "kdj_t1_fail": 0,
        "kdj_t_fail": 0,
        "ret_fail": 0,
        "vol_fail": 0,
        "upper_shadow_fail": 0,
    }
    stats["total"] = len(g.universe)
    short_samples = []

    for code in g.universe:
        if not is_main_board_a_share(code):
            continue

        bars = []
        try:
            bars = fetch_daily_bars(context, code, t_date, DAILY_KDJ_N + 2)
        except Exception:
            continue

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
        if bar_t["volume"] <= bar_t_minus1["volume"]:
            stats["vol_fail"] += 1
            continue
        if upper_shadow_ratio(bar_t) >= UPPER_SHADOW_MAX_RATIO:
            stats["upper_shadow_fail"] += 1
            continue

        candidates.append(code)

    _log(
        "daily_filter_stats total={0} bars_short={1} kdj_t1_fail={2} "
        "kdj_t_fail={3} ret_fail={4} vol_fail={5} upper_shadow_fail={6} pass={7}".format(
            stats["total"],
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
    for code in g.daily_candidates:
        vol_ratio = calc_volume_ratio(context, code, trade_date, now)
        if vol_ratio is None or vol_ratio <= VOLUME_RATIO_MIN:
            continue
        if not is_downtrend(context, code, trade_date, now):
            continue
        ranked.append((code, vol_ratio))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [code for code, _ in ranked[:WATCHLIST_SIZE]]


def should_buy_from_low(context, code, price):
    if price is None:
        return False
    low = g.intraday_low.get(code)
    if low is None:
        return False

    min_price = low + ENTRY_TICK_MIN * TICK_SIZE
    if price < min_price:
        return False
    return True


def update_intraday_low(context, code, price):
    if price is None:
        return
    low = g.intraday_low.get(code)
    if low is None or price < low:
        g.intraday_low[code] = price


def _update_buy_day_low(context, code, trade_date):
    buy_date = g.buy_date.get(code)
    if buy_date != trade_date:
        return
    cur_low = g.intraday_low.get(code)
    if cur_low is None:
        return
    prev_low = g.buy_day_low.get(code)
    if prev_low is None or cur_low < prev_low:
        g.buy_day_low[code] = cur_low


def _try_place_buy(context, code, price, now):
    if not ENABLE_TRADING:
        return

    cash = None
    try:
        cash = get_available_cash(context)
    except Exception:
        return

    if not cash or cash <= 0:
        return

    order_cash = min(cash, ORDER_CASH)
    try:
        ok = place_buy_order(context, code, order_cash)
    except Exception:
        ok = False

    if ok:
        g.bought.add(code)
        if code in g.pending_buy:
            del g.pending_buy[code]
        if code not in g.entry_price:
            g.entry_price[code] = price
        if code not in g.buy_day_low:
            g.buy_day_low[code] = g.intraday_low.get(code, price)
        if code not in g.buy_date:
            g.buy_date[code] = now.strftime("%Y%m%d")
        if code not in g.take_profit_state:
            g.take_profit_state[code] = 0
    else:
        # Retry on next minute bar with latest price
        next_retry = now + datetime.timedelta(minutes=1)
        g.pending_buy[code] = next_retry


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
    """Calculate volume ratio at time now.

    Definition: current cumulative volume / average cumulative volume at
    the same time over the past 5 trading days.
    """
    try:
        bars = fetch_minute_bars(context, code, trade_date, now.strftime("%H:%M"), 240)
    except Exception:
        return None

    if not bars:
        return None

    today_cum = sum(b["volume"] for b in bars)
    if today_cum <= 0:
        return None

    prev_dates = get_prev_trading_dates(context, trade_date, 5)
    if len(prev_dates) < 5:
        return None

    cum_list = []
    for d in prev_dates:
        try:
            d_bars = fetch_minute_bars(context, code, d, now.strftime("%H:%M"), 240)
        except Exception:
            continue
        if not d_bars:
            continue
        cum_list.append(sum(b["volume"] for b in d_bars))

    if len(cum_list) < 5:
        return None

    avg_prev = sum(cum_list) / 5.0
    if avg_prev <= 0:
        return None

    return today_cum / avg_prev


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
