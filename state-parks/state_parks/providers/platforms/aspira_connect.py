"""Aspira Connect ("GoingToCamp") adapter -- used by Maryland.

PLATFORM NOTES
==============
Vendor
    Aspira's modern SPA booking product, the same codebase behind
    ``*.goingtocamp.com`` (Washington, Wisconsin, Ontario, BC). Maryland Park
    Service launched on it in February 2026 at
    ``https://parkreservations.maryland.gov`` -- the ``/create-booking`` route
    in their public links is the signature of this platform.

    Note this is *not* the same product as ReserveAmerica, despite both being
    Aspira: ReserveAmerica is the legacy server-rendered system, Connect is a
    JSON-backed SPA. They share no endpoints.

Endpoints (JSON, all GET with query parameters)
    ``/api/resourceLocation``                      -- parks
    ``/api/maps``                                  -- mapId per resource location
    ``/api/resourcecategory``                      -- category ids (cabin vs site)
    ``/api/availability/map``                      -- the availability grid
    ``/api/resource/details?resourceId=<id>``      -- per-cabin detail
    ``/api/availability/resourcedailyavailability``-- per-day detail

    ``/api/availability/map`` query parameters::

        mapId, resourceLocationId, bookingCategoryId, startDate, endDate,
        isReserving, getDailyAvailability, partySize, numEquipment,
        equipmentCategoryId, subEquipmentCategoryId, filterData

    Response::

        {"resourceAvailabilities": {"<resourceId>": [{"availability": 0}, ...]},
         "mapLinkAvailabilities": {...}}

    The ``availability`` integer is the important and counter-intuitive bit:
    **0 means available**. Non-zero values are the various flavours of "not
    bookable" (already reserved, closed, partial). The list is ordered by night
    across the requested range.

VERIFICATION STATUS
    Endpoint paths, parameter names, the ``resourceAvailabilities`` shape and
    the ``availability == 0`` convention come from the open-source ``camply``
    project's GoingToCamp provider (MIT), which works against live deployments.
    Maryland's own ``resourceLocationId`` / ``mapId`` / ``bookingCategoryId``
    values could not be captured -- ``parkreservations.maryland.gov`` is blocked
    by this environment's egress policy -- so the catalog ships empty and is
    populated by ``python -m state_parks.cli discover MD``, which walks
    ``/api/resourceLocation`` and ``/api/maps`` and writes the catalog file.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, ClassVar

from state_parks.models import Cabin, Park
from state_parks.providers.base import HttpStateProvider, ProviderError
from state_parks.providers.platforms.reserve_america import looks_like_cabin

logger = logging.getLogger(__name__)

#: In this API, 0 is the *available* code. Everything else means blocked.
AVAILABLE_CODE = 0


def parse_map_availability(
    payload: dict[str, Any], arrival: date, departure: date
) -> list[dict[str, Any]]:
    """Parse ``/api/availability/map`` into per-resource stay results.

    ``resourceAvailabilities`` maps a resource id to a list of per-night
    entries, ordered from ``arrival``. A stay is bookable when every night in
    the range carries ``availability == 0``.
    """
    availabilities = payload.get("resourceAvailabilities") or {}
    nights = (departure - arrival).days
    results: list[dict[str, Any]] = []

    for resource_id, entries in availabilities.items():
        if not isinstance(entries, list) or not entries:
            continue
        # Some deployments nest one level deeper: {mapId: {resourceId: [...]}}.
        if isinstance(entries[0], dict) and "availability" not in entries[0]:
            continue

        window = entries[:nights]
        if len(window) < nights:
            # Upstream returned a shorter range than asked for; do not guess.
            continue

        available = all(
            entry.get("availability") == AVAILABLE_CODE for entry in window
        )
        rates = [
            float(entry["price"])
            for entry in window
            if entry.get("price") not in (None, "", 0)
        ]
        results.append(
            {
                "resource_id": str(resource_id),
                "available": available,
                "rate": round(sum(rates) / len(rates), 2) if rates else None,
            }
        )
    return results


def flatten_nested_availabilities(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize ``{mapId: {resourceId: [...]}}`` to ``{resourceId: [...]}``.

    Deployments disagree on whether the map id is included as an outer key, so
    callers run responses through this first.
    """
    availabilities = payload.get("resourceAvailabilities") or {}
    if not availabilities:
        return payload
    first = next(iter(availabilities.values()))
    if isinstance(first, dict):
        flattened: dict[str, Any] = {}
        for inner in availabilities.values():
            flattened.update(inner)
        return {**payload, "resourceAvailabilities": flattened}
    return payload


