"""Two-tab Streamlit app for screening and position monitoring."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - depends on local runtime
    st = None

from strategies.st_trading_system import storage
from strategies.st_trading_system.charting import ChartBundle, build_stock_chart
from strategies.st_trading_system.config import APP_TITLE, DATA_DIR, PORTFOLIO_PATH
from strategies.st_trading_system.data_provider import LocalCSVProvider
from strategies.st_trading_system.indicator_presets import (
    get_default_indicator_ids,
    get_indicator_preset,
    list_indicator_presets,
)
from strategies.st_trading_system.models import Position, ScreeningResult
from strategies.st_trading_system.monitors import (
    refresh_monitors,
    registry_errors as monitor_registry_errors,
)
from strategies.st_trading_system.positions import monitor_positions
from strategies.st_trading_system.screener import screen
from strategies.st_trading_system.substrategies import (
    list_substrategies,
    refresh_substrategies,
    registry_errors as substrategy_registry_errors,
)

_YELLOW = "#F0B90B"
_GOLD = "#FFD000"
_DARK_BG = "#222126"
_DARK_CARD = "#2B2F36"
_WHITE = "#FFFFFF"
_SNOW = "#F5F5F5"
_INK = "#1E2026"
_SLATE = "#848E9C"
_GREEN = "#0ECB81"
_RED = "#F6465D"
_BLUE = "#1EAEDB"
_BORDER = "#E6E8EA"
_WARNING = "#D0980B"

_CSS = f"""
<style>
    html, body, [class*="st-"] {{
        color: {_INK};
        font-family: "Segoe UI", Arial, sans-serif;
    }}
    #MainMenu {{ visibility: hidden; }}
    header {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}

    .app-header {{
        background: {_DARK_BG};
        border-radius: 16px;
        padding: 18px 22px;
        margin-bottom: 18px;
        display: flex;
        align-items: center;
        gap: 14px;
    }}
    .logo-mark {{
        width: 34px;
        height: 34px;
        border-radius: 10px;
        background: {_YELLOW};
        color: {_INK};
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
    }}
    .app-header h1 {{
        margin: 0;
        color: {_WHITE};
        font-size: 22px;
        font-weight: 600;
    }}
    .app-header .subtitle {{
        margin-left: auto;
        color: {_SLATE};
        font-size: 13px;
    }}
    .dark-band {{
        background: {_DARK_BG};
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 18px;
    }}
    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px;
    }}
    .metric-card {{
        background: {_DARK_CARD};
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 14px 10px;
        text-align: center;
    }}
    .metric-card .value {{
        color: {_YELLOW};
        font-weight: 700;
        font-size: 26px;
        line-height: 1;
    }}
    .metric-card .label {{
        color: {_SLATE};
        font-size: 12px;
        margin-top: 8px;
    }}
    .banner-error {{
        background: rgba(246, 70, 93, 0.08);
        border: 1px solid rgba(246, 70, 93, 0.35);
        color: {_RED};
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }}
    .row-card {{
        border: 1px solid {_BORDER};
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 10px;
        background: {_WHITE};
    }}
    .row-card.alert {{
        background: rgba(246, 70, 93, 0.06);
        border-color: rgba(246, 70, 93, 0.25);
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background: {_SNOW};
        border-radius: 10px;
        padding: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px !important;
        font-weight: 600;
    }}
    .stTabs [aria-selected="true"] {{
        background: {_WHITE} !important;
        color: {_YELLOW} !important;
    }}
    .strategy-chip {{
        display: inline-block;
        background: rgba(240, 185, 11, 0.12);
        color: #9A6B00;
        border-radius: 999px;
        padding: 2px 8px;
        margin-right: 6px;
        font-size: 11px;
        font-weight: 600;
    }}
    .inline-note {{
        color: {_SLATE};
        font-size: 12px;
    }}
    @media (max-width: 900px) {{
        .metric-grid {{
            grid-template-columns: repeat(2, 1fr);
        }}
        .app-header {{
            flex-wrap: wrap;
        }}
        .app-header .subtitle {{
            margin-left: 0;
            width: 100%;
        }}
    }}
