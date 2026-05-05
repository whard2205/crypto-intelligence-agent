from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Annotated, Union

from fastapi import APIRouter, Depends, Query
from config.settings import Settings, get_settings
from data_sources.factory import build_adapters
from graph.pipeline import build_graph
from api.deps import require_api_key, get_repo
from api.schemas import IntelligenceReportResponse, ErrorReportResponse
from storage.report_history import ReportHistoryRepository

router = APIRouter()

_SYMBOL_PATTERN = r"^[A-Z][A-Z0-9]{2,19}$"


def _make_initial_state(symbol: str) -> dict:
    return {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.now(timezone.utc).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }


@router.get(
    "/report",
    response_model=Union[IntelligenceReportResponse, ErrorReportResponse],
    response_model_exclude_none=False,
)
async def get_report(
    symbol: Annotated[
        str,
        Query(min_length=3, max_length=20, pattern=_SYMBOL_PATTERN),
    ] = "BTCUSDT",
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
    repo: ReportHistoryRepository = Depends(get_repo),
) -> Union[IntelligenceReportResponse, ErrorReportResponse]:
    adapters = build_adapters(settings)
    graph    = build_graph(settings, **adapters)
    result   = await graph.ainvoke(_make_initial_state(symbol))
    report   = result["report"]

    if not report.get("error"):
        await repo.save(report)
        return IntelligenceReportResponse(**report)

    return ErrorReportResponse(**report)
