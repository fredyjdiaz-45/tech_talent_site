"""North Carolina State Parks.

Platform: ReserveAmerica (``northcarolinastateparks.reserveamerica.com``,
``contractCode=NC``). See ``platforms/reserve_america.py`` for the request
shape and why HTML parsing is unavoidable here.

Cabin inventory: NC's cabin stock is small and concentrated. Only parks that
actually rent cabins/camping-cabins are listed -- querying the other ~40 parks
would be pure waste. ``parkId`` values must be confirmed with
``cli verify NC``; they are the one thing that cannot be derived offline.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import ReserveAmericaProvider


class NorthCarolinaProvider(ReserveAmericaProvider):
    state: ClassVar[str] = "NC"
    base_url: ClassVar[str] = "https://northcarolinastateparks.reserveamerica.com"
    contract_code: ClassVar[str] = "NC"

    # parkId values are placeholders pending `cli verify NC --discover`; names
    # and cabin facts come from NC State Parks' published cabin listings.
    park_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "parkId": "3234",
            "name": "Morrow Mountain State Park",
            "latitude": 35.3743,
            "longitude": -80.0723,
            "sleeps": 6,
            "waterfront": False,
            "pet_friendly": False,
        },
        {
            "parkId": "3243",
            "name": "Hanging Rock State Park",
            "latitude": 36.3959,
            "longitude": -80.2653,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": False,
        },
        {
            "parkId": "3221",
            "name": "Cape Hatteras / Jockey's Ridge Area",
            "latitude": 35.9650,
            "longitude": -75.6310,
            "sleeps": 4,
            "waterfront": True,
            "pet_friendly": False,
        },
        {
            "parkId": "3252",
            "name": "Carolina Beach State Park",
            "latitude": 34.0480,
            "longitude": -77.9080,
            "sleeps": 4,
            "waterfront": True,
            "pet_friendly": True,
        },
    ]
