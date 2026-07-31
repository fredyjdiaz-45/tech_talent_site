"""Provider tests with mocked HTTP.

These exercise the full provider path -- request building, response parsing,
normalization into ``Cabin`` -- without touching the network, using ``respx`` to
intercept httpx. They also lock in the properties the whole architecture rests
on: that every provider satisfies the same interface, and that the caller can
never tell which platform answered.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import httpx
import pytest
import respx

from state_parks.models import Cabin
from state_parks.providers import (
    PROVIDER_CLASSES,
    NotVerifiedError,
    StateProvider,
    all_providers,
    get_provider,
)
from state_parks.providers.base import ProviderError
from state_parks.providers.north_carolina import NorthCarolinaProvider
from state_parks.providers.virginia import VirginiaProvider
from tests.conftest import load_fixture, load_json_fixture

ARRIVAL = date(2026, 9, 4)
DEPARTURE = ARRIVAL + timedelta(days=2)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Registry / interface conformance
# ---------------------------------------------------------------------------
class TestRegistry:
    async def test_all_seven_states_are_registered(self) -> None:
        assert set(PROVIDER_CLASSES) == {"NC", "SC", "VA", "GA", "TN", "DE", "MD"}

    async def test_every_provider_implements_the_interface(self) -> None:
        for code, cls in PROVIDER_CLASSES.items():
            provider = cls()
            assert isinstance(provider, StateProvider)
            assert provider.state == code
            assert provider.base_url.startswith("https://")
            assert callable(provider.search_cabins)
            await provider.aclose()

    async def test_lookup_is_case_insensitive(self) -> None:
        provider = get_provider("nc")
        assert isinstance(provider, NorthCarolinaProvider)
        await provider.aclose()

    async def test_unknown_state_raises(self) -> None:
        with pytest.raises(KeyError):
            get_provider("XX")

    async def test_all_providers_respects_an_explicit_subset(self) -> None:
        providers = all_providers(["NC", "VA"])
        assert [p.state for p in providers] == ["NC", "VA"]
        for provider in providers:
            await provider.aclose()

    async def test_platforms_are_shared_as_designed(self) -> None:
        """Code reuse is a requirement here, so assert the grouping holds."""
        platforms: dict[str, list[str]] = {}
        for code, cls in PROVIDER_CLASSES.items():
            platforms.setdefault(cls.platform, []).append(code)
        assert sorted(platforms["reserve_america"]) == ["DE", "GA", "NC"]
        assert sorted(platforms["itinio"]) == ["SC", "TN"]
        assert platforms["usedirect"] == ["VA"]
        assert platforms["aspira_connect"] == ["MD"]


# ---------------------------------------------------------------------------
# North Carolina (ReserveAmerica) -- provider #1
# ---------------------------------------------------------------------------
class TestNorthCarolina:
    @respx.mock
    async def test_search_returns_normalized_cabins(self) -> None:
        provider = NorthCarolinaProvider()
        provider.park_catalog = [
            {"parkId": "3234", "name": "Morrow Mountain State Park",
             "latitude": 35.3743, "longitude": -80.0723, "sleeps": 6,
             "waterfront": False, "pet_friendly": False}
        ]
        respx.get(
            url__regex=r".*campsiteCalendar\.do.*"
        ).mock(
            return_value=httpx.Response(
                200, text=load_fixture("reserve_america_calendar.html")
            )
        )

        cabins = await provider.search_cabins(ARRIVAL, DEPARTURE, guests=2)
        await provider.aclose()

        # Cabin 1 free both nights; Cabin 2 blocked on the 5th; Camping Cabin 7
        # fully blocked. The tent site must be filtered out entirely.
        by_name = {c.cabin_name: c for c in cabins}
        assert "Tent Site 14" not in by_name
        assert by_name["Cabin 1"].available is True
        assert by_name["Cabin 2"].available is False
        assert by_name["Camping Cabin 7"].available is False

    @respx.mock
    async def test_normalization_fills_the_common_model(self) -> None:
        provider = NorthCarolinaProvider()
        provider.park_catalog = [
            {"parkId": "3234", "name": "Morrow Mountain State Park",
             "latitude": 35.3743, "longitude": -80.0723, "sleeps": 6,
             "waterfront": False, "pet_friendly": False}
        ]
        respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(
                200, text=load_fixture("reserve_america_calendar.html")
            )
        )
        cabin = next(
            c
            for c in await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
            if c.cabin_name == "Cabin 1"
        )
        await provider.aclose()

        assert isinstance(cabin, Cabin)
        assert cabin.state == "NC"
        assert cabin.park == "Morrow Mountain State Park"
        assert cabin.cabin_id == "91001"
        assert cabin.nightly_rate == 95.0
        assert cabin.sleeps == 6
        assert cabin.latitude == 35.3743
        assert "siteId=91001" in cabin.reservation_url
        assert cabin.provider == "NC"

    @respx.mock
    async def test_a_failing_park_does_not_sink_the_state(self) -> None:
        provider = NorthCarolinaProvider()
        provider.park_catalog = [
            {"parkId": "bad", "name": "Broken Park"},
            {"parkId": "3234", "name": "Morrow Mountain State Park"},
        ]
        respx.get(url__regex=r".*parkId=bad.*").mock(
            return_value=httpx.Response(404)
        )
        respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(
                200, text=load_fixture("reserve_america_calendar.html")
            )
        )
        cabins = await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
        await provider.aclose()
        assert {c.park for c in cabins} == {"Morrow Mountain State Park"}

    @respx.mock
    async def test_client_errors_are_not_retried(self) -> None:
        """Retrying a 404 just hammers a public agency's server."""
        provider = NorthCarolinaProvider()
        route = respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(ProviderError):
            await provider.fetch_calendar("3234", ARRIVAL)
        await provider.aclose()
        assert route.call_count == 1

    @respx.mock
    async def test_server_errors_are_retried(self, monkeypatch) -> None:
        from state_parks.config import settings

        monkeypatch.setattr(settings, "retry_backoff", 0.0)
        monkeypatch.setattr(settings, "request_delay", 0.0)
        provider = NorthCarolinaProvider()
        route = respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(ProviderError):
            await provider.fetch_calendar("3234", ARRIVAL)
        await provider.aclose()
        assert route.call_count == settings.max_retries

    @respx.mock
    async def test_request_carries_the_contract_code(self) -> None:
        provider = NorthCarolinaProvider()
        route = respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(200, text="<table id='calendar'></table>")
        )
        await provider.fetch_calendar("3234", ARRIVAL)
        await provider.aclose()
        request_url = str(route.calls[0].request.url)
        assert "contractCode=NC" in request_url
        assert "parkId=3234" in request_url
        assert "calarvdate=09%2F04%2F2026" in request_url


