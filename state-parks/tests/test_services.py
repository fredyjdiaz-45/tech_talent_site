"""Refresh and search service tests.

The incremental-refresh behaviour is the part worth pinning: a second run must
not re-fetch what is still fresh, failures must not mark a window done, and a
provider that raises ``NotVerifiedError`` must bail out immediately instead of
grinding through 12 months of windows that cannot possibly work.
"""

from __future__ import annotations

from datetime import date, timedelta

from state_parks.config import settings
from state_parks.database import Repository
from state_parks.models import Cabin, SearchQuery
from state_parks.providers.base import NotVerifiedError, ProviderError, StateProvider
from state_parks.services import RefreshService, SearchService, build_windows
from tests.conftest import make_cabin


class FakeProvider(StateProvider):
    """A provider that answers from memory, counting how often it is called."""

    state = "NC"
    platform = "fake"
    wire_format_verified = True
    base_url = "https://example.invalid"

    def __init__(self, cabins: list[Cabin] | None = None,
                 raises: Exception | None = None) -> None:
        self._cabins = cabins or []
        self._raises = raises
        self.calls = 0

    async def search_cabins(self, start_date, end_date, guests, pets=False):
        self.calls += 1
        if self._raises:
            raise self._raises
        return [
            c.model_copy(update={"arrival": start_date,
                                 "departure": start_date + timedelta(days=2)})
            for c in self._cabins
        ]


# ---------------------------------------------------------------------------
# Window planning
# ---------------------------------------------------------------------------
def test_build_windows_covers_the_horizon() -> None:
    start = date(2026, 1, 1)
    windows = build_windows(start, months=12, chunk_days=30)
    assert windows[0][0] == start
    assert (windows[-1][1] - start).days >= 364
    # Contiguous, no gaps.
    for earlier, later in zip(windows, windows[1:], strict=False):
        assert earlier[1] == later[0]


def test_build_windows_respects_chunk_size() -> None:
    windows = build_windows(date(2026, 1, 1), months=1, chunk_days=7)
    assert all((w[1] - w[0]).days <= 7 for w in windows)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
class TestRefresh:
    async def test_refresh_stores_cabins(self, repo: Repository) -> None:
        provider = FakeProvider([make_cabin()])
        result = await RefreshService(repo).refresh_provider(provider, months=1)
        assert result.ok
        assert result.cabins_found > 0
        assert result.rows_written > 0
        assert repo.list_cabins()

    async def test_second_run_skips_fresh_windows(self, repo: Repository) -> None:
        """This is the whole point of incremental refresh."""
        provider = FakeProvider([make_cabin()])
        service = RefreshService(repo)
        await service.refresh_provider(provider, months=1)
        first_pass_calls = provider.calls

        second = await service.refresh_provider(provider, months=1)
        assert provider.calls == first_pass_calls  # no new network calls
        assert second.skipped == "fresh"

    async def test_force_refetches_everything(self, repo: Repository) -> None:
        provider = FakeProvider([make_cabin()])
        service = RefreshService(repo)
        await service.refresh_provider(provider, months=1)
        calls_after_first = provider.calls

        await service.refresh_provider(provider, months=1, force=True)
        assert provider.calls > calls_after_first

    async def test_stale_windows_are_refetched(
        self, repo: Repository, monkeypatch
    ) -> None:
        provider = FakeProvider([make_cabin()])
        service = RefreshService(repo)
        await service.refresh_provider(provider, months=1)
        calls_after_first = provider.calls

        # Age everything out.
        monkeypatch.setattr(settings, "stale_after_hours", 0)
        await service.refresh_provider(provider, months=1)
        assert provider.calls > calls_after_first

    async def test_failed_window_is_not_marked_fresh(self, repo: Repository) -> None:
        provider = FakeProvider(raises=ProviderError("upstream down"))
        service = RefreshService(repo)
        result = await service.refresh_provider(provider, months=1)
        assert not result.ok
        assert result.windows_ok == 0

        # A retry must try again rather than considering the window done.
        retry = await service.refresh_provider(provider, months=1)
        assert retry.windows_attempted > 0

    async def test_unverified_provider_bails_out_immediately(
        self, repo: Repository
    ) -> None:
        """One failed window, not twelve months of pointless attempts."""
        provider = FakeProvider(raises=NotVerifiedError("endpoint unknown"))
        result = await RefreshService(repo).refresh_provider(provider, months=12)
        assert result.skipped == "wire format not verified"
        assert provider.calls == 1

    async def test_refresh_all_isolates_a_crashing_provider(
        self, repo: Repository
    ) -> None:
        good = FakeProvider([make_cabin()])
        bad = FakeProvider(raises=ProviderError("boom"))
        bad.state = "VA"
        results = await RefreshService(repo).refresh_all([good, bad], months=1)
        assert len(results) == 2
        assert any(r.ok for r in results)

    async def test_near_windows_are_fetched_before_far_ones(
        self, repo: Repository
    ) -> None:
        """Cancellations matter most soon, so soonest-first ordering matters."""
        seen: list[date] = []

        class OrderRecordingProvider(FakeProvider):
            async def search_cabins(self, start_date, end_date, guests, pets=False):
                seen.append(start_date)
                return []

        await RefreshService(repo).refresh_provider(
            OrderRecordingProvider(), months=6
        )
        assert seen == sorted(seen)


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------
class TestSearchService:
    async def test_cached_search_reads_from_sqlite(self, repo: Repository) -> None:
        repo.store_cabins([make_cabin()])
        service = SearchService(repo)
        found = await service.search(
            SearchQuery(arrival=date(2026, 9, 4), departure=date(2026, 9, 6),
                        guests=2)
        )
        assert len(found) == 1

    async def test_guests_defaults_the_sleeps_filter(self, repo: Repository) -> None:
        repo.store_cabins([make_cabin(cabin_id="small", sleeps=2)])
        service = SearchService(repo)
        found = await service.search(
            SearchQuery(arrival=date(2026, 9, 4), departure=date(2026, 9, 6),
                        guests=8)
        )
        assert found == []

    async def test_weekends_returns_only_weekend_arrivals(
        self, repo: Repository
    ) -> None:
        friday = date(2026, 9, 4)
        repo.store_cabins([make_cabin(arrival=friday,
                                      departure=friday + timedelta(days=2))])
        found = await SearchService(repo).weekends(start=friday, weeks=4)
        assert all(c.arrival.weekday() == 4 for c in found)

    async def test_parks_and_cabins_listings(self, repo: Repository) -> None:
        repo.store_cabins([make_cabin()])
        service = SearchService(repo)
        assert len(await service.parks()) == 1
        assert len(await service.cabins(state="NC")) == 1
        assert await service.cabins(state="VA") == []
