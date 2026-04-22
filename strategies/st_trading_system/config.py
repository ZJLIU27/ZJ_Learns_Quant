"""Configuration for the Streamlit trading system."""

from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = "D:/Git/QuanToolkit/data"
PORTFOLIO_PATH = str(_BASE_DIR / "portfolio.json")
APP_TITLE = "交易管理系统"
