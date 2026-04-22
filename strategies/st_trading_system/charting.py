"""Shared chart data builder for screener and positions views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .indicator_presets import apply_indicator_presets


@dataclass(frozen=True)
class ChartTraceSpec:
    """A render-agnostic chart trace description."""

    kind: Literal["candlestick", "line", "bar"]
    name: str
    y_column: str | None = None
    open_column: str | None = None
    high_column: str | None = None
    low_column: str | None = None
    close_column: str | None = None
    color: str | None = None
    width: float | None = None
    dash: str | None = None
    opacity: float = 1.0


@dataclass(frozen=True)
class ChartHorizontalLine:
    """Horizontal guide line for a subchart."""

    y: float
    color: str
    dash: str = "dot"
    width: float = 1.0


@dataclass
class ChartPanelSpec:
    """One panel of a chart bundle."""

    panel_id: str
    title: str
    traces: list[ChartTraceSpec] = field(default_factory=list)
    hlines: list[ChartHorizontalLine] = field(default_factory=list)


@dataclass
class ChartBundle:
    """Structured chart payload that a UI renderer can turn into figures."""

    code: str
    end_date: str | None
    resolved_indicator_ids: list[str]
    df: pd.DataFrame
    main_panel: ChartPanelSpec
    subcharts: list[ChartPanelSpec] = field(default_factory=list)


def build_stock_chart(
    code: str,
    end_date: str | None,
    days: int,
    active_indicator_ids: list[str],
    provider,
) -> ChartBundle | None:
    """Build a shared stock chart payload for the UI."""
    df = provider.get_history(code=code, end_date=end_date, days=days)
    if df is None or df.empty:
        return None

    resolved_ids = list(dict.fromkeys(active_indicator_ids))
    enriched = apply_indicator_presets(df, resolved_ids)

    main_panel = ChartPanelSpec(
        panel_id="price",
        title="主图",
        traces=[
            ChartTraceSpec(
                kind="candlestick",
                name="OHLC",
                open_column="open",
                high_column="high",
                low_column="low",
                close_column="close",
            )
        ],
    )
    subcharts: list[ChartPanelSpec] = []

    overlay_specs = {
        "bbi": ChartTraceSpec(kind="line", name="BBI", y_column="bbi", color="#F0B90B", width=1.5),
        "white_line": ChartTraceSpec(kind="line", name="白线", y_column="white_line", color="#FFFFFF", width=1.2),
        "yellow_line": ChartTraceSpec(
            kind="line",
            name="黄线",
            y_column="yellow_line",
            color="#FFD000",
            width=1.2,
            dash="dash",
        ),
    }
    for indicator_id in ("bbi", "white_line", "yellow_line"):
        if indicator_id in resolved_ids:
            main_panel.traces.append(overlay_specs[indicator_id])

    if "danzhen_panel" in resolved_ids:
        subcharts.append(
            ChartPanelSpec(
                panel_id="danzhen_panel",
                title="单针下20",
                traces=[
                    ChartTraceSpec(kind="line", name="短", y_column="danzhen_short", color="#FFFFFF"),
                    ChartTraceSpec(kind="line", name="中", y_column="danzhen_medium", color="#F0B90B"),
                    ChartTraceSpec(kind="line", name="中长", y_column="danzhen_medium_long", color="#FF00FF"),
                    ChartTraceSpec(kind="line", name="长", y_column="danzhen_long", color="#F6465D", width=2.0),
                    ChartTraceSpec(
                        kind="bar",
                        name="四线0",
                        y_column="danzhen_four_line_zero",
                        color="#0000FF",
                        opacity=0.45,
                    ),
                    ChartTraceSpec(
                        kind="bar",
                        name="短下20",
                        y_column="danzhen_short_below_20",
                        color="#00FFFF",
                        opacity=0.45,
                    ),
                    ChartTraceSpec(
                        kind="bar",
                        name="短穿中长",
                        y_column="danzhen_short_cross_long",
                        color="#00FF00",
                        opacity=0.45,
                    ),
                    ChartTraceSpec(
                        kind="bar",
                        name="短穿中",
                        y_column="danzhen_short_cross_medium",
                        color="#FF9150",
                        opacity=0.45,
                    ),
                ],
                hlines=[
                    ChartHorizontalLine(y=20.0, color="#0ECB81"),
                    ChartHorizontalLine(y=80.0, color="#0ECB81"),
                ],
            )
        )

    if "zhuan_panel" in resolved_ids:
        zhuan_series = enriched["signal_zhuan"]
        prev = zhuan_series.shift(1)
        enriched = enriched.copy()
        enriched["zhuan_up"] = zhuan_series.where(prev < zhuan_series)
        enriched["zhuan_down"] = zhuan_series.where(prev > zhuan_series)
        subcharts.append(
            ChartPanelSpec(
                panel_id="zhuan_panel",
                title="砖型图",
                traces=[
                    ChartTraceSpec(kind="line", name="砖型图", y_column="signal_zhuan", color="#777E90", width=1.0),
                    ChartTraceSpec(kind="line", name="红持", y_column="zhuan_up", color="#F6465D", width=2.0),
                    ChartTraceSpec(kind="line", name="绿空", y_column="zhuan_down", color="#0ECB81", width=2.0),
                ],
            )
        )

    return ChartBundle(
        code=code,
        end_date=end_date,
        resolved_indicator_ids=resolved_ids,
        df=enriched,
        main_panel=main_panel,
        subcharts=subcharts,
    )
