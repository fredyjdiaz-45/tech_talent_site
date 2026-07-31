"""Search service: the single normalized entry point used by the API.

Reads come from SQLite by default (fast, and kind to the upstream sites). A
``live=True`` search bypasses the cache, queries providers directly and writes
what it learns back -- useful when you want to be certain about a specific
weekend.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from state_parks.database import Repository, run_db
from state_parks.models import Cabin, Park, ProviderStatus, SearchQuery
from state_parks.providers import NotVerifiedError, ProviderError, all_providers

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def search(
        self, query: SearchQuery, *, limit: int = 200, offset: int = 0
    ) -> list[Cabin]:
        return await run_db(
            self.repo.search,
            arrival=query.arrival,
            departure=query.departure,
            states=query.states,
            park=query.park,
            sleeps=query.sleeps or query.guests,
            pets=query.pets,
            waterfront=query.waterfront,
            available_only=query.available_only,
            limit=limit,
            offset=offset,
        )

    async def search_live(
        self, query: SearchQuery, *, persist: bool = True
    ) -> list[Cabin]:
        """Query providers directly, in parallel, tolerating partial failure."""
        providers = all_providers(query.states)
        tasks = [
            p.search_cabins(query.arrival, query.departure, query.guests, query.pets)
            for p in providers
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        cabins: list[Cabin] = []
        for provider, outcome in zip(providers, outcomes, strict=True):
            if isinstance(outcome, NotVerifiedError):
                logger.info("%s skipped: %s", provider.name, outcome)
            elif isinstance(outcome, (ProviderError, Exception)) and isinstance(
                outcome, BaseException
            ):
                logger.warning("%s live search failed: %s", provider.name, outcome)
            else:
                cabins.extend(outcome)

        await asyncio.gather(*(p.aclose() for p in providers), return_exceptions=True)

        if persist and cabins:
            await run_db(self.repo.store_cabins, cabins)

        return [c for c in cabins if c.available or not query.available_only]

    async def weekends(
        self,
        *,
        start: date | None = None,
        weeks: int = 8,
        states: list[str] | None = None,
        sleeps: int | None = None,
        pets: bool = False,
        waterfront: bool | None = None,
        limit: int = 200,
    ) -> list[Cabin]:
        start = start or date.today()
        return await run_db(
            self.repo.weekend_search,
            start=start,
            end=start + timedelta(weeks=weeks),
            states=states,
            sleeps=sleeps,
            pets=pets,
            waterfront=waterfront,
            limit=limit,
        )

    async def parks(self, state: str | None = None) -> list[Park]:
        return await run_db(self.repo.list_parks, state)

    async def cabins(
        self,
        state: str | None = None,
        park: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[Cabin]:
        return await run_db(self.repo.list_cabins, state, park, limit, offset)

    async def providers(self) -> list[ProviderStatus]:
        return await run_db(self.repo.list_providers)
