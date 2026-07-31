"""Reservation-platform adapters.

Four platforms cover all seven states, which is the whole reason the provider
layer is split this way:

    reserve_america  -> NC, GA, DE   (HTML; no JSON API exists)
    itinio           -> SC, TN       (wire format not yet captured)
    usedirect        -> VA           (JSON)
    aspira_connect   -> MD           (JSON)
"""

from state_parks.providers.platforms.aspira_connect import AspiraConnectProvider
from state_parks.providers.platforms.itinio import ItinioProvider
from state_parks.providers.platforms.reserve_america import ReserveAmericaProvider
from state_parks.providers.platforms.usedirect import UseDirectProvider

__all__ = [
    "AspiraConnectProvider",
    "ItinioProvider",
    "ReserveAmericaProvider",
    "UseDirectProvider",
]
