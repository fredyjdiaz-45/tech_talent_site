"""Notification hooks -- deliberately a stub.

Not implemented yet (cancellation alerts, email/SMS/push are on the roadmap),
but the seam is here so adding them later is additive rather than surgical:
the refresh service can emit ``AvailabilityChanged`` events and subscribers can
be registered without touching provider or storage code.

See docs/ROADMAP.md for how the planned features attach to this.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from state_parks.models import Cabin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AvailabilityChanged:
    """A cabin became available (or stopped being) for a given window."""

    cabin: Cabin
    became_available: bool
    night: date


Subscriber = Callable[[AvailabilityChanged], Awaitable[None]]

_subscribers: list[Subscriber] = []


def subscribe(handler: Subscriber) -> Subscriber:
    """Register a handler. Returns it, so it can be used as a decorator."""
    _subscribers.append(handler)
    return handler


async def publish(event: AvailabilityChanged) -> None:
    """Fan an event out to subscribers, isolating handler failures."""
    for handler in _subscribers:
        try:
            await handler(event)
        except Exception:  # pragma: no cover - defensive
            logger.exception("notification handler %r failed", handler)


@subscribe
async def _log_only(event: AvailabilityChanged) -> None:
    """Default subscriber: log. Replace/augment with email, SMS, push."""
    if event.became_available:
        logger.info(
            "AVAILABLE %s %s at %s on %s",
            event.cabin.state, event.cabin.cabin_name,
            event.cabin.park, event.night,
        )
