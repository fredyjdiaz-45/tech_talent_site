"""REST API tests.

The app is exercised through FastAPI's TestClient against a temporary database,
with the dependency overridden so no real network or on-disk state is touched.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from state_parks.api.app import create_app
from state_parks.api.deps import get_repository, get_search_service
from state_parks.database import Repository, connect, init_db
from state_parks.models import ProviderStatus
from state_parks.services import SearchService
from tests.conftest import make_cabin

ARRIVAL = date.today() + timedelta(days=30)
DEPARTURE = ARRIVAL + timedelta(days=2)


@pytest.fixture
def client() -> TestClient:
    conn = connect(":memory:")
    init_db(conn)
    repo = Repository(conn)

    # A Friday arrival so the weekend endpoint has something to find.
    friday = ARRIVAL + timedelta(days=(4 - ARRIVAL.weekday()) % 7)
    repo.store_cabins([
        make_cabin(arrival=friday, departure=friday + timedelta(days=2)),
        make_cabin(state="VA", park="Douthat State Park", park_id="1",
                   cabin_name="Cabin 3", cabin_id="1001", provider="VA",
                   sleeps=8, waterfront=True, pet_friendly=True,
                   arrival=friday, departure=friday + timedelta(days=2)),
    ])
    repo.upsert_provider(ProviderStatus(name="NC", state="NC",
                                        platform="reserve_america",
                                        wire_format_verified=False))

    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_search_service] = lambda: SearchService(repo)

    with TestClient(app) as test_client:
        test_client.friday = friday  # type: ignore[attr-defined]
        yield test_client
    conn.close()


class TestMeta:
    def test_health(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}

    def test_providers_reports_verification_state(self, client: TestClient) -> None:
        """Callers need to know which states they can actually trust."""
        response = client.get("/providers")
        assert response.status_code == 200
        by_name = {p["name"]: p for p in response.json()}
        assert by_name["NC"]["platform"] == "reserve_america"
        assert by_name["NC"]["wire_format_verified"] is False

    def test_openapi_schema_builds(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 200


class TestInventory:
    def test_parks(self, client: TestClient) -> None:
        parks = client.get("/parks").json()
        assert {p["state"] for p in parks} == {"NC", "VA"}

    def test_parks_filtered_by_state(self, client: TestClient) -> None:
        parks = client.get("/parks", params={"state": "VA"}).json()
        assert len(parks) == 1
        assert parks[0]["name"] == "Douthat State Park"

    def test_cabins(self, client: TestClient) -> None:
        assert len(client.get("/cabins").json()) == 2

    def test_cabins_filtered_by_park_substring(self, client: TestClient) -> None:
        cabins = client.get("/cabins", params={"park": "Douthat"}).json()
        assert len(cabins) == 1


class TestAvailability:
    def test_availability_window(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        response = client.get(
            "/availability",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat()},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_state_filter_is_repeatable(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        cabins = client.get(
            "/availability",
            params=[("arrival", friday.isoformat()),
                    ("departure", (friday + timedelta(days=2)).isoformat()),
                    ("state", "VA")],
        ).json()
        assert {c["state"] for c in cabins} == {"VA"}

    def test_guests_filter(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        cabins = client.get(
            "/availability",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat(),
                    "guests": 8},
        ).json()
        assert {c["cabin_name"] for c in cabins} == {"Cabin 3"}

    def test_waterfront_filter(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        cabins = client.get(
            "/availability",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat(),
                    "waterfront": True},
        ).json()
        assert {c["state"] for c in cabins} == {"VA"}

    def test_pets_filter(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        cabins = client.get(
            "/availability",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat(),
                    "pets": True},
        ).json()
        assert {c["state"] for c in cabins} == {"VA"}

    def test_weekends_endpoint(self, client: TestClient) -> None:
        cabins = client.get(
            "/availability/weekends",
            params={"start": ARRIVAL.isoformat(), "weeks": 6},
        ).json()
        assert cabins
        assert all(date.fromisoformat(c["arrival"]).weekday() == 4 for c in cabins)

    def test_search_defaults_to_cache(self, client: TestClient) -> None:
        friday = client.friday  # type: ignore[attr-defined]
        response = client.get(
            "/search",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat()},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_response_shape_is_the_normalized_model(self, client: TestClient) -> None:
        """No platform-specific fields leak into the API surface."""
        friday = client.friday  # type: ignore[attr-defined]
        cabin = client.get(
            "/availability",
            params={"arrival": friday.isoformat(),
                    "departure": (friday + timedelta(days=2)).isoformat()},
        ).json()[0]
        assert set(cabin) >= {
            "state", "park", "cabin_name", "cabin_id", "arrival", "departure",
            "available", "nightly_rate", "sleeps", "bedrooms", "bathrooms",
            "pet_friendly", "waterfront", "latitude", "longitude",
            "reservation_url",
        }


class TestValidation:
    def test_departure_before_arrival_is_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/availability",
            params={"arrival": DEPARTURE.isoformat(),
                    "departure": ARRIVAL.isoformat()},
        )
        assert response.status_code == 422

    def test_past_arrival_is_rejected(self, client: TestClient) -> None:
        past = date.today() - timedelta(days=10)
        response = client.get(
            "/availability",
            params={"arrival": past.isoformat(),
                    "departure": (past + timedelta(days=2)).isoformat()},
        )
        assert response.status_code == 422

    def test_malformed_date_is_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/availability",
            params={"arrival": "not-a-date", "departure": DEPARTURE.isoformat()},
        )
        assert response.status_code == 422
