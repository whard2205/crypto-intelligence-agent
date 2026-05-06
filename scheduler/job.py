from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from config.settings import Settings
from graph.trend import inject_trend_signal
from publishers.base import ReportPublisher
from storage.report_history import ReportHistoryRepository

logger = logging.getLogger(__name__)


async def run_scheduled_reports(
    settings: Settings,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> None:
    symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]
    for symbol in symbols:
        await _run_single(symbol, graph, publisher, repo)


async def _run_single(
    symbol: str,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> None:
    report = None
    exc_detail = None

    for attempt in (1, 2):
        try:
            report = await _invoke_pipeline(graph, symbol)
            break
        except Exception as exc:
            exc_detail = exc
            logger.warning("Pipeline attempt %d failed for %s: %s", attempt, symbol, exc)
            if attempt == 2:
                report = _make_error_report(symbol)
                logger.error("Pipeline failed after retry for %s: %s", symbol, exc_detail)

    if report is not None and not report.get("error"):
        report = await inject_trend_signal(report, repo)

    if report is not None and not report.get("error"):
        try:
            await repo.save(report)
        except Exception as exc:
            logger.error("Failed to save report for %s to history: %s", symbol, exc)

    try:
        await publisher.publish(report)
    except Exception:
        logger.error("Telegram send failed for %s", symbol)


async def _invoke_pipeline(graph, symbol: str) -> dict:
    state = {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.now(timezone.utc).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "funding_rate_data":         None,
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }
    result = await graph.ainvoke(state)
    return result["report"]


def _make_error_report(symbol: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id":       str(uuid.uuid4()),
        "symbol":       symbol,
        "requested_at": now,
        "generated_at": now,
        "error":        "Scheduled report failed after retry",
        "data_gaps":    [],
    }
