"""Virginia State Parks.

Platform: UseDirect / US eDirect. Virginia DCR migrated off ReserveAmerica; the
booking front end is ``https://reservevaparks.com/Web/``. This is the best
platform of the seven -- a real JSON API, no HTML parsing.

Virginia has the richest cabin inventory in the group (cabins, lodges and
camping cabins at ~25 parks), so this provider is worth getting right first
among the JSON platforms.

The one value that could not be confirmed offline is ``rdr_base_url``: UseDirect
deployments either serve ``/rdr/rdr/...`` from the booking host itself or from a
dedicated ``<state>rdr.usedirect.com`` host. Both are listed below; run
``cli verify VA`` to find out which answers, and delete the other.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import UseDirectProvider


class VirginiaProvider(UseDirectProvider):
    state: ClassVar[str] = "VA"
    base_url: ClassVar[str] = "https://reservevaparks.com"

    #: Primary guess: the booking host proxies the RDR service. The documented
    #: alternative for other UseDirect states is a separate host, e.g.
    #: "https://vardr.usedirect.com/VaWebRDR" -- try that if this 404s.
    rdr_base_url: ClassVar[str] = "https://reservevaparks.com"

    facility_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "facilityId": "1",
            "placeId": "1",
            "name": "Douthat State Park",
            "latitude": 37.8940,
            "longitude": -79.8000,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "facilityId": "2",
            "placeId": "2",
            "name": "Hungry Mother State Park",
            "latitude": 36.8770,
            "longitude": -81.5240,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "facilityId": "3",
            "placeId": "3",
            "name": "First Landing State Park",
            "latitude": 36.9180,
            "longitude": -76.0490,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "facilityId": "4",
            "placeId": "4",
            "name": "Westmoreland State Park",
            "latitude": 38.1620,
            "longitude": -76.8650,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
        {
            "facilityId": "5",
            "placeId": "5",
            "name": "Fairy Stone State Park",
            "latitude": 36.7860,
            "longitude": -80.1080,
            "sleeps": 6,
            "waterfront": True,
            "pet_friendly": True,
        },
    ]
