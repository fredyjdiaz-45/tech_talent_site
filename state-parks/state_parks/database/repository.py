"""Persistence and query layer.

The repository is the only module that speaks SQL. Services and the API deal in
``Cabin``/``Park`` models.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from state_parks.models import Cabin, Park, ProviderStatus


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def nights_between(arrival: date, departure: date) -> list[date]:
    """Nights covered by a stay: arrival inclusive, departure exclusive."""
    return [arrival + timedelta(days=i) for i in range((departure - arrival).days)]


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    def upsert_provider(self, status: ProviderStatus) -> None:
        self.conn.execute(
            """
            INSERT INTO providers (name, state, platform, wire_format_verified, enabled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                state = excluded.state,
                platform = excluded.platform,
                wire_format_verified = excluded.wire_format_verified,
                enabled = excluded.enabled
            """,
            (
                status.name,
                status.state,
                status.platform,
                int(status.wire_format_verified),
                int(status.enabled),
            ),
        )
        self.conn.commit()

    def mark_refresh(
        self, provider: str, *, error: str | None = None
    ) -> None:
        self.conn.execute(
            "UPDATE providers SET last_refresh = ?, last_error = ? WHERE name = ?",
            (_now(), error, provider),
        )
        self.conn.commit()

    def list_providers(self) -> list[ProviderStatus]:
        rows = self.conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM cabins c
                     WHERE c.state = p.state) AS cabins_tracked
            FROM providers p ORDER BY p.name
            """
        ).fetchall()
        return [
            ProviderStatus(
                name=r["name"],
                state=r["state"],
                platform=r["platform"],
                wire_format_verified=bool(r["wire_format_verified"]),
                enabled=bool(r["enabled"]),
                last_refresh=(
                    datetime.fromisoformat(r["last_refresh"])
                    if r["last_refresh"]
                    else None
                ),
                last_error=r["last_error"],
                cabins_tracked=r["cabins_tracked"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Parks & cabins
    # ------------------------------------------------------------------
    def _ensure_provider(self, name: str, state: str) -> None:
        """Guarantee a providers row exists so parks' FK can be satisfied.

        Parks can arrive before a provider has been formally registered (an
        ad-hoc live search, a test, a restored database). Auto-registering a
        minimal row keeps the foreign key meaningful without making every
        caller remember to register first; a later `upsert_provider` fills in
        the real platform and verification flags.
        """
        self.conn.execute(
            """
            INSERT INTO providers (name, state, platform, wire_format_verified)
            VALUES (?, ?, 'unknown', 0)
            ON CONFLICT(name) DO NOTHING
            """,
            (name, state),
        )

    def upsert_park(self, park: Park) -> int:
        self._ensure_provider(park.provider, park.state)
        self.conn.execute(
            """
            INSERT INTO parks (state, park_id, name, provider, latitude, longitude,
                               url, metadata, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(state, park_id) DO UPDATE SET
                name = excluded.name,
                provider = excluded.provider,
                latitude = COALESCE(excluded.latitude, parks.latitude),
                longitude = COALESCE(excluded.longitude, parks.longitude),
                url = COALESCE(excluded.url, parks.url),
                metadata = excluded.metadata,
                collected_at = excluded.collected_at
            """,
            (
                park.state,
                park.park_id,
                park.name,
                park.provider,
                park.latitude,
                park.longitude,
                park.url,
                json.dumps(park.metadata),
                _now(),
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM parks WHERE state = ? AND park_id = ?",
            (park.state, park.park_id),
        ).fetchone()
        self.conn.commit()
        return int(row["id"])

    def list_parks(self, state: str | None = None) -> list[Park]:
        sql = "SELECT * FROM parks"
        params: list[Any] = []
        if state:
            sql += " WHERE state = ?"
            params.append(state.upper())
        sql += " ORDER BY state, name"
        return [
            Park(
                state=r["state"],
                park_id=r["park_id"],
                name=r["name"],
                provider=r["provider"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                url=r["url"],
                metadata=json.loads(r["metadata"]),
            )
            for r in self.conn.execute(sql, params).fetchall()
        ]

    def _upsert_cabin(self, park_pk: int, cabin: Cabin) -> int:
        cabin_id = cabin.cabin_id or cabin.cabin_name
        self.conn.execute(
            """
            INSERT INTO cabins (park_pk, state, cabin_id, cabin_name, sleeps, bedrooms,
                                bathrooms, pet_friendly, waterfront, latitude,
                                longitude,
                                reservation_url, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(park_pk, cabin_id) DO UPDATE SET
                cabin_name = excluded.cabin_name,
                -- COALESCE keeps previously-learned detail when a cheap search
                -- response omits it (search payloads are thinner than detail
                -- payloads on every platform here).
                sleeps = COALESCE(excluded.sleeps, cabins.sleeps),
                bedrooms = COALESCE(excluded.bedrooms, cabins.bedrooms),
                bathrooms = COALESCE(excluded.bathrooms, cabins.bathrooms),
                pet_friendly = COALESCE(excluded.pet_friendly, cabins.pet_friendly),
                waterfront = COALESCE(excluded.waterfront, cabins.waterfront),
                latitude = COALESCE(excluded.latitude, cabins.latitude),
                longitude = COALESCE(excluded.longitude, cabins.longitude),
                reservation_url = excluded.reservation_url,
                collected_at = excluded.collected_at
            """,
            (
                park_pk,
                cabin.state,
                cabin_id,
                cabin.cabin_name,
                cabin.sleeps,
                cabin.bedrooms,
                cabin.bathrooms,
                None if cabin.pet_friendly is None else int(cabin.pet_friendly),
                None if cabin.waterfront is None else int(cabin.waterfront),
                cabin.latitude,
                cabin.longitude,
                cabin.reservation_url,
                _now(),
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM cabins WHERE park_pk = ? AND cabin_id = ?",
            (park_pk, cabin_id),
        ).fetchone()
        return int(row["id"])

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def store_cabins(self, cabins: Iterable[Cabin]) -> int:
        """Persist stay quotes, expanding each into per-night availability rows.

        A provider that returns a 3-night quote is asserting the unit is bookable
        for all three nights, so the quote fans out to three rows. An
        *unavailable* quote only tells us the window as a whole failed, which is
        weaker information -- we record it against the arrival night only, so a
        single blocked night never poisons the whole window in the cache.
        """
        written = 0
        for cabin in cabins:
            park_pk = self.upsert_park(
                Park(
                    state=cabin.state,
                    park_id=cabin.park_id or cabin.park,
                    name=cabin.park,
                    provider=cabin.provider or cabin.state,
                    latitude=cabin.latitude,
                    longitude=cabin.longitude,
                )
            )
            cabin_pk = self._upsert_cabin(park_pk, cabin)
            nights = (
                nights_between(cabin.arrival, cabin.departure)
                if cabin.available
                else [cabin.arrival]
            )
            for night in nights:
                self.conn.execute(
                    """
                    INSERT INTO availability (cabin_pk, night, available, nightly_rate,
                                              collected_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(cabin_pk, night) DO UPDATE SET
                        available = excluded.available,
                        nightly_rate = COALESCE(excluded.nightly_rate,
                                                availability.nightly_rate),
                        collected_at = excluded.collected_at
                    """,
                    (
                        cabin_pk,
                        night.isoformat(),
                        int(cabin.available),
                        cabin.nightly_rate,
                        _now(),
                    ),
                )
                written += 1
        self.conn.commit()
        return written

    def log_refresh(
        self,
        provider: str,
        window_start: date,
        window_end: date,
        *,
        park_id: str = "*",
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO refresh_log (provider, park_id, window_start, window_end,
                                     refreshed_at, ok, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, park_id, window_start) DO UPDATE SET
                window_end = excluded.window_end,
                refreshed_at = excluded.refreshed_at,
                ok = excluded.ok,
                error = excluded.error
            """,
            (
                provider,
                park_id,
                window_start.isoformat(),
                window_end.isoformat(),
                _now(),
                int(ok),
                error,
            ),
        )
        self.conn.commit()

    def stale_windows(
        self, provider: str, windows: Sequence[tuple[date, date]], max_age_hours: int
    ) -> list[tuple[date, date]]:
        """Filter ``windows`` down to those never fetched or older than the TTL.

        This is what makes refreshes incremental: the scheduler proposes the full
        12 months every run, and only the aged-out slices actually hit the network.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        rows = self.conn.execute(
            "SELECT window_start, refreshed_at, ok FROM refresh_log WHERE provider = ?",
            (provider,),
        ).fetchall()
        fresh = {
            r["window_start"]
            for r in rows
            if r["ok"] and datetime.fromisoformat(r["refreshed_at"]) > cutoff
        }
        return [w for w in windows if w[0].isoformat() not in fresh]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(
        self,
        *,
        arrival: date,
        departure: date,
        states: Sequence[str] | None = None,
        park: str | None = None,
        sleeps: int | None = None,
        pets: bool | None = None,
        waterfront: bool | None = None,
        available_only: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Cabin]:
        """Find cabins bookable for the whole window.

        A cabin qualifies when it has an ``available`` row for *every* night of
        the stay -- expressed as a COUNT over the night range matching the stay
        length, which lets SQLite answer arbitrary windows from per-night rows.
        """
        nights = nights_between(arrival, departure)
        if not nights:
            return []

        where = ["a.night >= ?", "a.night < ?"]
        params: list[Any] = [arrival.isoformat(), departure.isoformat()]
        if available_only:
            where.append("a.available = 1")
        if states:
            where.append(f"c.state IN ({','.join('?' * len(states))})")
            params.extend(s.upper() for s in states)
        if park:
            where.append("p.name LIKE ?")
            params.append(f"%{park}%")
        if sleeps is not None:
            # NULL sleeps means "unknown", not "too small" -- keep those rows and
            # let the caller decide, rather than silently hiding inventory.
            where.append("(c.sleeps IS NULL OR c.sleeps >= ?)")
            params.append(sleeps)
        if pets:
            where.append("c.pet_friendly = 1")
        if waterfront is not None:
            where.append("c.waterfront = ?")
            params.append(int(waterfront))

        having = "HAVING COUNT(*) = ?" if available_only else ""
        params_tail: list[Any] = [len(nights)] if available_only else []

        sql = f"""
            SELECT c.*, p.name AS park_name, p.park_id AS park_key, p.provider,
                   AVG(a.nightly_rate) AS nightly_rate,
                   MIN(a.collected_at) AS collected_at
            FROM availability a
            JOIN cabins c ON c.id = a.cabin_pk
            JOIN parks p ON p.id = c.park_pk
            WHERE {' AND '.join(where)}
            GROUP BY c.id
            {having}
            ORDER BY c.state, p.name, c.cabin_name
            LIMIT ? OFFSET ?
        """
        rows = self.conn.execute(sql, [*params, *params_tail, limit, offset]).fetchall()
        return [self._row_to_cabin(r, arrival, departure) for r in rows]

    def weekend_search(
        self,
        *,
        start: date,
        end: date,
        states: Sequence[str] | None = None,
        sleeps: int | None = None,
        pets: bool | None = None,
        waterfront: bool | None = None,
        limit: int = 200,
    ) -> list[Cabin]:
        """Fri->Sun (2-night) stays across a date range.

        Weekend hunting is the main reason this project exists, so it gets a
        dedicated path rather than making the caller loop over dates.
        """
        results: list[Cabin] = []
        cursor = start
        # Advance to the first Friday.
        cursor += timedelta(days=(4 - cursor.weekday()) % 7)
        while cursor < end and len(results) < limit:
            results.extend(
                self.search(
                    arrival=cursor,
                    departure=cursor + timedelta(days=2),
                    states=states,
                    sleeps=sleeps,
                    pets=pets,
                    waterfront=waterfront,
                    available_only=True,
                    limit=limit - len(results),
                )
            )
            cursor += timedelta(days=7)
        return results

    def list_cabins(
        self,
        state: str | None = None,
        park: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[Cabin]:
        """Inventory listing, independent of any date window."""
        where: list[str] = []
        params: list[Any] = []
        if state:
            where.append("c.state = ?")
            params.append(state.upper())
        if park:
            where.append("p.name LIKE ?")
            params.append(f"%{park}%")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
            SELECT c.*, p.name AS park_name, p.park_id AS park_key, p.provider,
                   NULL AS nightly_rate, c.collected_at AS collected_at
            FROM cabins c JOIN parks p ON p.id = c.park_pk
            {clause}
            ORDER BY c.state, p.name, c.cabin_name
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        today = date.today()
        return [self._row_to_cabin(r, today, today + timedelta(days=1)) for r in rows]

    def _row_to_cabin(self, r: sqlite3.Row, arrival: date, departure: date) -> Cabin:
        keys = r.keys()
        return Cabin(
            state=r["state"],
            park=r["park_name"],
            park_id=r["park_key"],
            cabin_name=r["cabin_name"],
            cabin_id=r["cabin_id"],
            arrival=arrival,
            departure=departure,
            available=True,
            nightly_rate=r["nightly_rate"] if "nightly_rate" in keys else None,
            sleeps=r["sleeps"],
            bedrooms=r["bedrooms"],
            bathrooms=r["bathrooms"],
            pet_friendly=_as_bool(r["pet_friendly"]),
            waterfront=_as_bool(r["waterfront"]),
            latitude=r["latitude"],
            longitude=r["longitude"],
            reservation_url=r["reservation_url"],
            provider=r["provider"],
        )
