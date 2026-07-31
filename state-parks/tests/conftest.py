"""Shared test fixtures."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from state_parks.database import Repository, connect, init_db
from state_parks.models import Cabin

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def load_json_fixture(name: str) -> dict:
    return json.loads(load_fixture(name))


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def repo(conn: sqlite3.Connection) -> Repository:
    return Repository(conn)


@pytest.fixture
def arrival() -> date:
    return date(2026, 9, 4)


@pytest.fixture
def departure(arrival: date) -> date:
    return arrival + timedelta(days=2)


def make_cabin(**overrides) -> Cabin:
    """A valid Cabin with sensible defaults, for terse tests."""
    base = {
        "state": "NC",
        "park": "Morrow Mountain State Park",
        "park_id": "3234",
        "cabin_name": "Cabin 1",
        "cabin_id": "91001",
        "arrival": date(2026, 9, 4),
        "departure": date(2026, 9, 6),
        "available": True,
        "nightly_rate": 95.0,
        "sleeps": 6,
        "pet_friendly": False,
        "waterfront": False,
        "reservation_url": "https://example.invalid/cabin/91001",
        "provider": "NC",
    }
    base.update(overrides)
    return Cabin(**base)