class AspiraConnectProvider(HttpStateProvider):
    """Shared behaviour for Aspira Connect / GoingToCamp deployments."""

    platform: ClassVar[str] = "aspira_connect"
    wire_format_verified: ClassVar[bool] = False

    #: Booking category for overnight stays; cabins live under this in every
    #: deployment inspected. Confirm per agency with /api/resourcecategory.
    booking_category_id: ClassVar[int] = 0
    #: Resource-location catalog: {"resourceLocationId", "mapId", "name", ...}
    location_catalog: ClassVar[list[dict[str, Any]]] = []

    async def fetch_resource_locations(self) -> list[dict[str, Any]]:
        payload = await self.get_json("/api/resourceLocation")
        return payload if isinstance(payload, list) else []

    async def fetch_maps(self) -> list[dict[str, Any]]:
        payload = await self.get_json("/api/maps")
        return payload if isinstance(payload, list) else []

    async def fetch_map_availability(
        self,
        *,
        map_id: int | str,
        resource_location_id: int | str,
        arrival: date,
        departure: date,
        party_size: int,
    ) -> dict[str, Any]:
        params = {
            "mapId": map_id,
            "resourceLocationId": resource_location_id,
            "bookingCategoryId": self.booking_category_id,
            "startDate": arrival.isoformat(),
            "endDate": departure.isoformat(),
            "isReserving": "true",
            "getDailyAvailability": "true",
            "partySize": party_size,
            "numEquipment": 1,
            "equipmentCategoryId": -32768,  # sentinel used for "any/none"
            "filterData": "[]",
        }
        payload = await self.get_json("/api/availability/map", params=params)
        return flatten_nested_availabilities(payload)

    async def fetch_resource_details(self, resource_id: str) -> dict[str, Any]:
        return await self.get_json(
            "/api/resource/details", params={"resourceId": resource_id}
        )

    async def list_parks(self) -> list[Park]:
        return [
            Park(
                state=self.state,
                park_id=str(entry["resourceLocationId"]),
                name=entry["name"],
                provider=self.name,
                latitude=entry.get("latitude"),
                longitude=entry.get("longitude"),
                url=f"{self.base_url}/create-booking",
                metadata={"mapId": entry.get("mapId")},
            )
            for entry in self.location_catalog
        ]

    async def search_cabins(
        self,
        start_date: date,
        end_date: date,
        guests: int,
        pets: bool = False,
    ) -> list[Cabin]:
        results: list[Cabin] = []
        for location in self.location_catalog:
            try:
                payload = await self.fetch_map_availability(
                    map_id=location["mapId"],
                    resource_location_id=location["resourceLocationId"],
                    arrival=start_date,
                    departure=end_date,
                    party_size=guests,
                )
                resources = parse_map_availability(payload, start_date, end_date)
            except (ProviderError, ValueError, KeyError) as exc:
                logger.warning(
                    "%s: location %s failed: %s",
                    self.name, location.get("name"), exc,
                )
                continue

            # Resource names are not in the availability response; the catalog
            # carries a resourceId -> name map filled in by `cli discover`.
            names: dict[str, Any] = location.get("resources", {})
            for resource in resources:
                meta = names.get(resource["resource_id"], {})
                name = meta.get("name") or f"Site {resource['resource_id']}"
                if names and not looks_like_cabin(name, meta.get("category")):
                    continue
                results.append(
                    Cabin(
                        state=self.state,
                        park=location["name"],
                        park_id=str(location["resourceLocationId"]),
                        cabin_name=name,
                        cabin_id=resource["resource_id"],
                        arrival=start_date,
                        departure=end_date,
                        available=resource["available"],
                        nightly_rate=resource.get("rate"),
                        sleeps=meta.get("sleeps"),
                        bedrooms=meta.get("bedrooms"),
                        pet_friendly=meta.get("pet_friendly"),
                        waterfront=meta.get("waterfront"),
                        latitude=meta.get("latitude") or location.get("latitude"),
                        longitude=meta.get("longitude") or location.get("longitude"),
                        reservation_url=(
                            f"{self.base_url}/create-booking/results"
                            f"?resourceLocationId={location['resourceLocationId']}"
                            f"&mapId={location['mapId']}"
                            f"&startDate={start_date.isoformat()}"
                            f"&endDate={end_date.isoformat()}"
                        ),
                        provider=self.name,
                    )
                )
        return results

    async def discover(self) -> list[dict[str, Any]]:
        """Build the location catalog from the live API.

        Maryland's ids are not published anywhere, so this walks
        ``/api/resourceLocation`` and ``/api/maps`` and returns entries ready to
        be written to ``providers/catalog/<state>.json``.
        """
        locations = await self.fetch_resource_locations()
        maps = await self.fetch_maps()
        map_by_location = {
            str(m.get("resourceLocationId")): m.get("mapId") for m in maps
        }

        catalog: list[dict[str, Any]] = []
        for location in locations:
            location_id = str(location.get("resourceLocationId"))
            localized = location.get("localizedValues") or [{}]
            catalog.append(
                {
                    "resourceLocationId": location_id,
                    "mapId": map_by_location.get(location_id)
                    or location.get("mapId"),
                    "name": localized[0].get("fullName")
                    or localized[0].get("name")
                    or location_id,
                    "resources": {},
                }
            )
        return catalog

    async def verify(self) -> dict[str, Any]:
        report = await super().verify()
        checks: list[dict[str, Any]] = []
        try:
            locations = await self.fetch_resource_locations()
        except (ProviderError, ValueError) as exc:
            checks.append(
                {"check": "/api/resourceLocation", "ok": False, "detail": str(exc)}
            )
            report["checks"] = checks
            return report

        checks.append(
            {
                "check": "/api/resourceLocation",
                "ok": bool(locations),
                "detail": f"{len(locations)} locations",
            }
        )

        catalog = self.location_catalog or await self.discover()
        if catalog:
            entry = catalog[0]
            arrival = date.today() + timedelta(days=30)
            try:
                payload = await self.fetch_map_availability(
                    map_id=entry["mapId"],
                    resource_location_id=entry["resourceLocationId"],
                    arrival=arrival,
                    departure=arrival + timedelta(days=2),
                    party_size=2,
                )
            except (ProviderError, ValueError) as exc:
                checks.append(
                    {"check": "/api/availability/map", "ok": False, "detail": str(exc)}
                )
            else:
                parsed = parse_map_availability(
                    payload, arrival, arrival + timedelta(days=2)
                )
                checks.append(
                    {
                        "check": "/api/availability/map",
                        "ok": bool(parsed),
                        "detail": f"{len(parsed)} resources parsed",
                    }
                )
        report["checks"] = checks
        return report