# ---------------------------------------------------------------------------
# Virginia (UseDirect)
# ---------------------------------------------------------------------------
class TestVirginia:
    @respx.mock
    async def test_search_uses_the_json_api(self) -> None:
        provider = VirginiaProvider()
        provider.facility_catalog = [
            {"facilityId": "1", "placeId": "1", "name": "Douthat State Park",
             "waterfront": True, "pet_friendly": True}
        ]
        route = respx.post(url__regex=r".*/rdr/rdr/search/availability").mock(
            return_value=httpx.Response(
                200, json=load_json_fixture("usedirect_availability.json")
            )
        )
        cabins = await provider.search_cabins(ARRIVAL, ARRIVAL + timedelta(days=3), 2)
        await provider.aclose()

        body = json.loads(route.calls[0].request.content)
        assert body["FacilityId"] == "1"
        assert body["StartDate"] == "2026-09-04"
        assert body["EndDate"] == "2026-09-07"
        # Empty values are stripped before sending -- some RDR builds 500 on them.
        assert "UnitCategoryId" not in body
        assert "UnitTypesGroupIds" not in body

        by_name = {c.cabin_name: c for c in cabins}
        assert "Campsite 22" not in by_name  # campsites filtered out
        assert by_name["Cabin 3"].available is True
        assert by_name["Cabin 4"].available is False
        assert by_name["Cabin 3"].state == "VA"
        assert by_name["Cabin 3"].nightly_rate == 132.0

    @respx.mock
    async def test_party_larger_than_capacity_is_dropped(self) -> None:
        provider = VirginiaProvider()
        provider.facility_catalog = [
            {"facilityId": "1", "placeId": "1", "name": "Douthat State Park"}
        ]
        respx.post(url__regex=r".*/rdr/rdr/search/availability").mock(
            return_value=httpx.Response(
                200, json=load_json_fixture("usedirect_availability.json")
            )
        )
        cabins = await provider.search_cabins(
            ARRIVAL, ARRIVAL + timedelta(days=3), guests=5
        )
        await provider.aclose()
        # Cabin 3 sleeps 6, Cabin 4 sleeps 4.
        assert {c.cabin_name for c in cabins} == {"Cabin 3"}


