"""UseDirect / US eDirect adapter -- used by Virginia.

PLATFORM NOTES
==============
Vendor
    US eDirect (usedirect.com). Virginia DCR moved off ReserveAmerica to this
    vendor; the booking front end is ``https://reservevaparks.com/Web/``, an
    ASP.NET shell whose data comes from a JSON service known as "RDR".

    The same platform backs California (``calirdr.usedirect.com``), Texas,
    Arizona and Florida, so this adapter is reusable if the project ever grows
    past the mid-Atlantic.

Endpoints (JSON -- no HTML parsing needed)
    ``GET  {rdr}/rdr/rdr/search/places``      -- parks ("places")
    ``GET  {rdr}/rdr/rdr/search/facilities``  -- campgrounds/loops within a place
    ``GET  {rdr}/rdr/rdr/search/filters``     -- unit categories, type groups
    ``POST {rdr}/rdr/rdr/search/availability``-- the useful one

    Availability request body (keys are PascalCase and the server rejects
    unknown nulls, so empty values are stripped before sending)::

        {"FacilityId": "123", "StartDate": "2026-09-04", "EndDate": "2026-09-06",
         "UnitCategoryId": null, "UnitTypesGroupIds": [], "SleepingUnitId": null,
         "MinVehicleLength": 0, "IsADA": false, "WebOnly": true,
         "InSeasonOnly": true, "UnitSort": "orderby"}

    Response::

        {"Facility": {"FacilityId": .., "Latitude": .., "Longitude": ..,
                      "Units": {"<unitId>": {"UnitId": .., "Name": "Cabin 4",
                                             "Slices": {"<date>": {"Date": ..,
                                                                   "IsFree": true}}}}}}

    A unit is bookable for a stay when every night's slice has ``IsFree``.

VERIFICATION STATUS
    Endpoint paths, request keys and response field names are taken from the
    open-source ``camply`` project's UseDirect provider (MIT), which is a
    working implementation against live UseDirect deployments -- so the *shape*
    is solid. What could **not** be checked from this environment is Virginia's
    specific RDR host and its ``PlaceId``/``FacilityId`` values, because the
    egress policy blocks ``reservevaparks.com``. ``rdr_base_url`` below is the
    single value most likely to need correcting; ``cli verify VA`` prints what
    the host actually answers.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, ClassVar

from state_parks.models import Cabin, Park
from state_parks.providers.base import HttpStateProvider, ProviderError
from state_parks.providers.platforms.reserve_america import looks_like_cabin

logger = logging.getLogger(__name__)


def parse_availability(
    payload: dict[str, Any], arrival: date, departure: date
) -> list[dict[str, Any]]:
    """Turn an RDR availability response into per-unit stay results.

    Pure function -- fixture-testable without network access.
    """
    facility = payload.get("Facility") or {}
    units = facility.get("Units") or {}
    if isinstance(units, list):  # some deployments return a list, not a map
        units = {str(u.get("UnitId")): u for u in units}

    stay_nights = [
        (arrival + timedelta(days=i)).isoformat()
        for i in range((departure - arrival).days)
    ]

    results: list[dict[str, Any]] = []
    for unit in units.values():
        slices = unit.get("Slices") or {}
        if isinstance(slices, list):
            slices = {str(s.get("Date", ""))[:10]: s for s in slices}

        # Slice keys are ISO datetimes ("2026-09-04T00:00:00"); index by date.
        by_date = {str(key)[:10]: value for key, value in slices.items()}
        observed = [by_date.get(night) for night in stay_nights]
        if any(entry is None for entry in observed):
            continue

        available = all(bool(entry.get("IsFree")) for entry in observed)
        rates = [
            float(entry["Price"])
            for entry in observed
            if entry.get("Price") not in (None, "", 0)
        ]
        results.append(
            {
                "unit_id": str(unit.get("UnitId") or unit.get("Id") or ""),
                "name": unit.get("Name") or unit.get("ShortName") or "",
                "available": available,
                "rate": round(sum(rates) / len(rates), 2) if rates else None,
                "sleeps": unit.get("SleepingUnitCount") or unit.get("MaxPersons"),
                "is_ada": unit.get("IsAda"),
                "latitude": facility.get("Latitude"),
                "longitude": facility.get("Longitude"),
                "facility_id": str(facility.get("FacilityId") or ""),
            }
        )
    return results


class UseDirectProvider(HttpStateProvider):
    """Shared behaviour for UseDirect (US eDirect) deployments."""

    platform: ClassVar[str] = "usedirect"
    wire_format_verified: ClassVar[bool] = False

    #: Host serving the ``/rdr/rdr/...`` JSON API. Often the booking host
    #: itself, sometimes a dedicated ``*rdr.usedirect.com`` host.
    rdr_base_url: ClassVar[str] = ""
    #: Facilities (campgrounds) known to contain cabins.
    facility_catalog: ClassVar[list[dict[str, Any]]] = []

    default_headers: ClassVar[dict[str, str]] = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }

    def _rdr(self, path: str) -> str:
        return f"{self.rdr_base_url.rstrip('/')}/rdr/rdr/{path.lstrip('/')}"

    async def fetch_places(self) -> list[dict[str, Any]]:
        payload = await self.get_json(self._rdr("search/places"))
        # Deployments differ: some return a bare list, some wrap it.
        if isinstance(payload, dict):
            return payload.get("Where") or payload.get("Results") or []
        return payload or []

    async def fetch_availability(
        self, facility_id: str, arrival: date, departure: date
    ) -> dict[str, Any]:
        body = {
            "FacilityId": str(facility_id),
            "StartDate": arrival.isoformat(),
            "EndDate": departure.isoformat(),
            "UnitCategoryId": None,
            "UnitTypesGroupIds": [],
            "SleepingUnitId": None,
            "MinVehicleLength": 0,
            "IsADA": False,
            "WebOnly": True,
            "InSeasonOnly": True,
            "UnitSort": "orderby",
        }
        # The service 500s on unexpected nulls in some builds; send only real
        # values (this mirrors what camply found necessary in practice).
        body = {k: v for k, v in body.items() if v not in (None, [], "")}
        return await self.post_json(self._rdr("search/availability"), json=body)

    async def list_parks(self) -> list[Park]:
        return [
            Park(
                state=self.state,
                park_id=str(entry["facilityId"]),
                name=entry["name"],
                provider=self.name,
                latitude=entry.get("latitude"),
                longitude=entry.get("longitude"),
                url=self.base_url,
                metadata={"placeId": entry.get("placeId")},
            )
            for entry in self.facility_catalog
        ]

    async def search_cabins(
        self,
        start_date: date,
        end_date: date,
        guests: int,
        pets: bool = False,
    ) -> list[Cabin]:
        results: list[Cabin] = []
        failures = 0
        for facility in self.facility_catalog:
            facility_id = str(facility["facilityId"])
            try:
                payload = await self.fetch_availability(
                    facility_id, start_date, end_date
                )
                units = parse_availability(payload, start_date, end_date)
            except (ProviderError, ValueError) as exc:
                logger.warning(
                    "%s: facility %s failed: %s", self.name, facility_id, exc
                )
                failures += 1
                continue

            for unit in units:
                # Classify per *unit*, not per facility: a UseDirect facility is
                # usually a whole park containing campsites and cabins alike, so
                # a facility-level label would let campsites through. Facilities
                # that really are cabin-only can say so explicitly.
                if not facility.get("cabin_only") and not looks_like_cabin(
                    unit["name"]
                ):
                    continue
                sleeps = unit.get("sleeps") or facility.get("sleeps")
                if sleeps is not None and guests > int(sleeps):
                    continue
                results.append(
                    Cabin(
                        state=self.state,
                        park=facility["name"],
                        park_id=facility_id,
                        cabin_name=unit["name"],
                        cabin_id=unit["unit_id"] or None,
                        arrival=start_date,
                        departure=end_date,
                        available=unit["available"],
                        nightly_rate=unit.get("rate"),
                        sleeps=int(sleeps) if sleeps else None,
                        pet_friendly=facility.get("pet_friendly"),
                        waterfront=facility.get("waterfront"),
                        latitude=unit.get("latitude") or facility.get("latitude"),
                        longitude=unit.get("longitude") or facility.get("longitude"),
                        reservation_url=(
                            f"{self.base_url}/Web/Default.aspx#!park/"
                            f"{facility.get('placeId', '')}/{facility_id}"
                        ),
                        provider=self.name,
                    )
                )

        # See the equivalent note in reserve_america: a total wipeout is an
        # outage, not an empty result, and must not be cached as success.
        if failures and failures == len(self.facility_catalog):
            raise ProviderError(
                f"{self.name}: all {failures} facilities failed for "
                f"{start_date}..{end_date}"
            )
        return results

    async def verify(self) -> dict[str, Any]:
        report = await super().verify()
        checks: list[dict[str, Any]] = []
        try:
            places = await self.fetch_places()
        except (ProviderError, ValueError) as exc:
            checks.append({"check": "search/places", "ok": False, "detail": str(exc)})
        else:
            checks.append(
                {
                    "check": "search/places",
                    "ok": bool(places),
                    "detail": f"{len(places)} places; sample keys="
                    f"{sorted(places[0].keys())[:12] if places else []}",
                }
            )

        if self.facility_catalog:
            arrival = date.today() + timedelta(days=30)
            try:
                payload = await self.fetch_availability(
                    str(self.facility_catalog[0]["facilityId"]),
                    arrival,
                    arrival + timedelta(days=2),
                )
            except (ProviderError, ValueError) as exc:
                checks.append(
                    {"check": "search/availability", "ok": False, "detail": str(exc)}
                )
            else:
                units = parse_availability(
                    payload, arrival, arrival + timedelta(days=2)
                )
                checks.append(
                    {
                        "check": "search/availability",
                        "ok": bool(units),
                        "detail": f"{len(units)} units parsed",
                    }
                )
        report["checks"] = checks
        return report
