"""Parser tests for each platform adapter.

These are the tests that matter most in this project: the parsers are the part
most likely to break when an upstream site changes, and they are pure functions
so they can be tested exhaustively without touching the network.

Note the fixtures are hand-built to the documented wire formats, not captured
from live responses (docs/PLATFORMS.md explains why). They therefore verify
*parser logic* -- that a blocked night makes a stay unavailable, that cabins are
told apart from campsites, that partial data is refused -- rather than proving
the upstream shape is right.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from state_parks.providers.base import ProviderError
from state_parks.providers.platforms.aspira_connect import (
    flatten_nested_availabilities,
    parse_map_availability,
)
from state_parks.providers.platforms.itinio import (
    parse_availability_json,
    parse_cabin_listing_html,
)
from state_parks.providers.platforms.reserve_america import (
    looks_like_cabin,
    parse_campsite_calendar,
)
from state_parks.providers.platforms.usedirect import parse_availability
from tests.conftest import load_fixture, load_json_fixture

ARRIVAL = date(2026, 9, 4)


# ---------------------------------------------------------------------------
# ReserveAmerica (NC, GA, DE)
# ---------------------------------------------------------------------------
class TestReserveAmerica:
    @pytest.fixture
    def sites(self) -> list[dict]:
        return parse_campsite_calendar(
            load_fixture("reserve_america_calendar.html"), ARRIVAL
        )

    def test_parses_every_site_row(self, sites: list[dict]) -> None:
        assert len(sites) == 4
        assert {s["name"] for s in sites} == {
            "Cabin 1", "Cabin 2", "Tent Site 14", "Camping Cabin 7",
        }

    def test_extracts_site_id_from_detail_link(self, sites: list[dict]) -> None:
        cabin = next(s for s in sites if s["name"] == "Cabin 1")
        assert cabin["site_id"] == "91001"

    def test_reads_dates_from_the_header_row(self, sites: list[dict]) -> None:
        cabin = next(s for s in sites if s["name"] == "Cabin 1")
        assert set(cabin["nights"]) == {
            date(2026, 9, 4), date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7),
        }

    def test_available_and_blocked_nights(self, sites: list[dict]) -> None:
        cabin = next(s for s in sites if s["name"] == "Cabin 2")
        assert cabin["nights"][date(2026, 9, 4)] is True
        assert cabin["nights"][date(2026, 9, 5)] is False  # class="status r"

    def test_fully_blocked_site(self, sites: list[dict]) -> None:
        cabin = next(s for s in sites if s["name"] == "Camping Cabin 7")
        assert not any(cabin["nights"].values())

    def test_rate_is_extracted(self, sites: list[dict]) -> None:
        assert next(s for s in sites if s["name"] == "Cabin 1")["rate"] == 95.0

    def test_missing_table_raises(self) -> None:
        with pytest.raises(ProviderError):
            parse_campsite_calendar("<html><body>down for maintenance</body></html>",
                                    ARRIVAL)

    def test_year_rollover_in_header(self) -> None:
        """A December search whose grid runs into January must not go backwards."""
        html = """
        <table id="calendar">
          <tr class="tbl_head"><th>Site</th>
            <th>Wed<br/>Dec 30</th><th>Fri<br/>Jan 1</th></tr>
          <tr><td class="sn"><a href="campsiteDetails.do?siteId=1">Cabin 9</a></td>
              <td class="status a">A</td><td class="status a">A</td></tr>
        </table>
        """
        sites = parse_campsite_calendar(html, date(2026, 12, 30))
        assert date(2026, 12, 30) in sites[0]["nights"]
        assert date(2027, 1, 1) in sites[0]["nights"]

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Cabin 1", True),
            ("Camping Cabin 7", True),
            ("Lakeside Cottage", True),
            ("Yurt 3", True),
            ("Vogel Lodge", True),
            ("Tent Site 14", False),
            ("RV Site 22", False),
            ("Group Camp", False),
        ],
    )
    def test_cabin_classifier(self, name: str, expected: bool) -> None:
        assert looks_like_cabin(name) is expected


# ---------------------------------------------------------------------------
# UseDirect (VA)
# ---------------------------------------------------------------------------
class TestUseDirect:
    @pytest.fixture
    def units(self) -> list[dict]:
        return parse_availability(
            load_json_fixture("usedirect_availability.json"),
            ARRIVAL,
            ARRIVAL + timedelta(days=3),
        )

    def test_all_units_parsed(self, units: list[dict]) -> None:
        assert {u["name"] for u in units} == {"Cabin 3", "Cabin 4", "Campsite 22"}

    def test_fully_free_unit_is_available(self, units: list[dict]) -> None:
        assert next(u for u in units if u["name"] == "Cabin 3")["available"] is True

    def test_one_blocked_night_makes_the_stay_unavailable(
        self, units: list[dict]
    ) -> None:
        assert next(u for u in units if u["name"] == "Cabin 4")["available"] is False

    def test_rate_and_capacity(self, units: list[dict]) -> None:
        cabin = next(u for u in units if u["name"] == "Cabin 3")
        assert cabin["rate"] == 132.0
        assert cabin["sleeps"] == 6

    def test_facility_coordinates_are_attached(self, units: list[dict]) -> None:
        assert units[0]["latitude"] == 37.894

    def test_units_missing_a_night_are_skipped(self) -> None:
        """A short window must not be silently treated as available."""
        payload = load_json_fixture("usedirect_availability.json")
        units = parse_availability(payload, ARRIVAL, ARRIVAL + timedelta(days=5))
        assert units == []

    def test_handles_units_as_a_list(self) -> None:
        payload = {
            "Facility": {
                "FacilityId": 9,
                "Units": [
                    {
                        "UnitId": 1,
                        "Name": "Cabin A",
                        "Slices": [
                            {"Date": "2026-09-04T00:00:00", "IsFree": True},
                            {"Date": "2026-09-05T00:00:00", "IsFree": True},
                        ],
                    }
                ],
            }
        }
        units = parse_availability(payload, ARRIVAL, ARRIVAL + timedelta(days=2))
        assert units[0]["available"] is True


# ---------------------------------------------------------------------------
# Aspira Connect (MD)
# ---------------------------------------------------------------------------
class TestAspiraConnect:
    @pytest.fixture
    def resources(self) -> list[dict]:
        return parse_map_availability(
            load_json_fixture("aspira_map_availability.json"),
            ARRIVAL,
            ARRIVAL + timedelta(days=3),
        )

    def test_zero_means_available(self, resources: list[dict]) -> None:
        """The counter-intuitive core of this API."""
        assert next(r for r in resources if r["resource_id"] == "2001")["available"]

    def test_any_nonzero_night_blocks_the_stay(self, resources: list[dict]) -> None:
        blocked = next(r for r in resources if r["resource_id"] == "2002")
        assert not blocked["available"]

    def test_fully_blocked_resource(self, resources: list[dict]) -> None:
        assert not next(r for r in resources if r["resource_id"] == "2003")["available"]

    def test_rate_averaged_across_nights(self, resources: list[dict]) -> None:
        assert next(r for r in resources if r["resource_id"] == "2001")["rate"] == 110.0

    def test_short_response_is_refused(self) -> None:
        payload = load_json_fixture("aspira_map_availability.json")
        assert parse_map_availability(
            payload, ARRIVAL, ARRIVAL + timedelta(days=9)
        ) == []

    def test_flattens_map_keyed_responses(self) -> None:
        nested = {"resourceAvailabilities": {"77": {"2001": [{"availability": 0}]}}}
        flattened = flatten_nested_availabilities(nested)
        assert flattened["resourceAvailabilities"] == {"2001": [{"availability": 0}]}

    def test_flatten_is_a_noop_for_flat_responses(self) -> None:
        flat = load_json_fixture("aspira_map_availability.json")
        assert flatten_nested_availabilities(flat)["resourceAvailabilities"].keys() == {
            "2001", "2002", "2003"
        }


# ---------------------------------------------------------------------------
# Itinio (SC, TN)
# ---------------------------------------------------------------------------
class TestItinio:
    def test_boolean_available_flag(self) -> None:
        payload = {"units": [{"id": 5, "name": "Cabin 5", "available": True,
                              "rate": 150, "sleeps": 6}]}
        units = parse_availability_json(payload, ARRIVAL, ARRIVAL + timedelta(days=2))
        assert units[0]["available"] is True
        assert units[0]["rate"] == 150.0

    def test_per_night_list(self) -> None:
        payload = {"units": [{"id": 6, "name": "Cabin 6", "nights": [
            {"available": True}, {"available": False}]}]}
        units = parse_availability_json(payload, ARRIVAL, ARRIVAL + timedelta(days=2))
        assert units[0]["available"] is False

    def test_units_without_availability_info_are_dropped(self) -> None:
        payload = {"units": [{"id": 7, "name": "Cabin 7"}]}
        units = parse_availability_json(payload, ARRIVAL, ARRIVAL + timedelta(days=2))
        assert units == []

    def test_bare_list_payload(self) -> None:
        payload = [{"id": 8, "name": "Cabin 8", "isAvailable": True}]
        units = parse_availability_json(payload, ARRIVAL, ARRIVAL + timedelta(days=2))
        assert len(units) == 1

    def test_inventory_scrape(self) -> None:
        html = """
        <div class="cabin"><h3>Lakeside Cabin 2</h3>
          <p>Sleeps 6 - 2 bedroom - from $155.00 per night</p>
          <a href="/standing-stone/cabins/2">Details</a></div>
        <div class="cabin"><h3>Rustic Cabin 4</h3>
          <p>Sleeps 4 - 1 bedroom - from $120.00 per night</p></div>
        """
        cabins = parse_cabin_listing_html(html)
        assert [c["name"] for c in cabins] == ["Lakeside Cabin 2", "Rustic Cabin 4"]
        assert cabins[0]["sleeps"] == 6
        assert cabins[0]["bedrooms"] == 2
        assert cabins[0]["rate"] == 155.0