# ---------------------------------------------------------------------------
# Itinio providers (SC, TN) -- unverified by design
# ---------------------------------------------------------------------------
class TestItinioProviders:
    @pytest.mark.parametrize("code", ["SC", "TN"])
    async def test_search_refuses_rather_than_guessing(self, code: str) -> None:
        """An unknown endpoint must fail loudly, not silently return nothing."""
        provider = get_provider(code)
        with pytest.raises(NotVerifiedError, match="not known yet"):
            await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
        await provider.aclose()

    @pytest.mark.parametrize("code", ["SC", "TN"])
    async def test_parks_are_listed_even_though_availability_is_not(
        self, code: str
    ) -> None:
        provider = get_provider(code)
        parks = await provider.list_parks()
        await provider.aclose()
        assert len(parks) >= 5
        assert all(p.state == code for p in parks)

    @respx.mock
    async def test_inventory_scrape_works_today(self) -> None:
        provider = get_provider("TN")
        respx.get(url__regex=r".*/standing-stone/cabins").mock(
            return_value=httpx.Response(
                200,
                text='<div class="cabin"><h3>Cabin 1</h3><p>Sleeps 6 $150.00</p></div>',
            )
        )
        listing = await provider.fetch_cabin_listing("standing-stone")
        await provider.aclose()
        assert listing[0]["name"] == "Cabin 1"


# ---------------------------------------------------------------------------
# Maryland (Aspira Connect)
# ---------------------------------------------------------------------------
class TestMaryland:
    @respx.mock
    async def test_search_parses_the_map_endpoint(self) -> None:
        provider = get_provider("MD")
        provider.location_catalog = [
            {
                "resourceLocationId": "-2147483600",
                "mapId": "-2147483647",
                "name": "Rocky Gap State Park",
                "resources": {
                    "2001": {"name": "Cabin 1", "sleeps": 6},
                    "2002": {"name": "Cabin 2", "sleeps": 4},
                    "2003": {"name": "Campsite 9", "sleeps": 6},
                },
            }
        ]
        route = respx.get(url__regex=r".*/api/availability/map.*").mock(
            return_value=httpx.Response(
                200, json=load_json_fixture("aspira_map_availability.json")
            )
        )
        cabins = await provider.search_cabins(ARRIVAL, ARRIVAL + timedelta(days=3), 2)
        await provider.aclose()

        request_url = str(route.calls[0].request.url)
        assert "resourceLocationId=-2147483600" in request_url
        assert "startDate=2026-09-04" in request_url

        by_name = {c.cabin_name: c for c in cabins}
        assert "Campsite 9" not in by_name
        assert by_name["Cabin 1"].available is True
        assert by_name["Cabin 2"].available is False

    @respx.mock
    async def test_discover_builds_a_catalog(self) -> None:
        provider = get_provider("MD")
        respx.get(url__regex=r".*/api/resourceLocation").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "resourceLocationId": -2147483600,
                        "localizedValues": [{"fullName": "Rocky Gap State Park"}],
                    }
                ],
            )
        )
        respx.get(url__regex=r".*/api/maps").mock(
            return_value=httpx.Response(
                200,
                json=[{"resourceLocationId": -2147483600, "mapId": -2147483647}],
            )
        )
        catalog = await provider.discover()
        await provider.aclose()
        assert catalog[0]["name"] == "Rocky Gap State Park"
        assert catalog[0]["mapId"] == -2147483647


class TestOutageHandling:
    """A total failure must surface as an error, not as 'no cabins today'.

    Otherwise the refresh service marks the window fresh and caches an empty
    result for a day -- exactly when you most want it to retry.
    """

    @respx.mock
    async def test_all_parks_failing_raises(self) -> None:
        provider = NorthCarolinaProvider()
        provider.park_catalog = [
            {"parkId": "1", "name": "A"},
            {"parkId": "2", "name": "B"},
        ]
        respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(ProviderError, match="all 2 parks failed"):
            await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
        await provider.aclose()

    @respx.mock
    async def test_partial_failure_still_returns_results(self) -> None:
        provider = NorthCarolinaProvider()
        provider.park_catalog = [
            {"parkId": "bad", "name": "Broken"},
            {"parkId": "3234", "name": "Morrow Mountain State Park"},
        ]
        respx.get(url__regex=r".*parkId=bad.*").mock(
            return_value=httpx.Response(404)
        )
        respx.get(url__regex=r".*campsiteCalendar\.do.*").mock(
            return_value=httpx.Response(
                200, text=load_fixture("reserve_america_calendar.html")
            )
        )
        assert await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
        await provider.aclose()

    @respx.mock
    async def test_usedirect_total_failure_raises(self) -> None:
        provider = VirginiaProvider()
        provider.facility_catalog = [{"facilityId": "1", "name": "A"}]
        respx.post(url__regex=r".*/rdr/rdr/search/availability").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(ProviderError, match="all 1 facilities failed"):
            await provider.search_cabins(ARRIVAL, DEPARTURE, 2)
        await provider.aclose()
