"""REST endpoints.

All filters are query parameters, all responses are the normalized models, and
no endpoint reveals which reservation platform a row came from (beyond the
``/providers`` diagnostics endpoint, which exists precisely to surface that).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from state_parks.api.deps import get_refresh_service, get_search_service
from state_parks.models import Cabin, Park, ProviderStatus, SearchQuery
from state_parks.providers import all_providers
from state_parks.services import RefreshService, SearchService

router = APIRouter()

StateFilter = Annotated[
    list[str] | None,
    Query(description="USPS codes, repeatable: ?state=NC&state=VA"),
]


@router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/providers", response_model=list[ProviderStatus], tags=["meta"])
async def providers(
    service: Annotated[SearchService, Depends(get_search_service)],
) -> list[ProviderStatus]:
    """Provider health, including whether each wire format is verified.

    Worth checking before trusting a state's results: providers with
    ``wire_format_verified = false`` have parsers that have not been confirmed
    against a live response.
    """
    return await service.providers()


@router.get("/parks", response_model=list[Park], tags=["inventory"])
async def parks(
    service: Annotated[SearchService, Depends(get_search_service)],
    state: str | None = Query(None, description="USPS code, e.g. NC"),
) -> list[Park]:
    return await service.parks(state)


@router.get("/cabins", response_model=list[Cabin], tags=["inventory"])
async def cabins(
    service: Annotated[SearchService, Depends(get_search_service)],
    state: str | None = None,
    park: str | None = Query(None, description="Substring match on park name"),
    limit: int = Query(200, le=1000),
    offset: int = 0,
) -> list[Cabin]:
    """Known cabin inventory, independent of dates."""
    return await service.cabins(state=state, park=park, limit=limit, offset=offset)


@router.get("/availability", response_model=list[Cabin], tags=["availability"])
async def availability(
    service: Annotated[SearchService, Depends(get_search_service)],
    arrival: date,
    departure: date,
    state: StateFilter = None,
    park: str | None = None,
    guests: int = 2,
    pets: bool = False,
    sleeps: int | None = None,
    waterfront: bool | None = None,
    available_only: bool = True,
    limit: int = Query(200, le=1000),
    offset: int = 0,
) -> list[Cabin]:
    """Cabins bookable for a specific arrival/departure window."""
    query = _build_query(
        arrival=arrival,
        departure=departure,
        state=state,
        park=park,
        guests=guests,
        pets=pets,
        sleeps=sleeps,
        waterfront=waterfront,
        available_only=available_only,
    )
    return await service.search(query, limit=limit, offset=offset)


@router.get(
    "/availability/weekends", response_model=list[Cabin], tags=["availability"]
)
async def weekend_availability(
    service: Annotated[SearchService, Depends(get_search_service)],
    start: date | None = None,
    weeks: int = Query(8, ge=1, le=52, description="How many weekends ahead"),
    state: StateFilter = None,
    guests: int = 2,
    pets: bool = False,
    sleeps: int | None = None,
    waterfront: bool | None = None,
    limit: int = Query(200, le=1000),
) -> list[Cabin]:
    """Friday->Sunday stays across the next N weeks."""
    return await service.weekends(
        start=start,
        weeks=weeks,
        states=state,
        sleeps=sleeps or guests,
        pets=pets,
        waterfront=waterfront,
        limit=limit,
    )


@router.get("/search", response_model=list[Cabin], tags=["availability"])
async def search(
    service: Annotated[SearchService, Depends(get_search_service)],
    arrival: date,
    departure: date,
    state: StateFilter = None,
    park: str | None = None,
    guests: int = 2,
    pets: bool = False,
    sleeps: int | None = None,
    waterfront: bool | None = None,
    available_only: bool = True,
    source: Literal["cache", "live"] = Query(
        "cache",
        description=(
            "'cache' reads local SQLite (fast). 'live' queries the parks' "
            "reservation systems directly and updates the cache -- slower, and "
            "please use sparingly."
        ),
    ),
    limit: int = Query(200, le=1000),
) -> list[Cabin]:
    """Primary search endpoint, cache-backed or live."""
    query = _build_query(
        arrival=arrival,
        departure=departure,
        state=state,
        park=park,
        guests=guests,
        pets=pets,
        sleeps=sleeps,
        waterfront=waterfront,
        available_only=available_only,
    )
    if source == "live":
        return (await service.search_live(query))[:limit]
    return await service.search(query, limit=limit)


@router.post("/refresh", tags=["meta"])
async def refresh(
    service: Annotated[RefreshService, Depends(get_refresh_service)],
    state: StateFilter = None,
    months: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Trigger a refresh now (the scheduler does this on its own interval)."""
    providers = all_providers(state)
    results = await service.refresh_all(providers, months=months, force=force)
    return {
        "results": [
            {
                "provider": r.provider,
                "windows_attempted": r.windows_attempted,
                "windows_ok": r.windows_ok,
                "cabins_found": r.cabins_found,
                "rows_written": r.rows_written,
                "skipped": r.skipped,
                "errors": r.errors[:5],
            }
            for r in results
        ]
    }


def _build_query(
    *,
    arrival: date,
    departure: date,
    state: list[str] | None,
    park: str | None,
    guests: int,
    pets: bool,
    sleeps: int | None,
    waterfront: bool | None,
    available_only: bool,
) -> SearchQuery:
    if departure <= arrival:
        raise HTTPException(422, "departure must be after arrival")
    if arrival < date.today() - timedelta(days=1):
        raise HTTPException(422, "arrival is in the past")
    return SearchQuery(
        arrival=arrival,
        departure=departure,
        guests=guests,
        pets=pets,
        states=[s.upper() for s in state] if state else None,
        park=park,
        sleeps=sleeps,
        waterfront=waterfront,
        available_only=available_only,
    )
