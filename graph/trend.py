from __future__ import annotations
import logging

from storage.report_history import ReportHistoryRepository

logger = logging.getLogger(__name__)


async def inject_trend_signal(
    report: dict,
    repo: ReportHistoryRepository,
) -> dict:
    if report.get("error"):
        return report

    symbol       = report.get("symbol", "")
    current_bias = report.get("market_bias")

    if not symbol or not current_bias:
        return report

    key_signals = list(report.get("key_signals") or [])

    if any(s.startswith("Bias changed:") for s in key_signals):
        return report

    try:
        history = await repo.get_latest(symbol, limit=1)
    except Exception as exc:
        logger.warning("Failed to fetch history for trend signal (%s): %s", symbol, exc)
        return report

    if not history:
        return report

    previous_bias = history[0].get("market_bias")
    if previous_bias and previous_bias != current_bias:
        signal = f"Bias changed: {previous_bias} → {current_bias} since last report"
        report = {**report, "key_signals": key_signals + [signal]}

    return report
