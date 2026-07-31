"""Georgia State Parks & Historic Sites.

Platform: ReserveAmerica (``gastateparks.reserveamerica.com``,
``contractCode=GA``). Identical wire format to North Carolina and Delaware --
this class is configuration only.

Georgia has the largest cabin inventory of the seven states (roughly 250
cottages across ~40 parks), so the catalog below is a starter set of the
best-known cottage parks rather than an exhaustive list. Extend it with
``cli discover GA`` once ``parkId`` values are confirmed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import ReserveAmericaProvider


class GeorgiaProvider(ReserveAmericaProvider):
    state: ClassVar[str] = "GA"
    base_url: ClassVar[str] = "https://gastateparks.reserveamerica.com"
    contract_code: ClassVar[str] = "GA"

    park_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "parkId": "343000",
            "name": "Amicalola Falls State Park",
            "latitude": 34.5620,
            "longitude": -84.2480,
            "sleeps": 8,
            "waterfront": False,
            "pet_friendly": True,
        },
        {
            "parkId": "343010",
            "name": "Vogel State Park",
            "latitude": 34.7660,
            "longitude": -83.9250,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "parkId": "343020",
            "name": "Unicoi State Park & Lodge",
            "latitude": 34.7230,
            "longitude": -83.7220,
            "sleeps": 8,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "parkId": "343030",
            "name": "Cloudland Canyon State Park",
            "latitude": 34.8390,
            "longitude": -85.4820,
            "sleeps": 8,
            "waterfront": False,
            "pet_friendly": True,
        },
        {
            "parkId": "343040",
            "name": "Fort Mountain State Park",
            "latitude": 34.7720,
            "longitude": -84.7000,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
    ]
