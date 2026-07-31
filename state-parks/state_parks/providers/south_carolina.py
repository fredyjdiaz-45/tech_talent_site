"""South Carolina State Parks.

Platform: Itinio (``reserve.southcarolinaparks.com``). Same product as
Tennessee -- see ``platforms/itinio.py``, including the important caveat that
the availability endpoint has not been captured yet, so this provider is
disabled by default and ``search_cabins`` raises ``NotVerifiedError`` until
``availability_path`` is filled in.

SC advertises 220+ cabins and villas, so it is worth finishing: the park slugs
below are taken from the site's public ``/<slug>`` URLs, which means the
inventory scrape (``list_cabins``) works today even though availability does not.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import ItinioProvider


class SouthCarolinaProvider(ItinioProvider):
    state: ClassVar[str] = "SC"
    base_url: ClassVar[str] = "https://reserve.southcarolinaparks.com"

    park_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "slug": "edisto-beach",
            "name": "Edisto Beach State Park",
            "latitude": 32.5090,
            "longitude": -80.3000,
            "waterfront": True,
        },
        {
            "slug": "hunting-island",
            "name": "Hunting Island State Park",
            "latitude": 32.3750,
            "longitude": -80.4380,
            "waterfront": True,
        },
        {
            "slug": "devils-fork",
            "name": "Devils Fork State Park",
            "latitude": 34.9520,
            "longitude": -82.9450,
            "waterfront": True,
        },
        {
            "slug": "keowee-toxaway",
            "name": "Keowee-Toxaway State Park",
            "latitude": 34.9310,
            "longitude": -82.8850,
            "waterfront": True,
        },
        {
            "slug": "santee",
            "name": "Santee State Park",
            "latitude": 33.5350,
            "longitude": -80.4880,
            "waterfront": True,
        },
        {
            "slug": "dreher-island",
            "name": "Dreher Island State Park",
            "latitude": 34.0870,
            "longitude": -81.4130,
            "waterfront": True,
        },
    ]
