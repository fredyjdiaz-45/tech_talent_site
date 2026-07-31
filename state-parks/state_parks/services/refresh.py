"""Background refresh.

Strategy
--------
The refresh walks the next ``refresh_months`` in fixed windows
(``refresh_chunk_days``) per provider, but only fetches windows that are
*stale* -- never fetched, or fetched longer ago than ``stale_after_hours``.
That is what makes repeated runs cheap and lets a run be interrupted and
resumed without losing ground.

Near-term dates are refreshed more aggressively than far-out ones: a cabin four
months out rarely changes hour to hour, but next weekend's cancellations are the
whole point of the project. ``window_priority`` implements that ordering.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from state_parks.config import settings
from state_parks.database import Repository, run_db
from state_parks.models import Cabin
from state_parks.providers import NotVerifiedError, ProviderError, StateProvider

logger = logging.getLogger(__name__)


@dataclass
class RefreshResult:
    provider: str
    windows_attempted: int = 0
    windows_ok: int = 0
    cabins_found: int = 0
    rows_written: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and self.skipped is None


def build_windows(
    start: date, months: int, chunk_days: int
) -> list[tuple[date, date]]:
    """Split the horizon into consecutive fetch windows."""
    end = start + timedelta(days=int(months * 30.44))
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=chunk_days), end)
        windows.append((cursor, stop))
        cursor = stop
    return windows


def window_priority(window: tuple[date, date], today: date) -> int:
    """Sort key: soonest windows first.

    Cancellations matter most for imminent dates, so if a run is cut short the
    valuable half is already done.
    """
    return (window[0] - today).days


class RefreshService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def refresh_provider(
        self,
        provider: StateProvider,
        *,
        months: int | None = None,
        force: bool = False,
        guests: int = 2,
    ) -> RefreshResult:
        """Refresh one provider's stale windows."""
        result = RefreshResult(provider=provider.name)
        months = months or settings.refresh_months
        today = date.today()

        # Register before anything else: the refresh log and parks both carry a
        # foreign key to providers, and refresh_provider is callable directly
        # (CLI, tests) without going through refresh_all.
        await run_db(self.repo.upsert_provider, provider.status())

        windows = build_windows(today, months, settings.refresh_chunk_days)
        windows.sort(key=lambda w: window_priority(w, today))

        if not force:
            windows = await run_db(
                self.repo.stale_windows,
                provider.name,
                windows,
                settings.stale_after_hours,
            )
        if not windows:
            logger.info("%s: nothing stale, skipping", provider.name)
            result.skipped = "fresh"
            return result

        for start, stop in windows:
            result.windows_attempted += 1
            try:
                cabins = await provider.search_cabins(start, stop, guests)
            except NotVerifiedError as exc:
                # Expected for providers whose wire format is not confirmed.
                # Record once and stop -- retrying every window is pointless.
                logger.info("%s: %s", provider.name, exc)
                result.skipped = "wire format not verified"
                result.errors.append(str(exc))
                await run_db(
                    self.repo.log_refresh, provider.name, start, stop,
                    ok=False, error=str(exc),
                )
                break
            except (ProviderError, ValueError) as exc:
                logger.warning("%s: window %s failed: %s", provider.name, start, exc)
                result.errors.append(f"{start}: {exc}")
                await run_db(
                    self.repo.log_refresh, provider.name, start, stop,
                    ok=False, error=str(exc),
                )
                continue

            written = await run_db(self.repo.store_cabins, cabins)
            result.windows_ok += 1
            result.cabins_found += len(cabins)
            result.rows_written += written
            await run_db(self.repo.log_refresh, provider.name, start, stop, ok=True)

        await run_db(
            self.repo.mark_refresh,
            provider.name,
            error="; ".join(result.errors[:3]) or None,
        )
        return result

    async def refresh_all(
        self,
        providers: list[StateProvider],
        *,
        months: int | None = None,
        force: bool = False,
    ) -> list[RefreshResult]:
        """Refresh every provider concurrently.

        Concurrency is across providers only -- each provider still serializes
        its own requests, so no single agency's site sees parallel load.
        """
        for provider in providers:
            await run_db(self.repo.upsert_provider, provider.status())

        results = await asyncio.gather(
            *(
                self.refresh_provider(p, months=months, force=force)
                for p in providers
            ),
            return_exceptions=True,
        )

        collected: list[RefreshResult] = []
        for provider, outcome in zip(providers, results, strict=True):
            if isinstance(outcome, BaseException):
                logger.exception(
                    "%s: refresh crashed: %s", provider.name, outcome
                )
                collected.append(
                    RefreshResult(provider=provider.name, errors=[str(outcome)])
                )
            else:
                collected.append(outcome)
        return collected


async def store_live_results(repo: Repository, cabins: list[Cabin]) -> int:
    """Persist ad-hoc live search results so the cache warms as you browse."""
    return await run_db(repo.store_cabins, cabins)
