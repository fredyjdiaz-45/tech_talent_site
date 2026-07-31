"""ReserveAmerica (Aspira) adapter -- used by North Carolina, Georgia, Delaware.

PLATFORM NOTES
==============
Vendor
    ReserveAmerica, owned by Aspira since 2017. Each agency gets a branded
    subdomain plus a two-letter ``contractCode``:

        NC  https://northcarolinastateparks.reserveamerica.com   contractCode=NC
        GA  https://gastateparks.reserveamerica.com              contractCode=GA
        DE  https://delawarestateparks.reserveamerica.com        contractCode=DE

Why this adapter parses HTML
    The user's preference is JSON endpoints over HTML, and that preference is
    right -- but ReserveAmerica does not offer a usable one. Aspira's public
    "Campground API" (developer.active.com) is XML-only, is documented as having
    *no* availability data ("there is no way to get available dates for
    campgrounds through the API"), and requires an API key that is not issued
    for personal projects. The booking site itself is a server-rendered Struts
    application: every meaningful URL ends in ``.do`` and returns HTML. There is
    no XHR/JSON layer behind it to reverse engineer.

    So HTML parsing here is the "absolutely necessary" case, not a shortcut.
    It is confined to :func:`parse_campsite_calendar` so the blast radius of a
    markup change is one function with fixture-backed tests.

Request shape (reconstructed)
    Availability grid for one campground, 14 nights from ``calarvdate``::

        GET /campsiteCalendar.do
            ?page=calendar
            &contractCode=NC
            &parkId=<park id>
            &calarvdate=MM/DD/YYYY
            &sitepage=true

    The response contains ``table#calendar``: one row per site, one cell per
    night. Availability is carried in the cell's CSS class -- ``.a`` (free),
    ``.r``/``.x`` (reserved), ``.n`` (not available / closed). Site rows link to
    ``campsiteDetails.do?siteId=<id>``, which is the stable per-cabin id.

    ``parkId`` values are per-contract and must be seeded from each state's
    catalog (``providers/catalog/<state>.json``); they are not discoverable
    without walking the search UI.

VERIFICATION STATUS
    Unverified. The build environment's egress policy blocked
    ``*.reserveamerica.com`` (403 on CONNECT), and the site returns 403 to
    non-browser clients besides. The selectors below follow ReserveAmerica's
    long-standing ``campsiteCalendar.do`` markup, and the parser is written
    defensively with several fallback selectors, but the exact classes must be
    confirmed against a real response before trusting the output. Run::

        python -m state_parks.cli verify NC --save-fixture

    which writes the live HTML to ``tests/fixtures/`` so the parser can be
    corrected against reality in one edit.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any, ClassVar

from bs4 import BeautifulSoup, Tag

from state_parks.models import Cabin, Park
from state_parks.providers.base import HttpStateProvider, ProviderError

logger = logging.getLogger(__name__)

#: The calendar view returns two weeks per request.
CALENDAR_WINDOW_DAYS = 14

#: Site-type words that mean "a building you sleep in" rather than a campsite.
#: ReserveAmerica has no single "is a cabin" flag, so classification is by name
#: and by the loop/site-type label.
CABIN_KEYWORDS = (
    "cabin",
    "cottage",
    "lodge",
    "yurt",
    "villa",
    "bunkhouse",
    "camping shelter",
)

_AVAILABLE_CLASSES = {"a", "available", "sa"}
_UNAVAILABLE_CLASSES = {"r", "x", "n", "nr", "unavailable", "reserved", "closed"}

_RATE_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{2})?)")
_SITE_ID_RE = re.compile(r"siteId=(\d+)")


def looks_like_cabin(name: str, site_type: str | None = None) -> bool:
    """Heuristic cabin classifier for platforms without a lodging flag."""
    haystack = f"{name} {site_type or ''}".lower()
    return any(word in haystack for word in CABIN_KEYWORDS)


def _cell_available(cell: Tag) -> bool | None:
    """Interpret one night cell. Returns None when the cell says nothing."""
    classes = {c.lower() for c in cell.get("class", [])}
    if classes & _AVAILABLE_CLASSES:
        return True
    if classes & _UNAVAILABLE_CLASSES:
        return False
    # Fall back to the cell text/link: available cells link to a booking action
    # and usually read "A"; blocked ones read "R"/"X".
    text = cell.get_text(strip=True).lower()
    if text in {"a", "available"}:
        return True
    if text in {"r", "x", "n"}:
        return False
    if cell.find("a", href=re.compile("book|arrivalDate", re.I)):
        return True
    return None


def parse_campsite_calendar(
    html: str, start: date, window_days: int = CALENDAR_WINDOW_DAYS
) -> list[dict[str, Any]]:
    """Parse a ``campsiteCalendar.do`` grid into per-site nightly availability.

    Returns one dict per site::

        {"site_id": "12345", "name": "Cabin 3", "loop": "Cabin Area",
         "rate": 95.0, "nights": {date(...): True, ...}}

    Kept pure (str in, dicts out) so it can be tested against saved fixtures
    without any network access.
    """
    soup = BeautifulSoup(html, "lxml")
    table = (
        soup.find("table", id="calendar")
        or soup.find("table", class_="items")
        or soup.find("table")
    )
    if table is None:
        raise ProviderError("campsiteCalendar.do: no calendar table found")

    # Prefer explicit column dates from the header when present; the header
    # encodes the true night for each column, which beats assuming the grid
    # starts exactly on `start` (ReserveAmerica snaps to week boundaries).
    column_dates = _header_dates(table, start, window_days)

    sites: list[dict[str, Any]] = []
    for row in table.find_all("tr"):
        name_cell = (
            row.find("td", class_="sn")
            or row.find("td", class_="siteName")
            or row.find("th", class_="sn")
        )
        if name_cell is None:
            continue

        link = name_cell.find("a")
        name = (link or name_cell).get_text(strip=True)
        if not name:
            continue

        site_id = None
        if link is not None and link.get("href"):
            match = _SITE_ID_RE.search(link["href"])
            if match:
                site_id = match.group(1)

        loop_cell = row.find("td", class_="loopName") or row.find("td", class_="ln")
        loop = loop_cell.get_text(strip=True) if loop_cell else None

        status_cells = row.find_all("td", class_="status")
        if not status_cells:
            # Some skins drop the `status` class; fall back to every cell after
            # the descriptive ones.
            status_cells = [
                td
                for td in row.find_all("td")
                if td is not name_cell and td is not loop_cell
            ]

        nights: dict[date, bool] = {}
        for index, cell in enumerate(status_cells):
            if index >= len(column_dates):
                break
            state = _cell_available(cell)
            if state is not None:
                nights[column_dates[index]] = state

        if not nights:
            continue

        rate_match = _RATE_RE.search(row.get_text(" ", strip=True))
        sites.append(
            {
                "site_id": site_id,
                "name": name,
                "loop": loop,
                "rate": float(rate_match.group(1)) if rate_match else None,
                "nights": nights,
            }
        )
    return sites


def _header_dates(table: Tag, start: date, window_days: int) -> list[date]:
    """Read night dates from the calendar header, falling back to a range."""
    fallback = [start + timedelta(days=i) for i in range(window_days)]
    header = table.find("tr", class_="tbl_head") or table.find("thead")
    if header is None:
        return fallback

    dates: list[date] = []
    # Headers render as e.g. "Fri<br/>Mar 14" -- pull month/day and infer the
    # year from `start`, handling the December->January rollover.
    for cell in header.find_all(["th", "td"]):
        text = cell.get_text(" ", strip=True)
        match = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2})", text)
        if not match:
            continue
        try:
            month = [
                "jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec",
            ].index(match.group(1).lower()[:3]) + 1
        except ValueError:
            continue
        day = int(match.group(2))
        year = start.year + 1 if month < start.month else start.year
        try:
            dates.append(date(year, month, day))
        except ValueError:
            continue
    return dates or fallback


class ReserveAmericaProvider(HttpStateProvider):
    """Shared behaviour for every ReserveAmerica-hosted state."""

    platform: ClassVar[str] = "reserve_america"
    wire_format_verified: ClassVar[bool] = False

    #: Two-letter agency contract code used in every query string.
    contract_code: ClassVar[str] = ""
    #: Parks known to have cabins: ``{"parkId": ..., "name": ..., ...}``.
    park_catalog: ClassVar[list[dict[str, Any]]] = []

    default_headers: ClassVar[dict[str, str]] = {
        # This endpoint serves HTML; asking for JSON gets a 406 on some skins.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def list_parks(self) -> list[Park]:
        return [
            Park(
                state=self.state,
                park_id=str(entry["parkId"]),
                name=entry["name"],
                provider=self.name,
                latitude=entry.get("latitude"),
                longitude=entry.get("longitude"),
                url=self._park_url(str(entry["parkId"])),
                metadata={"contractCode": self.contract_code},
            )
            for entry in self.park_catalog
        ]

    def _park_url(self, park_id: str) -> str:
        return (
            f"{self.base_url}/campgroundDetails.do"
            f"?contractCode={self.contract_code}&parkId={park_id}"
        )

    def _site_url(self, park_id: str, site_id: str | None) -> str:
        if site_id is None:
            return self._park_url(park_id)
        return (
            f"{self.base_url}/campsiteDetails.do"
            f"?contractCode={self.contract_code}&parkId={park_id}&siteId={site_id}"
        )

    async def fetch_calendar(self, park_id: str, arrival: date) -> str:
        """Fetch the 14-night availability grid for one park."""
        response = await self.request(
            "GET",
            "/campsiteCalendar.do",
            params={
                "page": "calendar",
                "contractCode": self.contract_code,
                "parkId": park_id,
                "calarvdate": arrival.strftime("%m/%d/%Y"),
                "sitepage": "true",
                # Ask for lodging only where the skin honours it; harmless
                # otherwise since we re-filter by name below.
                "siteTypeFilter": "CABIN",
            },
        )
        return response.text

    async def search_cabins(
        self,
        start_date: date,
        end_date: date,
        guests: int,
        pets: bool = False,
    ) -> list[Cabin]:
        results: list[Cabin] = []
        failures = 0
        for park in self.park_catalog:
            park_id = str(park["parkId"])
            try:
                nights_by_site = await self._collect_park(park_id, start_date, end_date)
            except ProviderError as exc:
                # One bad park should not lose the whole state's refresh.
                logger.warning("%s: park %s failed: %s", self.name, park_id, exc)
                failures += 1
                continue

            for site in nights_by_site:
                if not looks_like_cabin(site["name"], site.get("loop")):
                    continue
                stay_nights = [
                    start_date + timedelta(days=i)
                    for i in range((end_date - start_date).days)
                ]
                observed = [site["nights"].get(n) for n in stay_nights]
                if any(state is None for state in observed):
                    # Incomplete grid coverage -- do not guess.
                    continue
                results.append(
                    Cabin(
                        state=self.state,
                        park=park["name"],
                        park_id=park_id,
                        cabin_name=site["name"],
                        cabin_id=site["site_id"],
                        arrival=start_date,
                        departure=end_date,
                        available=all(observed),
                        nightly_rate=site.get("rate"),
                        sleeps=park.get("sleeps"),
                        pet_friendly=park.get("pet_friendly"),
                        waterfront=park.get("waterfront"),
                        latitude=park.get("latitude"),
                        longitude=park.get("longitude"),
                        reservation_url=self._site_url(park_id, site["site_id"]),
                        provider=self.name,
                    )
                )

        # If *every* park failed, this is an outage (or a broken selector), not
        # an empty result. Raising keeps the refresh window marked stale so the
        # next run retries it, instead of caching "no cabins" for a day.
        if failures and failures == len(self.park_catalog):
            raise ProviderError(
                f"{self.name}: all {failures} parks failed for "
                f"{start_date}..{end_date}"
            )
        return results

    async def _collect_park(
        self, park_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Walk 14-night calendar pages until the whole window is covered."""
        merged: dict[str, dict[str, Any]] = {}
        cursor = start_date
        while cursor < end_date:
            html = await self.fetch_calendar(park_id, cursor)
            for site in parse_campsite_calendar(html, cursor):
                key = site["site_id"] or site["name"]
                if key in merged:
                    merged[key]["nights"].update(site["nights"])
                    merged[key]["rate"] = merged[key]["rate"] or site["rate"]
                else:
                    merged[key] = site
            cursor += timedelta(days=CALENDAR_WINDOW_DAYS)
        return list(merged.values())

    async def verify(self) -> dict[str, Any]:
        """Fetch one real calendar page and report what the parser found."""
        report = await super().verify()
        checks: list[dict[str, Any]] = []
        if not self.park_catalog:
            checks.append(
                {"check": "park_catalog", "ok": False, "detail": "catalog is empty"}
            )
            report["checks"] = checks
            return report

        park_id = str(self.park_catalog[0]["parkId"])
        arrival = date.today() + timedelta(days=30)
        try:
            html = await self.fetch_calendar(park_id, arrival)
        except ProviderError as exc:
            checks.append({"check": "fetch_calendar", "ok": False, "detail": str(exc)})
            report["checks"] = checks
            return report

        checks.append(
            {"check": "fetch_calendar", "ok": True, "detail": f"{len(html)} bytes"}
        )
        try:
            sites = parse_campsite_calendar(html, arrival)
        except ProviderError as exc:
            checks.append({"check": "parse", "ok": False, "detail": str(exc)})
        else:
            cabins = [s for s in sites if looks_like_cabin(s["name"], s.get("loop"))]
            checks.append(
                {
                    "check": "parse",
                    "ok": bool(sites),
                    "detail": f"{len(sites)} sites, {len(cabins)} classified as cabins",
                }
            )
        report["checks"] = checks
        report["raw_sample"] = html[:2000]
        return report


def merge_night_maps(maps: Iterable[dict[date, bool]]) -> dict[date, bool]:
    """Combine per-page night maps; later pages win on conflict."""
    merged: dict[date, bool] = {}
    for night_map in maps:
        merged.update(night_map)
    return merged
