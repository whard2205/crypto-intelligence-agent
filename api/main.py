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

    scheduler = None
    if settings.SCHEDULER_ENABLED:
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            logger.warning(
                "SCHEDULER_ENABLED=true but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing "
                "— scheduler will not start"
            )
        else:
            if settings.SCHEDULER_INTERVAL_HOURS < 1:
                raise ValueError(
                    f"SCHEDULER_INTERVAL_HOURS must be >= 1, "
                    f"got {settings.SCHEDULER_INTERVAL_HOURS}"
                )
            import telegram
            from publishers.telegram_publisher import TelegramPublisher
            from data_sources.factory import build_adapters
            from graph.pipeline import build_graph
            from scheduler.runner import build_scheduler

            bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
            publisher = TelegramPublisher(
                bot, settings.TELEGRAM_CHAT_ID, settings.DISPLAY_TIMEZONE
            )
            adapters = build_adapters(settings)
            graph = build_graph(settings, **adapters)
            scheduler = build_scheduler(settings, graph, publisher, repo)
            scheduler.start()
            logger.info(
                "Scheduler started — interval=%dh symbols=%s",
                settings.SCHEDULER_INTERVAL_HOURS,
                settings.WATCH_SYMBOLS,
            )

    bot_application = None
    if settings.TELEGRAM_BOT_ENABLED:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning(
                "TELEGRAM_BOT_ENABLED=true but TELEGRAM_BOT_TOKEN is missing "
                "— bot will not start"
            )
        else:
            from telegram_bot.main import build_bot, _post_init
            # MVP: no rollback on partial init failure; exception propagates and server aborts
            bot_application = build_bot(settings)
            await bot_application.initialize()
            await _post_init(bot_application)   # sets up repo + registers /commands in Telegram UI
            await bot_application.start()
            await bot_application.updater.start_polling()
            logger.info("Telegram bot started — polling for commands")

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    if bot_application is not None:
        if bot_application.updater:
            await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()
        logger.info("Telegram bot stopped")


app = FastAPI(
    title="Crypto Intelligence Agent",
    version="0.1.0",
    description="Mock-first LangGraph pipeline for crypto market intelligence.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(report.router)
app.include_router(history.router)
