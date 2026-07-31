"""Provider registry.

The application asks this module for providers by state code and never imports
a concrete provider directly -- that is what keeps the reservation platform an
implementation detail.
"""

from __future__ import annotations

from collections.abc import Iterable

from state_parks.config import settings
from state_parks.providers.base import (
    HttpStateProvider,
    NotVerifiedError,
    ProviderError,
    StateProvider,
)
from state_parks.providers.delaware import DelawareProvider
from state_parks.providers.georgia import GeorgiaProvider
from state_parks.providers.maryland import MarylandProvider
from state_parks.providers.north_carolina import NorthCarolinaProvider
from state_parks.providers.south_carolina import SouthCarolinaProvider
from state_parks.providers.tennessee import TennesseeProvider
from state_parks.providers.virginia import VirginiaProvider

#: Declared in the implementation order requested for this project.
PROVIDER_CLASSES: dict[str, type[StateProvider]] = {
    "NC": NorthCarolinaProvider,
    "SC": SouthCarolinaProvider,
    "VA": VirginiaProvider,
    "GA": GeorgiaProvider,
    "TN": TennesseeProvider,
    "DE": DelawareProvider,
    "MD": MarylandProvider,
}


def get_provider(state: str) -> StateProvider:
    """Instantiate the provider for a state code (case-insensitive)."""
    try:
        return PROVIDER_CLASSES[state.upper()]()
    except KeyError as exc:
        raise KeyError(
            f"No provider for {state!r}. Known: {sorted(PROVIDER_CLASSES)}"
        ) from exc


def all_providers(states: Iterable[str] | None = None) -> list[StateProvider]:
    """Instantiate every enabled provider, or a specific subset."""
    codes = list(states) if states is not None else settings.enabled_providers
    return [get_provider(code) for code in codes if code.upper() in PROVIDER_CLASSES]


__all__ = [
    "DelawareProvider",
    "GeorgiaProvider",
    "HttpStateProvider",
    "MarylandProvider",
    "NorthCarolinaProvider",
    "NotVerifiedError",
    "PROVIDER_CLASSES",
    "ProviderError",
    "SouthCarolinaProvider",
    "StateProvider",
    "TennesseeProvider",
    "VirginiaProvider",
    "all_providers",
    "get_provider",
]
