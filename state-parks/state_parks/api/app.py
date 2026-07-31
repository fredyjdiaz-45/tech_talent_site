"""FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from state_parks.api.deps import get_database
from state_parks.api.routes import router
from state_parks.config import settings
from state_parks.database import Repository
from state_parks.providers import all_providers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    db = get_database()
    repo = Repository(db.conn)
    # Register providers so /providers reports verification state even before
    # the first refresh has run.
    for provider in all_providers():
        repo.upsert_provider(provider.status())
    logger.info("state-parks API ready (db=%s)", settings.database_path)
    yield
    db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="State Parks Cabin Aggregator",
        version="0.1.0",
        summary=(
            "Normalized cabin availability across NC, SC, VA, GA, TN, DE and MD "
            "state park systems."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
