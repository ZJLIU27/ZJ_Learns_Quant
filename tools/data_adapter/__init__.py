"""Data adapter for st_b2 backtesting.

Provides unified data loading with canonical DataFrame schema:
  trade_date, open, high, low, close, vol

Currently supports LocalCSVProvider. TushareProvider can be added later.
"""

from .local_csv import load_market_data, get_stock_list

__all__ = ["load_market_data", "get_stock_list", "create_provider"]


def create_provider(config: dict):
    """Return data loading functions based on config.

    Args:
        config: Dict with optional 'data_source' key ('local_csv' default).

    Returns:
        Object with load_market_data() and get_stock_list() methods.
    """
    source = config.get("data_source", "local_csv")
    if source == "local_csv":
        return _LocalCSVProvider(config)
    raise ValueError(f"Unknown data source: {source}")


class _LocalCSVProvider:
    """Duck-typed provider wrapping local_csv functions."""

    def __init__(self, config: dict):
        self.data_dir = config.get("data_dir", "")
        if not self.data_dir:
            raise ValueError("config must include 'data_dir' for local_csv provider")

    def load_market_data(self, stock_codes: list[str], start_date: str, end_date: str) -> dict:
        return load_market_data(self.data_dir, start_date, end_date, stock_codes=stock_codes)

    def get_stock_list(self) -> list[str]:
        return get_stock_list(self.data_dir)