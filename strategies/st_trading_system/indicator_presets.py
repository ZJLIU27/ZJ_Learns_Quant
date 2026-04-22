"""Registry for chart indicator presets used by the Streamlit UI."""

from __future__ import annotations

import pandas as pd

from .indicators import calc_bbi, calc_danzhen_panel, calc_white_line, calc_yellow_line, calc_zhuan
from .models import IndicatorPreset

_PRESETS: dict[str, IndicatorPreset] = {
    "bbi": IndicatorPreset(
        id="bbi",
        name="BBI",
        panel="overlay",
        description="主图叠加 BBI 线",
        default_strategy_ids=["b1"],
    ),
    "white_line": IndicatorPreset(
        id="white_line",
        name="白线(Z_短期趋势线)",
        panel="overlay",
        description="主图叠加双 EMA 白线",
        default_strategy_ids=["b1"],
    ),
    "yellow_line": IndicatorPreset(
        id="yellow_line",
        name="黄线/多空线(Z_多空线)",
        panel="overlay",
        description="主图叠加多空线",
        default_strategy_ids=["b1"],
    ),
    "danzhen_panel": IndicatorPreset(
        id="danzhen_panel",
        name="单针下20",
        panel="subchart",
        description="单针下20四线、参考线和信号柱",
        default_strategy_ids=["danzhen20"],
    ),
    "zhuan_panel": IndicatorPreset(
        id="zhuan_panel",
        name="砖型图",
        panel="subchart",
        description="砖型图主线与红涨绿跌分段",
        default_strategy_ids=["zhuan"],
    ),
}

_PRESET_ORDER = ["bbi", "white_line", "yellow_line", "danzhen_panel", "zhuan_panel"]


def _clone_preset(preset: IndicatorPreset) -> IndicatorPreset:
    return IndicatorPreset(
        id=preset.id,
        name=preset.name,
        panel=preset.panel,
        description=preset.description,
        default_strategy_ids=list(preset.default_strategy_ids),
    )


def list_indicator_presets() -> list[IndicatorPreset]:
    """Return presets in stable UI order."""
    return [_clone_preset(_PRESETS[preset_id]) for preset_id in _PRESET_ORDER]


def get_indicator_preset(preset_id: str) -> IndicatorPreset | None:
    preset = _PRESETS.get(preset_id)
    if preset is None:
        return None
    return _clone_preset(preset)


def get_default_indicator_ids(strategy_ids: list[str]) -> list[str]:
    """Resolve the default indicator presets implied by the hit strategies."""
    strategy_id_set = set(strategy_ids)
    resolved: list[str] = []
    for preset_id in _PRESET_ORDER:
        preset = _PRESETS[preset_id]
        if strategy_id_set.intersection(preset.default_strategy_ids):
            resolved.append(preset_id)
    return resolved


def apply_indicator_presets(df: pd.DataFrame, indicator_ids: list[str]) -> pd.DataFrame:
    """Apply the selected indicator presets to a price DataFrame."""
    enriched = df.copy()
    for indicator_id in dict.fromkeys(indicator_ids):
        if indicator_id == "bbi":
            enriched = calc_bbi(enriched)
        elif indicator_id == "white_line":
            enriched = calc_white_line(enriched)
        elif indicator_id == "yellow_line":
            enriched = calc_yellow_line(enriched)
        elif indicator_id == "danzhen_panel":
            enriched = calc_danzhen_panel(enriched)
        elif indicator_id == "zhuan_panel":
            enriched = calc_zhuan(enriched)
        else:
            raise KeyError(f"Unknown indicator preset: {indicator_id}")
    return enriched
