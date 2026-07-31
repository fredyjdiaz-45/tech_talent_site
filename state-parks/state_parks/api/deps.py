"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache

from state_parks.database import Database, Repository
from state_parks.services import RefreshService, SearchService


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database()


def get_repository() -> Repository:
    return Repository(get_database().conn)


def get_search_service() -> SearchService:
    return SearchService(get_repository())


def get_refresh_service() -> RefreshService:
    return RefreshService(get_repository())
