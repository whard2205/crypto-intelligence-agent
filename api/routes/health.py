from __future__ import annotations
from fastapi import APIRouter, Depends
from config.settings import Settings, get_settings
from api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        mock_mode=settings.use_mock(),
        llm_enabled=settings.LLM_ENABLED,
    )
