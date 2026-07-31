"""Maryland Park Service.

Platform: Aspira Connect (the GoingToCamp SPA product), launched February 2026
at ``https://parkreservations.maryland.gov``. 37 parks with campsites, cabins,
mini-cabins and pavilions moved onto it.

Because the system is new, none of Maryland's ``resourceLocationId`` / ``mapId``
values appear anywhere public, and they could not be fetched here. The catalog
is therefore intentionally empty: run

    python -m state_parks.cli discover MD

which walks ``/api/resourceLocation`` and ``/api/maps`` and writes a populated
catalog. Everything else about this provider works the moment the catalog
exists -- see ``platforms/aspira_connect.py``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from state_parks.providers.platforms import AspiraConnectProvider


class MarylandProvider(AspiraConnectProvider):
    state: ClassVar[str] = "MD"
    base_url: ClassVar[str] = "https://parkreservations.maryland.gov"

    #: Overnight bookings. Confirm against /api/resourcecategory -- some
    #: deployments split cabins into their own booking category.
    booking_category_id: ClassVar[int] = 0

    #: Populated by `cli discover MD`. See module docstring.
    location_catalog: ClassVar[list[dict[str, Any]]] = []
