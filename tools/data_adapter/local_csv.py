"""LocalCSV data provider.

Loads daily OHLCV data from local CSV files produced by tushare export.
Canonical DataFrame schema: trade_date, open, high, low, close, vol

By default the stock universe is limited to main-board A-shares. Callers can
optionally include growth boards (300/688/689) when scanning.
"""

import warnings
from pathlib import Path

import pandas as pd

MAIN_BOARD_PREFIXES = ("600", "601", "603", "605", "000", "001", "002")


def is_main_board(code: str) -> bool:
    """Check if a stock code (e.g. '000001') belongs to main board."""
    if code.startswith(("300", "688", "689")):
        return False
    return code.startswith(MAIN_BOARD_PREFIXES)


def get_stock_list(data_dir: str, include_growth_boards: bool = False) -> list[str]:
    """Scan data_dir for CSV files and return A-share stock codes.

    Args:
        data_dir: Path to directory containing <code>.csv files.
        include_growth_boards: If True, also include 创业板 (300) and 科创板
            (688/689). Default False keeps the previous main-board-only behavior.

    Returns:
        Sorted list of stock code strings.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    codes = []
    for csv_file in data_path.glob("*.csv"):
        code = csv_file.stem
        if is_main_board(code):
            codes.append(code)
        elif include_growth_boards and code.startswith(("300", "688", "689")):
            codes.append(code)
    return sorted(codes)


def load_market_data(
    data_dir: str,
    start_date: str,
    end_date: str,
    stock_codes: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Load daily market data from local CSV files.

    Args:
        data_dir: Path to directory containing <code>.csv files.
        start_date: Start date in YYYYMMDD format.
        end_date: End date in YYYYMMDD format.
        stock_codes: Optional filter — only load these codes. If None, loads all main-board.

    Returns:
        {stock_code: DataFrame} with columns: trade_date, open, high, low, close, vol
        DataFrames are sorted by trade_date ascending and filtered to date range.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    # If no stock_codes filter provided, load all main-board stocks
    if stock_codes is None:
        stock_codes = get_stock_list(data_dir)

    # Convert stock_codes to set for fast lookup (only if we're filtering from files)
    code_set = set(stock_codes)

    result = {}
    csv_files = sorted(data_path.glob("*.csv"))
    print(f"Loading data from {data_dir} ({len(csv_files)} files, {len(stock_codes)} stocks)...")

    skipped = 0
    for csv_file in csv_files:
        code = csv_file.stem

        # Skip non-main-board and non-requested codes
        if code not in code_set:
            continue

        try:
            df = pd.read_csv(csv_file, dtype={"date": str})
        except Exception:
            skipped += 1
            continue

        if df.empty:
            skipped += 1
            continue

        # Normalize columns: date → trade_date, volume → vol
        if "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})
        if "volume" in df.columns:
            df = df.rename(columns={"volume": "vol"})

        # Convert date format YYYY-MM-DD → YYYYMMDD if needed
        if df["trade_date"].dtype == object:
            df["trade_date"] = df["trade_date"].str.replace("-", "")

        # Ensure canonical schema: trade_date, open, high, low, close, vol
        required = {"trade_date", "open", "high", "low", "close", "vol"}
        if not required.issubset(df.columns):
            skipped += 1
            continue

        # Filter by date range
        df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)]
        df = df.sort_values("trade_date").reset_index(drop=True)

        if not df.empty:
            result[code] = df

    if skipped > 0:
        print(f"  Skipped {skipped} files (empty/malformed/missing columns)")
    print(f"  Loaded {len(result)} stocks.")
    return result