</style>
"""


def _ensure_streamlit() -> None:
    if st is None:
        raise RuntimeError(
            "streamlit 未安装，无法启动 UI。请先安装 strategies/st_trading_system/requirements.txt 中的依赖。"
        )


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _position_to_dict(position: Position) -> dict:
    return {
        "code": position.code,
        "entry_date": position.entry_date,
        "cost_basis": position.cost_basis,
        "strategy_ids": list(position.strategy_ids),
        "quantity": position.quantity,
        "notes": position.notes,
    }


def _dict_to_position(payload: dict) -> Position:
    return Position(
        code=payload["code"],
        entry_date=payload["entry_date"],
        cost_basis=float(payload["cost_basis"]),
        strategy_ids=list(payload.get("strategy_ids", [])),
        quantity=payload.get("quantity"),
        notes=payload.get("notes", ""),
    )


def _data_provider() -> LocalCSVProvider:
    if "provider" not in st.session_state:
        st.session_state["provider"] = LocalCSVProvider(DATA_DIR)
    return st.session_state["provider"]


def _scan_cache() -> dict:
    if "scan_cache" not in st.session_state:
        st.session_state["scan_cache"] = {}
    return st.session_state["scan_cache"]


def _reload_positions() -> None:
    st.session_state["positions"] = [
        _position_to_dict(position)
        for position in storage.load_positions(PORTFOLIO_PATH)
    ]
    st.session_state["positions_loaded"] = True


def _combined_registry_errors() -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    for module_name, error in substrategy_registry_errors():
        errors.append((f"substrategies/{module_name}.py", error))
    for module_name, error in monitor_registry_errors():
        errors.append((f"monitors/{module_name}.py", error))
    return errors


def _render_errors() -> None:
    for file_name, error in _combined_registry_errors():
        st.markdown(
            f'<div class="banner-error"><strong>{file_name}</strong> {error}</div>',
            unsafe_allow_html=True,
        )


def _status_color(status: str) -> str:
    if status == "alert":
        return _RED
    if status == "ok":
        return _GREEN
    return _WARNING


def _resolve_selected_screen_code(
    results: list[ScreeningResult],
    previous_code: str | None,
) -> str | None:
    if not results:
        return None

    codes = [result.code for result in results]
    if previous_code in codes:
        return previous_code
    return codes[0]


def _resolve_screen_indicator_ids(
    hit_ids: list[str],
    manual_indicator_ids: list[str],
) -> list[str]:
    default_ids = get_default_indicator_ids(hit_ids)
    return list(dict.fromkeys(default_ids + list(manual_indicator_ids)))


def _format_screening_option(code: str, result_map: dict[str, ScreeningResult]) -> str:
    result = result_map[code]
    return f"{code} | {', '.join(result.hit_ids)}"


def _format_indicator_option(indicator_id: str) -> str:
    preset = get_indicator_preset(indicator_id)
    if preset is None:
        return indicator_id
    return preset.name


def _render_chart_bundle(
    bundle: ChartBundle,
    title: str,
    vertical_dates: list[str] | None = None,
) -> None:
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError:  # pragma: no cover - depends on local runtime
        st.error("当前环境缺少 plotly，图表无法渲染。")
        return

    df = bundle.df
    plot_dates = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    fig = go.Figure()
    for trace in bundle.main_panel.traces:
        if trace.kind == "candlestick":
            fig.add_trace(
                go.Candlestick(
                    x=plot_dates,
                    open=df[trace.open_column],
                    high=df[trace.high_column],
                    low=df[trace.low_column],
                    close=df[trace.close_column],
                    name=trace.name,
                    increasing_line_color=_GREEN,
                    decreasing_line_color=_RED,
                )
            )
        elif trace.kind == "line":
            fig.add_trace(
                go.Scatter(
                    x=plot_dates,
                    y=df[trace.y_column],
                    name=trace.name,
                    line=dict(
                        color=trace.color,
                        width=trace.width or 1.0,
                        dash=trace.dash or "solid",
                    ),
                )
            )

    for vertical_date in vertical_dates or []:
        try:
            fig.add_vline(
                x=pd.to_datetime(vertical_date, format="%Y%m%d"),
                line=dict(color=_YELLOW, dash="dot", width=1),
            )
        except Exception:
            continue

    fig.update_layout(
        title=dict(text=title, font=dict(color=_SLATE, size=13)),
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_DARK_BG,
        font=dict(color=_SLATE, size=11),
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=50, r=30, t=40, b=30),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    for panel in bundle.subcharts:
        subfig = go.Figure()
        for trace in panel.traces:
            if trace.kind == "line":
                subfig.add_trace(
                    go.Scatter(
                        x=plot_dates,
                        y=df[trace.y_column],
                        name=trace.name,
                        line=dict(
                            color=trace.color,
                            width=trace.width or 1.0,
                            dash=trace.dash or "solid",
                        ),
                    )
                )
            elif trace.kind == "bar":
                subfig.add_trace(
                    go.Bar(
                        x=plot_dates,
                        y=df[trace.y_column],
                        name=trace.name,
                        marker_color=trace.color,
                        opacity=trace.opacity,
                    )
                )

        for hline in panel.hlines:
            subfig.add_hline(y=hline.y, line=dict(color=hline.color, dash=hline.dash, width=hline.width))

        subfig.update_layout(
            title=dict(text=panel.title, font=dict(color=_SLATE, size=12)),
            paper_bgcolor=_DARK_BG,
            plot_bgcolor=_DARK_BG,
            font=dict(color=_SLATE, size=11),
            height=240,
            margin=dict(l=50, r=30, t=20, b=30),
            xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        )
        st.plotly_chart(subfig, use_container_width=True)


def _render_position_chart(position: Position) -> None:
    indicator_ids = get_default_indicator_ids(position.strategy_ids)
    bundle = build_stock_chart(
        code=position.code,
        end_date=date.today().strftime("%Y%m%d"),
        days=120,
        active_indicator_ids=indicator_ids,
        provider=_data_provider(),
    )
    if bundle is None:
        st.warning(f"{position.code} 暂无可用行情数据。")
        return

    _render_chart_bundle(
        bundle,
        title=f"{position.code} | 成本 {position.cost_basis:.2f}",
        vertical_dates=[position.entry_date],
    )


def _tab_screener() -> None:
    st.subheader("选股")

    substrategies = list_substrategies()
    if not substrategies:
        st.warning("没有可用子策略，先检查插件目录或者上面的错误 banner。")
        return

    groups: dict[str, list] = {}
    for strategy in substrategies:
        group = strategy.tags[0] if strategy.tags else "untagged"
        groups.setdefault(group, []).append(strategy)

    left_col, right_col = st.columns([1.35, 1], gap="large")

    with left_col:
        controls = st.columns([2, 1, 1])
        with controls[0]:
            scan_date = st.date_input("扫描日期", date.today(), key="scan_date")
        with controls[1]:
            mode = st.radio("组合方式", ["AND", "OR"], horizontal=True, key="scan_mode")
        with controls[2]:
            include_growth = st.checkbox("含创业板/科创板", value=False, key="scan_growth")

        st.markdown("**子策略清单**")
        selected_ids: list[str] = []
        for group_name in sorted(groups):
            st.markdown(f"`{group_name}`")
            for strategy in groups[group_name]:
                label = f"{strategy.name} | {strategy.description}"
                if st.checkbox(label, key=f"sub_{strategy.id}"):
                    selected_ids.append(strategy.id)

        if st.button("Run Scan", key="run_scan"):
            if not selected_ids:
                st.warning("至少勾一个子策略，不然这按钮就跟摆设似的。")
            else:
                date_str = scan_date.strftime("%Y%m%d")
                with st.spinner("Scanning..."):
                    universe = _data_provider().get_universe(include_growth_boards=include_growth)
                    results = screen(
                        substrategy_ids=selected_ids,
                        mode=mode,
                        universe=universe,
                        date=date_str,
                        data_provider=_data_provider(),
                        cache=_scan_cache(),
                    )
                st.session_state["last_screen_results"] = results
                st.session_state["last_screen_date"] = date_str
                st.session_state["selected_screen_date"] = date_str
                st.session_state["selected_screen_code"] = _resolve_selected_screen_code(
                    results,
                    st.session_state.get("selected_screen_code"),
                )

    results = st.session_state.get("last_screen_results", [])
    last_screen_date = st.session_state.get("last_screen_date", scan_date.strftime("%Y%m%d"))

    with left_col:
        if not results:
            st.info("勾选子策略后点击 `Run Scan`，结果会展示在这里。")
        else:
            st.markdown(f"**命中结果：{len(results)} 只**")
            rows: list[dict] = []
            for result in results:
                row = {
                    "code": result.code,
                    "hit_count": result.hit_count,
                    "hit_ids": ", ".join(result.hit_ids),
                    "close": round(float(result.close), 3),
                }
                for key, value in result.indicators_snapshot.items():
                    if key == "close":
                        continue
                    if isinstance(value, (int, float)):
                        row[key] = round(float(value), 3)
                    else:
                        row[key] = value
                rows.append(row)

            df = pd.DataFrame(rows).sort_values(["hit_count", "code"], ascending=[False, True]).reset_index(drop=True)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                label="Export CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"screen_{last_screen_date}.csv",
                mime="text/csv",
            )

    with right_col:
        st.markdown("**K 线详情**")
        if not results:
            st.info("先跑出结果，再在这里看单只股票的图。")
            return

        result_map = {result.code: result for result in results}
        resolved_code = _resolve_selected_screen_code(results, st.session_state.get("selected_screen_code"))
        if resolved_code is None:
            st.info("当前没有可展示的标的。")
            return

        st.session_state["selected_screen_code"] = resolved_code
        st.session_state["selected_screen_date"] = last_screen_date

        selected_code = st.selectbox(
            "当前标的",
            options=list(result_map.keys()),
            format_func=lambda code: _format_screening_option(code, result_map),
            key="selected_screen_code",
        )
        selected_result = result_map[selected_code]

        valid_indicator_ids = [preset.id for preset in list_indicator_presets()]
        manual_indicator_ids = [
            indicator_id
            for indicator_id in st.session_state.get("manual_indicator_ids", [])
            if indicator_id in valid_indicator_ids
        ]
        st.session_state["manual_indicator_ids"] = manual_indicator_ids
        st.multiselect(
            "额外指标",
            options=valid_indicator_ids,
            format_func=_format_indicator_option,
            key="manual_indicator_ids",
        )

        active_indicator_ids = _resolve_screen_indicator_ids(
            selected_result.hit_ids,
            st.session_state.get("manual_indicator_ids", []),
        )
        active_indicator_names = [_format_indicator_option(indicator_id) for indicator_id in active_indicator_ids]
        chip_html = "".join(
            f'<span class="strategy-chip">{strategy_id}</span>' for strategy_id in selected_result.hit_ids
        )
        st.markdown(chip_html or '<span class="inline-note">(无命中策略)</span>', unsafe_allow_html=True)
        st.caption(f"扫描日：{last_screen_date} | 当前指标：{', '.join(active_indicator_names)}")

        bundle = build_stock_chart(
            code=selected_result.code,
            end_date=last_screen_date,
            days=120,
            active_indicator_ids=active_indicator_ids,
            provider=_data_provider(),
        )
        if bundle is None:
            st.warning(f"{selected_result.code} 暂无可用行情数据。")
            return

        _render_chart_bundle(
            bundle,
            title=f"{selected_result.code} | 扫描日 {last_screen_date}",
        )


def _tab_positions() -> None:
    st.subheader("持仓")

    if "positions_loaded" not in st.session_state:
        _reload_positions()

    if st.button("刷新行情", key="refresh_positions"):
        st.rerun()

    position_dicts = st.session_state.get("positions", [])
    positions = [_dict_to_position(item) for item in position_dicts]
    statuses = []
    if positions:
        statuses = monitor_positions(
            positions=positions,
            data_provider=_data_provider(),
            today=date.today().strftime("%Y%m%d"),
        )

    alert_count = sum(1 for status in statuses if status.status == "alert")
    ok_count = sum(1 for status in statuses if status.status == "ok")
    unmonitored_count = sum(1 for status in statuses if status.status == "unmonitored")
    avg_pnl_pct = sum(status.pnl_pct for status in statuses) / len(statuses) if statuses else 0.0

    st.markdown(
        f'<div class="dark-band"><div class="metric-grid">'
        f'<div class="metric-card"><div class="value">{len(position_dicts)}</div><div class="label">总持仓</div></div>'
        f'<div class="metric-card"><div class="value">{alert_count}</div><div class="label">告警</div></div>'
        f'<div class="metric-card"><div class="value">{ok_count}</div><div class="label">安全</div></div>'
        f'<div class="metric-card"><div class="value">{unmonitored_count}</div><div class="label">无监控</div></div>'
        f'<div class="metric-card"><div class="value">{avg_pnl_pct * 100:.2f}%</div><div class="label">平均浮动</div></div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    strategy_ids = [strategy.id for strategy in list_substrategies()]
    with st.expander("新增持仓", expanded=False):
        with st.form("add_position_form", clear_on_submit=True):
            code = st.text_input("股票代码", placeholder="例如 000001")
            form_cols = st.columns(2)
            with form_cols[0]:
                entry_dt = st.date_input("买入日", date.today(), key="add_entry_date")
            with form_cols[1]:
                cost_basis = st.number_input(
                    "成本价",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="add_cost_basis",
                )
            strategy_selection = st.multiselect("绑定子策略", strategy_ids, key="add_strategy_ids")
            qty = st.number_input(
                "数量（可选，0=不记录）",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="add_quantity",
            )
            notes = st.text_input("备注（可选）", key="add_notes")
            submitted = st.form_submit_button("添加")
            if submitted:
                if not code.strip():
                    st.error("股票代码不能为空。")
                else:
                    storage.add_position(
                        PORTFOLIO_PATH,
                        Position(
                            code=code.strip(),
                            entry_date=entry_dt.strftime("%Y%m%d"),
                            cost_basis=float(cost_basis),
                            strategy_ids=list(strategy_selection),
                            quantity=float(qty) if qty > 0 else None,
                            notes=notes.strip(),
                        ),
                    )
                    _reload_positions()
                    st.success(f"已添加 {code.strip()}")
                    st.rerun()

    if not positions:
        st.info("还没有持仓，先录一条再说。")
        return

    header = st.columns([1.2, 1.2, 1.1, 1.1, 1.1, 2.4, 1.1, 0.8, 0.8, 0.8])
    for column, label in zip(
        header,
        ["代码", "买入日", "成本", "现价", "浮动%", "绑定策略", "状态", "编", "删", "图"],
    ):
        column.markdown(f"**{label}**")

    editing_index = st.session_state.get("editing_index")

    for index, (position, status) in enumerate(zip(positions, statuses)):
        row_cols = st.columns([1.2, 1.2, 1.1, 1.1, 1.1, 2.4, 1.1, 0.8, 0.8, 0.8])
        row_cls = "row-card alert" if status.status == "alert" else "row-card"
        row_cols[0].markdown(
            f'<div class="{row_cls}"><strong>{position.code}</strong></div>',
            unsafe_allow_html=True,
        )
        row_cols[1].write(position.entry_date)
        row_cols[2].write(f"{position.cost_basis:.2f}")
        row_cols[3].write(f"{status.current_price:.2f}")
        row_cols[4].markdown(
            f'<span style="color:{_GREEN if status.pnl_pct >= 0 else _RED}">{status.pnl_pct * 100:+.2f}%</span>',
            unsafe_allow_html=True,
        )
        chip_html = "".join(
            f'<span class="strategy-chip">{strategy_id}</span>' for strategy_id in position.strategy_ids
        )
        row_cols[5].markdown(chip_html or '<span class="inline-note">(无)</span>', unsafe_allow_html=True)
        row_cols[6].markdown(
            f'<span style="color:{_status_color(status.status)}">{status.status}</span>',
            unsafe_allow_html=True,
        )

        if row_cols[7].button("编", key=f"edit_btn_{index}"):
            st.session_state["editing_index"] = None if editing_index == index else index
            st.rerun()

        if row_cols[8].button("删", key=f"delete_btn_{index}"):
            storage.delete_position(PORTFOLIO_PATH, index)
            if st.session_state.get("editing_index") == index:
                st.session_state["editing_index"] = None
            st.session_state.pop(f"chart_open_{index}", None)
            _reload_positions()
            st.rerun()

        if row_cols[9].button("图", key=f"chart_btn_{index}"):
            chart_key = f"chart_open_{index}"
            st.session_state[chart_key] = not st.session_state.get(chart_key, False)
            st.rerun()

        pnl_abs_text = ""
        if status.pnl_abs is not None:
            pnl_abs_text = f" | 绝对盈亏 {status.pnl_abs:+.2f}"
        notes_text = f" | 备注：{position.notes}" if position.notes else ""
        st.caption(
            f"{position.code} 当前状态：{status.status}{pnl_abs_text}{notes_text}"
        )

        if st.session_state.get("editing_index") == index:
            with st.form(f"edit_position_{index}"):
                edit_code = st.text_input("股票代码", value=position.code, key=f"edit_code_{index}")
                edit_cols = st.columns(2)
                with edit_cols[0]:
                    edit_entry_date = st.date_input(
                        "买入日",
                        value=pd.to_datetime(position.entry_date, format="%Y%m%d").date(),
                        key=f"edit_entry_{index}",
                    )
                with edit_cols[1]:
                    edit_cost_basis = st.number_input(
                        "成本价",
                        min_value=0.0,
                        value=float(position.cost_basis),
                        step=0.01,
                        format="%.2f",
                        key=f"edit_cost_{index}",
                    )
                edit_strategy_ids = st.multiselect(
                    "绑定子策略",
                    strategy_ids,
                    default=position.strategy_ids,
                    key=f"edit_strategies_{index}",
                )
                edit_quantity = st.number_input(
                    "数量（可选，0=不记录）",
                    min_value=0.0,
                    value=float(position.quantity or 0.0),
                    step=1.0,
                    key=f"edit_qty_{index}",
                )
                edit_notes = st.text_input("备注（可选）", value=position.notes, key=f"edit_notes_{index}")
                save_clicked = st.form_submit_button("保存修改")
                if save_clicked:
                    storage.update_position(
                        PORTFOLIO_PATH,
                        index,
                        Position(
                            code=edit_code.strip(),
                            entry_date=edit_entry_date.strftime("%Y%m%d"),
                            cost_basis=float(edit_cost_basis),
                            strategy_ids=list(edit_strategy_ids),
                            quantity=float(edit_quantity) if edit_quantity > 0 else None,
                            notes=edit_notes.strip(),
                        ),
                    )
                    st.session_state["editing_index"] = None
                    _reload_positions()
                    st.success(f"已更新 {edit_code.strip()}")
                    st.rerun()

        if st.session_state.get(f"chart_open_{index}"):
            _render_position_chart(position)
            if status.alerts:
                st.markdown("**告警详情**")
                for monitor_id, reason in status.alerts:
                    st.markdown(f"- `{monitor_id}`: {reason}")


def main() -> None:
    _ensure_streamlit()
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    refresh_substrategies()
    refresh_monitors()
    _inject_css()

    st.markdown(
        f'<div class="app-header">'
        f'<div class="logo-mark">T</div>'
        f"<h1>{APP_TITLE}</h1>"
        f'<span class="subtitle">A-Share Screener & Positions</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    _render_errors()

    tab_screener, tab_positions = st.tabs(["选股", "持仓"])
    with tab_screener:
        _tab_screener()
    with tab_positions:
        _tab_positions()


if __name__ == "__main__":
    main()
