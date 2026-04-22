"""Pure position-monitoring helpers."""

from __future__ import annotations

from .models import Position, PositionStatus
from .monitors import get_monitor
from .substrategies import get_substrategy


def monitor_positions(
    positions: list[Position],
    data_provider,
    today: str,
) -> list[PositionStatus]:
    """Compute live monitoring status for user-held positions."""
    statuses: list[PositionStatus] = []

    for position in positions:
        df = data_provider.get_latest(code=position.code, days=250, end_date=today)
        if df is None or df.empty:
            statuses.append(
                PositionStatus(
                    code=position.code,
                    current_price=0.0,
                    pnl_pct=0.0,
                    pnl_abs=None,
                    alerts=[],
                    status="unmonitored",
                )
            )
            continue

        current_price = float(df["close"].iloc[-1])
        pnl_pct = 0.0
        if position.cost_basis:
            pnl_pct = (current_price - position.cost_basis) / position.cost_basis
        pnl_abs = None
        if position.quantity is not None:
            pnl_abs = (current_price - position.cost_basis) * position.quantity

        alerts: list[tuple[str, str]] = []
        has_monitor = False

        for strategy_id in position.strategy_ids:
            strategy = get_substrategy(strategy_id)
            if strategy is None:
                continue
            monitor_id = getattr(strategy, "exit_monitor_id", None)
            if not monitor_id:
                continue

            monitor = get_monitor(monitor_id)
            if monitor is None:
                continue

            has_monitor = True
            triggered, reason = monitor.check(df, position)
            if triggered:
                alerts.append((monitor.id, reason))

        if alerts:
            status = "alert"
        elif not has_monitor:
            status = "unmonitored"
        else:
            status = "ok"

        statuses.append(
            PositionStatus(
                code=position.code,
                current_price=current_price,
                pnl_pct=pnl_pct,
                pnl_abs=pnl_abs,
                alerts=alerts,
                status=status,
            )
        )

    return statuses
