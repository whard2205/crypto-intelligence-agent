from __future__ import annotations
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from config.settings import Settings, get_settings
from storage.report_history import ReportHistoryRepository


async def require_api_key(
    x_api_key: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.API_AUTH_ENABLED:
        return
    if not settings.API_KEY or x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def get_repo(request: Request) -> ReportHistoryRepository:
    return request.app.state.repo
