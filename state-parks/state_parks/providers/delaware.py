"""Delaware State Parks.

Platform: ReserveAmerica (``delawarestateparks.reserveamerica.com``,
``contractCode=DE``). Delaware has used Aspira for camping reservations, point
of sale and ticketing for years; the camping side is still the ReserveAmerica
product, not Aspira Connect.

Inventory is genuinely small: cabins and cottages exist at a handful of parks,
mostly coastal.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import ReserveAmericaProvider


class DelawareProvider(ReserveAmericaProvider):
    state: ClassVar[str] = "DE"
    base_url: ClassVar[str] = "https://delawarestateparks.reserveamerica.com"
    contract_code: ClassVar[str] = "DE"

    park_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "parkId": "471",
            "name": "Cape Henlopen State Park",
            "latitude": 38.7920,
            "longitude": -75.0930,
            "sleeps": 4,
            "waterfront": True,
            "pet_friendly": False,
        },
        {
            "parkId": "472",
            "name": "Delaware Seashore State Park",
            "latitude": 38.6180,
            "longitude": -75.0640,
            "sleeps": 4,
            "waterfront": True,
            "pet_friendly": False,
        },
        {
            "parkId": "473",
            "name": "Trap Pond State Park",
            "latitude": 38.5250,
            "longitude": -75.4790,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "parkId": "474",
            "name": "Killens Pond State Park",
            "latitude": 38.9930,
            "longitude": -75.5410,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
    ]
