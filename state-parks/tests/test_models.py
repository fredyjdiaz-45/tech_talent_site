"""Tests for the normalized models."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from state_parks.models import SearchQuery
from tests.conftest import make_cabin


def test_nights_and_total_rate() -> None:
    cabin = make_cabin(arrival=date(2026, 9, 4), departure=date(2026, 9, 7),
                       nightly_rate=95.0)
    assert cabin.nights == 3
    assert cabin.total_rate == 285.0


def test_total_rate_is_none_without_a_rate() -> None:
    assert make_cabin(nightly_rate=None).total_rate is None


def test_departure_must_follow_arrival() -> None:
    with pytest.raises(ValidationError):
        make_cabin(arrival=date(2026, 9, 6), departure=date(2026, 9, 4))


def test_same_day_stay_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_cabin(arrival=date(2026, 9, 4), departure=date(2026, 9, 4))


def test_state_is_normalized() -> None:
    assert make_cabin(state=" nc ").state == "NC"


def test_unit_key_is_stable_across_date_windows() -> None:
    a = make_cabin(arrival=date(2026, 9, 4), departure=date(2026, 9, 6))
    b = make_cabin(arrival=date(2026, 10, 2), departure=date(2026, 10, 4))
    assert a.unit_key == b.unit_key


def test_cabin_is_hashable_and_frozen() -> None:
    cabin = make_cabin()
    assert {cabin, make_cabin()}  # frozen models are hashable
    with pytest.raises(ValidationError):
        cabin.cabin_name = "changed"


def test_search_query_rejects_backwards_range() -> None:
    with pytest.raises(ValidationError):
        SearchQuery(arrival=date(2026, 9, 6), departure=date(2026, 9, 4))


def test_search_query_nights() -> None:
    query = SearchQuery(arrival=date(2026, 9, 4), departure=date(2026, 9, 6))
    assert query.nights == 2
