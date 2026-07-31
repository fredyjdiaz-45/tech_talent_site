"""Provider interface and shared HTTP plumbing.

Two layers live here:

``StateProvider``
    The contract every state implements. The rest of the application only ever
    sees this.

``HttpStateProvider``
    A base class adding a polite, retrying ``httpx`` client. Platform adapters
    (``state_parks.providers.platforms``) build on it; concrete states then
    subclass a platform adapter and supply configuration only.

Design intent: a new state should be ~40 lines of configuration if it runs on a
platform we already speak, and a new *platform adapter* only when it does not.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random
from datetime import date
from typing import Any, ClassVar

import httpx

from state_parks.config import settings
from state_parks.models import Cabin, Park, ProviderStatus

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request against its platform."""


class NotVerifiedError(ProviderError):
    """Raised when a provider's wire format has not been confirmed.

    Providers whose request/response shape could not be captured are shipped
    with ``wire_format_verified = False``. They stay callable -- so ``verify``
    can exercise them -- but the refresh service skips them by default rather
    than filling the database with rows parsed by an unproven parser.
    """


class StateProvider(abc.ABC):
    """Common interface implemented by every state."""

    #: USPS code, e.g. "NC".
    state: ClassVar[str]
    #: Human name of the reservation platform, e.g. "reserve_america".
    platform: ClassVar[str] = "unknown"
    #: Whether the request/response shape has been confirmed against the live
    #: site. See docs/PLATFORMS.md for what was and was not verifiable.
    wire_format_verified: ClassVar[bool] = False
    #: Public booking site, used for building reservation URLs.
    base_url: ClassVar[str] = ""

    @property
    def name(self) -> str:
        return self.state

    @abc.abstractmethod
    async def search_cabins(
        self,
        start_date: date,
        end_date: date,
        guests: int,
        pets: bool = False,
    ) -> list[Cabin]:
        """Return cabin quotes for the window, normalized to ``Cabin``."""

    async def list_parks(self) -> list[Park]:
        """Parks known to offer cabins. Defaults to the static catalog."""
        return []

    async def verify(self) -> dict[str, Any]:
        """Probe the upstream platform and report what was observed.

        Used by ``python -m state_parks.cli verify`` so wire formats that could
        not be captured during development can be confirmed -- or corrected --
        from a machine with unrestricted network access.
        """
        return {
            "provider": self.name,
            "platform": self.platform,
            "verified_in_repo": self.wire_format_verified,
            "checks": [],
        }

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            state=self.state,
            platform=self.platform,
            wire_format_verified=self.wire_format_verified,
        )

    async def aclose(self) -> None:  # pragma: no cover - overridden where needed
        return None


class HttpStateProvider(StateProvider):
    """``StateProvider`` with a shared, rate-limited HTTP client.

    Every one of these systems is run by a small public agency. The client is
    deliberately conservative: one in-flight request per provider, a delay
    between requests, and retries only on transient failures (never on a 4xx,
    which means we are asking wrongly and should fix the code instead).
    """

    #: Sent on every request. Some platforms 403 requests without a browser-ish
    #: Accept header, so a minimal realistic set is included.
    default_headers: ClassVar[dict[str, str]] = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(settings.per_host_concurrency)
        self._last_request: float = 0.0

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=settings.request_timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": settings.user_agent,
                    **self.default_headers,
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _throttle(self) -> None:
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_request
        wait = settings.request_delay - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = loop.time()

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Perform a request with throttling and bounded retries."""
        last_exc: Exception | None = None
        for attempt in range(settings.max_retries):
            async with self._semaphore:
                await self._throttle()
                try:
                    response = await self.client.request(method, url, **kwargs)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_exc = exc
                    logger.warning(
                        "%s: transport error on %s (attempt %d/%d): %s",
                        self.name, url, attempt + 1, settings.max_retries, exc,
                    )
                else:
                    # 429/5xx are worth retrying; other 4xx mean our request is
                    # wrong and retrying just hammers the site.
                    if response.status_code < 400:
                        return response
                    if response.status_code not in (429, 500, 502, 503, 504):
                        raise ProviderError(
                            f"{self.name}: {method} {url} returned "
                            f"{response.status_code}"
                        )
                    last_exc = ProviderError(
                        f"{self.name}: {method} {url} returned {response.status_code}"
                    )
                    logger.warning(
                        "%s: %s on %s (attempt %d/%d)",
                        self.name, response.status_code, url,
                        attempt + 1, settings.max_retries,
                    )
            # Exponential backoff with jitter so parallel providers do not
            # synchronise their retries onto the same upstream.
            delay = settings.retry_backoff ** attempt + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

        raise ProviderError(
            f"{self.name}: {method} {url} failed after {settings.max_retries} attempts"
        ) from last_exc

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.request("GET", url, **kwargs)
        return response.json()

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.request("POST", url, **kwargs)
        return response.json()
