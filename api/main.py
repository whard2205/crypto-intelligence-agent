from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.settings import get_settings
from storage.report_history import ReportHistoryRepository
from api.routes import health, report, history

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    app.state.repo = repo
    logger.info("Report history DB initialized at %s", settings.DB_PATH)
    yield


app = FastAPI(
    title="Crypto Intelligence Agent",
    version="0.1.0",
    description="Mock-first LangGraph pipeline for crypto market intelligence.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(report.router)
app.include_router(history.router)
