"""Storage and query tests.

The interesting behaviour here is the per-night model: providers hand over stay
quotes, storage fans them out to nights, and arbitrary windows are reconstructed
in SQL. These tests pin that round trip.
"""

from __future__ import annotations

from datetime import date, timedelta

from state_parks.database import Repository, nights_between
from state_parks.models import ProviderStatus
from tests.conftest import make_cabin

ARRIVAL = date(2026, 9, 4)


def test_nights_between_excludes_departure() -> None:
    assert nights_between(date(2026, 9, 4), date(2026, 9, 6)) == [
        date(2026, 9, 4),
        date(2026, 9, 5),
    ]


def test_store_expands_a_stay_into_nights(repo: Repository) -> None:
    written = repo.store_cabins([make_cabin(arrival=ARRIVAL,
                                            departure=ARRIVAL + timedelta(days=3))])
    assert written == 3


def test_unavailable_quote_only_marks_the_arrival_night(repo: Repository) -> None:
    """An unavailable window says nothing definite about its later nights."""
    written = repo.store_cabins([
        make_cabin(available=False, arrival=ARRIVAL,
                   departure=ARRIVAL + timedelta(days=3))
    ])
    assert written == 1


def test_round_trip_search_finds_the_stay(repo: Repository) -> None:
    repo.store_cabins([make_cabin()])
    found = repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2))
    assert len(found) == 1
    assert found[0].cabin_name == "Cabin 1"
    assert found[0].park == "Morrow Mountain State Park"


def test_search_requires_every_night_available(repo: Repository) -> None:
    """Two separate 1-night quotes with a gap must not satisfy a 3-night stay."""
    repo.store_cabins([
        make_cabin(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=1)),
        make_cabin(arrival=ARRIVAL + timedelta(days=2),
                   departure=ARRIVAL + timedelta(days=3)),
    ])
    assert repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=3)) == []


def test_search_spans_windows_stored_separately(repo: Repository) -> None:
    """Adjacent quotes stitch together into a longer bookable stay."""
    repo.store_cabins([
        make_cabin(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2)),
        make_cabin(arrival=ARRIVAL + timedelta(days=2),
                   departure=ARRIVAL + timedelta(days=4)),
    ])
    found = repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=4))
    assert len(found) == 1


def test_state_filter(repo: Repository) -> None:
    repo.store_cabins([make_cabin(), make_cabin(state="VA", park="Douthat",
                                                park_id="1", cabin_id="7")])
    assert len(repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                           states=["VA"])) == 1


def test_sleeps_filter_keeps_unknown_capacity(repo: Repository) -> None:
    """Unknown capacity is not the same as too small -- keep those rows."""
    repo.store_cabins([
        make_cabin(cabin_id="known", sleeps=4),
        make_cabin(cabin_id="unknown", sleeps=None),
    ])
    found = repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                        sleeps=6)
    assert {c.cabin_id for c in found} == {"unknown"}


def test_pets_filter(repo: Repository) -> None:
    repo.store_cabins([
        make_cabin(cabin_id="nopets", pet_friendly=False),
        make_cabin(cabin_id="pets", pet_friendly=True),
    ])
    found = repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                        pets=True)
    assert {c.cabin_id for c in found} == {"pets"}


def test_waterfront_filter(repo: Repository) -> None:
    repo.store_cabins([
        make_cabin(cabin_id="water", waterfront=True),
        make_cabin(cabin_id="inland", waterfront=False),
    ])
    found = repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                        waterfront=True)
    assert {c.cabin_id for c in found} == {"water"}


def test_park_substring_filter(repo: Repository) -> None:
    repo.store_cabins([make_cabin()])
    assert repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                       park="Morrow")
    assert not repo.search(arrival=ARRIVAL, departure=ARRIVAL + timedelta(days=2),
                           park="Hanging Rock")


def test_upsert_preserves_detail_when_a_thin_row_arrives(repo: Repository) -> None:
    """A later search response without `sleeps` must not erase what we knew."""
    repo.store_cabins([make_cabin(sleeps=6, bedrooms=2)])
    repo.store_cabins([make_cabin(sleeps=None, bedrooms=None)])
    cabins = repo.list_cabins()
    assert cabins[0].sleeps == 6
    assert cabins[0].bedrooms == 2


def test_reupsert_does_not_duplicate(repo: Repository) -> None:
    repo.store_cabins([make_cabin()])
    repo.store_cabins([make_cabin()])
    assert len(repo.list_cabins()) == 1
    assert len(repo.list_parks()) == 1


def test_weekend_search_returns_only_fri_to_sun(repo: Repository) -> None:
    friday = date(2026, 9, 4)  # a Friday
    assert friday.weekday() == 4
    repo.store_cabins([make_cabin(arrival=friday,
                                  departure=friday + timedelta(days=2))])
    found = repo.weekend_search(start=friday - timedelta(days=3),
                                end=friday + timedelta(days=14))
    assert len(found) == 1
    assert found[0].arrival == friday


def test_stale_windows_filters_out_fresh_ones(repo: Repository) -> None:
    repo.upsert_provider(ProviderStatus(name="NC", state="NC",
                                        platform="reserve_america",
                                        wire_format_verified=False))
    windows = [(ARRIVAL, ARRIVAL + timedelta(days=30)),
               (ARRIVAL + timedelta(days=30), ARRIVAL + timedelta(days=60))]
    assert repo.stale_windows("NC", windows, 24) == windows

    repo.log_refresh("NC", *windows[0])
    assert repo.stale_windows("NC", windows, 24) == [windows[1]]


def test_failed_windows_stay_stale(repo: Repository) -> None:
    repo.upsert_provider(ProviderStatus(name="NC", state="NC",
                                        platform="reserve_america",
                                        wire_format_verified=False))
    window = (ARRIVAL, ARRIVAL + timedelta(days=30))
    repo.log_refresh("NC", *window, ok=False, error="boom")
    assert repo.stale_windows("NC", [window], 24) == [window]


def test_provider_status_round_trip(repo: Repository) -> None:
    repo.upsert_provider(ProviderStatus(name="VA", state="VA", platform="usedirect",
                                        wire_format_verified=True))
    repo.mark_refresh("VA")
    statuses = repo.list_providers()
    assert statuses[0].name == "VA"
    assert statuses[0].wire_format_verified is True
    assert statuses[0].last_refresh is not None
