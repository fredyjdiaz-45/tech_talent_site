"""Itinio adapter -- used by South Carolina and Tennessee.

PLATFORM NOTES
==============
Vendor
    Itinio, a smaller reservation vendor than Aspira/UseDirect. Both states run
    the same product, which is why they share this adapter:

        SC  https://reserve.southcarolinaparks.com
        TN  https://reserve.tnstateparks.com   (also served as tsp.itinio.com)

    The give-away is the URL scheme, identical across both states:
    ``/<park-slug>/cabins``, ``/<park-slug>/camping``, ``/myaccount/``. Tennessee
    pages are additionally reachable under ``tsp.itinio.com`` /
    ``tspg.itinio.com``, which is what identifies the vendor by name.

VERIFICATION STATUS -- READ THIS FIRST
    This is the least-verified adapter in the project, and it is disabled by
    default (``enabled = False``).

    Neither the endpoints nor the response shapes could be observed: the hosts
    are blocked by this environment's egress policy, and they also return 403
    to non-browser clients. Unlike UseDirect and Aspira Connect, Itinio has no
    open-source client I could use as a reference for its wire format, so
    inventing endpoint names here would produce confident-looking code that
    silently fails -- worse than no code.

    What this module therefore provides:

    1. :meth:`ItinioProvider.probe` -- asks a list of *candidate* endpoints
       which ones exist and which return JSON, and reports the result. Run
       ``python -m state_parks.cli verify SC`` from an unrestricted network and
       it will tell you what the real API looks like.
    2. A JSON-first / HTML-fallback :meth:`search_cabins` built around a single
       configurable ``availability_path`` template plus a
       :func:`parse_availability_json` normalizer, so wiring in the real
       endpoint is a one-line change plus a fixture.

    In other words: the structure is finished, the two facts that need a
    browser's network tab are marked and isolated.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from state_parks.models import Cabin, Park
from state_parks.providers.base import (
    HttpStateProvider,
    NotVerifiedError,
    ProviderError,
)

logger = logging.getLogger(__name__)

#: Endpoint paths worth trying when probing an Itinio deployment. Ordered by
#: how likely they are, based on the site's public URL conventions.
CANDIDATE_PATHS: tuple[str, ...] = (
    "/api/availability",
    "/api/search",
    "/api/lodging/availability",
    "/availability.json",
    "/{park}/cabins.json",
    "/{park}/availability",
    "/services/availability",
)

_RATE_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{2})?)")


def parse_availability_json(
    payload: Any, arrival: date, departure: date
) -> list[dict[str, Any]]:
    """Normalize an Itinio-style availability payload.

    Written against the shapes these systems converge on rather than a captured
    response: a list of units, each with an id, a name, a rate, and either a
    boolean ``available`` or a list of per-night entries. Adjust once a real
    response is in hand -- the fixture test documents the expected contract.
    """
    if isinstance(payload, dict):
        units = (
            payload.get("units")
            or payload.get("results")
            or payload.get("sites")
            or payload.get("data")
            or []
        )
    else:
        units = payload or []

    nights = (departure - arrival).days
    results: list[dict[str, Any]] = []

    for unit in units:
        if not isinstance(unit, dict):
            continue

        available: bool | None = None
        if isinstance(unit.get("nights"), list):
            window = unit["nights"][:nights]
            if len(window) == nights:
                available = all(
                    bool(n.get("available", n.get("isAvailable"))) for n in window
                )
        if available is None:
            for key in ("available", "isAvailable", "bookable"):
                if key in unit:
                    available = bool(unit[key])
                    break
        if available is None:
            continue

        rate = unit.get("rate") or unit.get("price") or unit.get("nightlyRate")
        results.append(
            {
                "unit_id": str(
                    unit.get("id") or unit.get("unitId") or unit.get("siteId") or ""
                ),
                "name": unit.get("name") or unit.get("title") or "",
                "available": available,
                "rate": float(rate) if rate not in (None, "") else None,
                "sleeps": unit.get("sleeps") or unit.get("maxOccupancy"),
                "bedrooms": unit.get("bedrooms"),
            }
        )
    return results


def parse_cabin_listing_html(html: str) -> list[dict[str, Any]]:
    """Scrape the public ``/<park>/cabins`` page for the cabin *inventory*.

    Inventory only -- names, rates and sleeps -- not availability. Even
    unverified this is useful: it seeds the cabin catalog so the rest of the
    system has something to attach availability to once the API is known.
    """
    soup = BeautifulSoup(html, "lxml")
    cabins: list[dict[str, Any]] = []

    for node in soup.select(
        ".cabin, .lodging-item, .unit, article.cabin, li.cabin, .room-type"
    ):
        heading = node.find(["h2", "h3", "h4"])
        name = heading.get_text(strip=True) if heading else None
        if not name:
            continue
        text = node.get_text(" ", strip=True)
        rate_match = _RATE_RE.search(text)
        sleeps_match = re.search(r"sleeps\s+(\d+)", text, re.I)
        bedrooms_match = re.search(r"(\d+)\s*bedroom", text, re.I)
        link = node.find("a", href=True)
        cabins.append(
            {
                "name": name,
                "rate": float(rate_match.group(1)) if rate_match else None,
                "sleeps": int(sleeps_match.group(1)) if sleeps_match else None,
                "bedrooms": int(bedrooms_match.group(1)) if bedrooms_match else None,
                "url": link["href"] if link else None,
            }
        )
    return cabins


class ItinioProvider(HttpStateProvider):
    """Shared behaviour for Itinio deployments (SC, TN)."""

    platform: ClassVar[str] = "itinio"
    wire_format_verified: ClassVar[bool] = False
    #: Off by default: see the module docstring. Flip to True once `verify`
    #: has confirmed `availability_path` and `parse_availability_json`.
    enabled: ClassVar[bool] = False

    #: Set this once the real endpoint is known. ``{park}`` is substituted with
    #: the park slug.
    availability_path: ClassVar[str | None] = None
    #: Parks with cabins: {"slug": "standing-stone", "name": "Standing Stone"}.
    park_catalog: ClassVar[list[dict[str, Any]]] = []

    default_headers: ClassVar[dict[str, str]] = {
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def list_parks(self) -> list[Park]:
        return [
            Park(
                state=self.state,
                park_id=entry["slug"],
                name=entry["name"],
                provider=self.name,
                latitude=entry.get("latitude"),
                longitude=entry.get("longitude"),
                url=f"{self.base_url}/{entry['slug']}/cabins",
                metadata={"slug": entry["slug"]},
            )
            for entry in self.park_catalog
        ]

    async def fetch_cabin_listing(self, slug: str) -> list[dict[str, Any]]:
        """Inventory for one park from its public cabins page."""
        response = await self.request("GET", f"/{slug}/cabins")
        return parse_cabin_listing_html(response.text)

    async def search_cabins(
        self,
        start_date: date,
        end_date: date,
        guests: int,
        pets: bool = False,
    ) -> list[Cabin]:
        if not self.availability_path:
            raise NotVerifiedError(
                f"{self.name}: Itinio availability endpoint is not known yet. "
                f"Run `python -m state_parks.cli verify {self.state}` from an "
                f"unrestricted network to discover it, then set "
                f"`availability_path` on the provider. Inventory-only listing "
                f"is available via `list_cabins()`."
            )

        results: list[Cabin] = []
        for park in self.park_catalog:
            slug = park["slug"]
            path = self.availability_path.format(park=slug)
            try:
                payload = await self.get_json(
                    path,
                    params={
                        "arrival": start_date.isoformat(),
                        "departure": end_date.isoformat(),
                        "guests": guests,
                    },
                )
                units = parse_availability_json(payload, start_date, end_date)
            except (ProviderError, ValueError) as exc:
                logger.warning("%s: park %s failed: %s", self.name, slug, exc)
                continue

            for unit in units:
                sleeps = unit.get("sleeps")
                if sleeps is not None and guests > int(sleeps):
                    continue
                results.append(
                    Cabin(
                        state=self.state,
                        park=park["name"],
                        park_id=slug,
                        cabin_name=unit["name"],
                        cabin_id=unit["unit_id"] or None,
                        arrival=start_date,
                        departure=end_date,
                        available=unit["available"],
                        nightly_rate=unit.get("rate"),
                        sleeps=int(sleeps) if sleeps else None,
                        bedrooms=unit.get("bedrooms"),
                        pet_friendly=park.get("pet_friendly"),
                        waterfront=park.get("waterfront"),
                        latitude=park.get("latitude"),
                        longitude=park.get("longitude"),
                        reservation_url=f"{self.base_url}/{slug}/cabins",
                        provider=self.name,
                    )
                )
        return results

    async def probe(self) -> list[dict[str, Any]]:
        """Try candidate endpoints and report which ones exist.

        This is the tool for finishing the adapter: it reports status code and
        content type per candidate, so the real availability endpoint can be
        identified without guessing.
        """
        slug = self.park_catalog[0]["slug"] if self.park_catalog else "park"
        arrival = date.today() + timedelta(days=30)
        findings: list[dict[str, Any]] = []

        for template in CANDIDATE_PATHS:
            path = template.format(park=slug)
            try:
                response = await self.request(
                    "GET",
                    path,
                    params={
                        "arrival": arrival.isoformat(),
                        "departure": (arrival + timedelta(days=2)).isoformat(),
                    },
                )
            except ProviderError as exc:
                findings.append({"path": path, "ok": False, "detail": str(exc)})
                continue

            content_type = response.headers.get("content-type", "")
            finding: dict[str, Any] = {
                "path": path,
                "ok": True,
                "status": response.status_code,
                "content_type": content_type,
            }
            if "json" in content_type:
                try:
                    payload = response.json()
                except ValueError:
                    finding["detail"] = "declared JSON but did not parse"
                else:
                    finding["json_keys"] = (
                        sorted(payload.keys())[:20]
                        if isinstance(payload, dict)
                        else f"list[{len(payload)}]"
                    )
            findings.append(finding)
        return findings

    async def verify(self) -> dict[str, Any]:
        report = await super().verify()
        checks: list[dict[str, Any]] = []

        if self.park_catalog:
            slug = self.park_catalog[0]["slug"]
            try:
                listing = await self.fetch_cabin_listing(slug)
            except ProviderError as exc:
                checks.append(
                    {"check": f"/{slug}/cabins", "ok": False, "detail": str(exc)}
                )
            else:
                checks.append(
                    {
                        "check": f"/{slug}/cabins",
                        "ok": bool(listing),
                        "detail": f"{len(listing)} cabins parsed from HTML",
                    }
                )

        report["checks"] = checks
        report["endpoint_probe"] = await self.probe()
        report["next_step"] = (
            "Identify the availability endpoint in the probe results (or from "
            "the browser network tab on a real search), set "
            "`availability_path` on this provider, save a response to "
            "tests/fixtures/, and flip `enabled`/`wire_format_verified`."
        )
        return report
