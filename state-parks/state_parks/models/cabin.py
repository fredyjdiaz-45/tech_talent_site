"""Normalized data models shared by every provider.

Nothing outside ``state_parks.providers`` should ever need to know which
reservation platform a record originated from -- providers are responsible for
translating their platform's vocabulary into the models below.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class State(StrEnum):
    """States covered by this aggregator, keyed by USPS code."""

    NC = "NC"
    SC = "SC"
    VA = "VA"
    GA = "GA"
    TN = "TN"
    DE = "DE"
    MD = "MD"

    @property
    def label(self) -> str:
        return _STATE_LABELS[self]


_STATE_LABELS: dict[State, str] = {
    State.NC: "North Carolina",
    State.SC: "South Carolina",
    State.VA: "Virginia",
    State.GA: "Georgia",
    State.TN: "Tennessee",
    State.DE: "Delaware",
    State.MD: "Maryland",
}


class Cabin(BaseModel):
    """A cabin as offered for a specific arrival/departure window.

    One ``Cabin`` is a *stay quote*, not a physical building: the same physical
    cabin searched for two different date ranges produces two instances. The
    physical unit is identified by ``(state, park, cabin_id)``.
    """

    model_config = ConfigDict(frozen=True)

    state: str
    park: str
    cabin_name: str
    cabin_id: str | None = None
    arrival: date
    departure: date
    available: bool
    nightly_rate: float | None = None
    sleeps: int | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    pet_friendly: bool | None = None
    waterfront: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    reservation_url: str

    # Provenance -- not in the original sketch, but needed so the refresh
    # service can attribute rows to a provider and expire stale ones.
    provider: str | None = None
    park_id: str | None = None
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this quote was collected from the upstream platform.",
    )

    @model_validator(mode="after")
    def _check_dates(self) -> Cabin:
        if self.departure <= self.arrival:
            raise ValueError(
                f"departure ({self.departure}) must be after arrival ({self.arrival})"
            )
        return self

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days

    @property
    def total_rate(self) -> float | None:
        """Best-effort total for the stay.

        Platforms differ wildly in whether they quote nightly or total, and
        almost none of them include taxes/fees in a search response. Treat this
        as an estimate for ranking, never as a price to show as final.
        """
        if self.nightly_rate is None:
            return None
        return round(self.nightly_rate * self.nights, 2)

    @property
    def unit_key(self) -> str:
        """Stable identity for the physical cabin across searches."""
        unit = self.cabin_id or self.cabin_name
        return f"{self.state}:{self.park_id or self.park}:{unit}"


class Park(BaseModel):
    """A park (or historic site / lodge) that owns cabins."""

    model_config = ConfigDict(frozen=True)

    state: str
    park_id: str
    name: str
    provider: str
    latitude: float | None = None
    longitude: float | None = None
    url: str | None = None
    # Platform-specific identifiers the provider needs to build requests
    # (contract codes, map ids, place ids...). Persisted as JSON.
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchQuery(BaseModel):
    """Normalized search input accepted by every provider."""

    arrival: date
    departure: date
    guests: int = 2
    pets: bool = False
    states: list[str] | None = None
    park: str | None = None
    sleeps: int | None = None
    waterfront: bool | None = None
    available_only: bool = True

    @model_validator(mode="after")
    def _check_dates(self) -> SearchQuery:
        if self.departure <= self.arrival:
            raise ValueError("departure must be after arrival")
        return self

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days


class ProviderStatus(BaseModel):
    """Health/verification state of a provider, surfaced through the API.

    ``wire_format_verified`` is deliberately explicit: several platforms in this
    project were identified with confidence, but their request/response shapes
    could not be captured from the build environment. See docs/PLATFORMS.md.
    """

    name: str
    state: str
    platform: str
    wire_format_verified: bool
    enabled: bool = True
    last_refresh: datetime | None = None
    last_error: str | None = None
    cabins_tracked: int = 0
