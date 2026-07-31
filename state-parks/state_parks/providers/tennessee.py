"""Tennessee State Parks.

Platform: Itinio (``reserve.tnstateparks.com``, also served as
``tsp.itinio.com``/``tspg.itinio.com`` -- which is how the vendor was
identified). Shares every line of transport logic with South Carolina.

Same caveat as SC: availability endpoint not yet captured, provider disabled by
default, inventory scraping works. See ``platforms/itinio.py``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import ItinioProvider


class TennesseeProvider(ItinioProvider):
    state: ClassVar[str] = "TN"
    base_url: ClassVar[str] = "https://reserve.tnstateparks.com"

    park_catalog: ClassVar[list[dict[str, Any]]] = [
        {
            "slug": "standing-stone",
            "name": "Standing Stone State Park",
            "latitude": 36.4640,
            "longitude": -85.4180,
            "waterfront": True,
        },
        {
            "slug": "cumberland-mountain",
            "name": "Cumberland Mountain State Park",
            "latitude": 35.8990,
            "longitude": -84.9950,
            "waterfront": True,
        },
        {
            "slug": "paris-landing",
            "name": "Paris Landing State Park",
            "latitude": 36.4370,
            "longitude": -88.0900,
            "waterfront": True,
        },
        {
            "slug": "rock-island",
            "name": "Rock Island State Park",
            "latitude": 35.8140,
            "longitude": -85.6390,
            "waterfront": True,
        },
        {
            "slug": "fall-creek-falls",
            "name": "Fall Creek Falls State Park",
            "latitude": 35.6600,
            "longitude": -85.3550,
            "waterfront": True,
        },
        {
            "slug": "montgomery-bell",
            "name": "Montgomery Bell State Park",
            "latitude": 36.0980,
            "longitude": -87.2760,
            "waterfront": True,
        },
    ]
