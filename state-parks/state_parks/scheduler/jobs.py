"""Scheduled refresh.

APScheduler's asyncio scheduler runs the refresh on an interval. It is
deliberately a separate process from the API (``cli schedule``) so a long
refresh can never make the API unresponsive, and so the API can be restarted
without interrupting a crawl.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from state_parks.config import settings
from state_parks.database import Database, Repository
from state_parks.providers import all_providers
from state_parks.services import RefreshService

logger = logging.getLogger(__name__)


async def refresh_job(force: bool = False) -> None:
    """One pass over every enabled provider."""
    db = Database()
    try:
        service = RefreshService(Repository(db.conn))
        providers = all_providers()
        results = await service.refresh_all(providers, force=force)
        for result in results:
            if result.skipped:
                logger.info("%s: skipped (%s)", result.provider, result.skipped)
            else:
                logger.info(
                    "%s: %d/%d windows, %d cabins, %d rows%s",
                    result.provider,
                    result.windows_ok,
                    result.windows_attempted,
                    result.cabins_found,
                    result.rows_written,
                    f", {len(result.errors)} errors" if result.errors else "",
                )
        await asyncio.gather(
            *(p.aclose() for p in providers), return_exceptions=True
        )
    finally:
        db.close()


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_job,
        trigger=IntervalTrigger(minutes=settings.refresh_interval_minutes),
        id="refresh",
        name="Refresh cabin availability",
        # If a run overruns the interval, skip rather than pile up -- doubling
        # up would double the load on the parks' servers.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


async def run_forever() -> None:
    """Start the scheduler and run an immediate first pass."""
    scheduler = build_scheduler()
    scheduler.start()
    logger.info(
        "scheduler started: every %d minutes, %d month horizon",
        settings.refresh_interval_minutes,
        settings.refresh_months,
    )
    await refresh_job()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        scheduler.shutdown()
