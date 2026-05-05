from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from api.deps import require_api_key, get_repo
from storage.report_history import ReportHistoryRepository

router = APIRouter()

_SYMBOL_PATTERN = r"^[A-Z][A-Z0-9]{2,19}$"


@router.get("/history")
async def get_history(
    symbol: Annotated[
        str,
        Query(min_length=3, max_length=20, pattern=_SYMBOL_PATTERN),
    ] = "BTCUSDT",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    _: None = Depends(require_api_key),
    repo: ReportHistoryRepository = Depends(get_repo),
) -> list[dict]:
    return await repo.get_latest(symbol, limit)
