from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config.settings import Settings
from publishers.base import ReportPublisher
from storage.report_history import ReportHistoryRepository
from scheduler.job import run_scheduled_reports


def build_scheduler(
    settings: Settings,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        func=run_scheduled_reports,
        trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        args=[settings, graph, publisher, repo],
        id="crypto_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
