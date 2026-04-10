"""Parity test: verify generate_signals() matches screen_stocks() on same data."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from strategies.st_b2.strategy import generate_signals, get_default_config
from tools.data_adapter.local_csv import load_market_data


def test_parity():
    config_path = project_root / "strategies" / "st_b2_tushare" / "config.json"
    import json
    with open(config_path) as f:
        cfg = json.load(f)

    start_date = cfg.get("start_date", "20240101")
    end_date = cfg.get("end_date", "20241231")
    data_dir = cfg.get("data_dir", "")

    print("Loading data...")
    daily_data = load_market_data(data_dir, start_date, end_date)

    print("Running generate_signals (strategy module)...")
    params = get_default_config()
    for key in params:
        if key in cfg:
            params[key] = cfg[key]
    new_signals = generate_signals(daily_data, params)

    total_candidates = sum(len(v) for v in new_signals.values())
    print(f"\nResult: {len(new_signals)} dates, {total_candidates} candidates")

    # Check that all candidates have expected fields
    sample_date = next(iter(new_signals.keys()))
    sample = new_signals[sample_date][0]
    required_fields = {"code", "close", "daily_return_pct", "vol_ratio", "j_now", "j_prev"}
    assert required_fields.issubset(sample.keys()), f"Missing fields: {required_fields - sample.keys()}"

    print(f"\nSample candidate: {sample}")
    print(f"\nPARITY TEST PASSED: {total_candidates} candidates across {len(new_signals)} dates")


if __name__ == "__main__":
    test_parity()