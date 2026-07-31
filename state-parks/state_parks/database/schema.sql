-- SQLite schema for the cabin aggregator.
--
-- Design notes:
--   * `availability` is a per-night table, not a per-stay table. Platforms
--     answer "is unit X free on night N", and arbitrary arrival/departure
--     windows are derived from that in SQL. Storing stays instead would make
--     the cache combinatorial (365 arrivals x 14 lengths per cabin).
--   * Every table carries `collected_at` so incremental refresh can target the
--     stale ranges and so price/availability history is a matter of *not*
--     deleting rows later (see docs/ROADMAP.md).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS providers (
    name                TEXT PRIMARY KEY,          -- 'NC', 'VA', ...
    state               TEXT NOT NULL,
    platform            TEXT NOT NULL,             -- 'reserve_america', 'usedirect', ...
    wire_format_verified INTEGER NOT NULL DEFAULT 0,
    enabled             INTEGER NOT NULL DEFAULT 1,
    last_refresh        TEXT,
    last_error          TEXT
);

CREATE TABLE IF NOT EXISTS parks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    state       TEXT NOT NULL,
    park_id     TEXT NOT NULL,                     -- provider-native id
    name        TEXT NOT NULL,
    provider    TEXT NOT NULL REFERENCES providers(name),
    latitude    REAL,
    longitude   REAL,
    url         TEXT,
    metadata    TEXT NOT NULL DEFAULT '{}',        -- JSON blob of platform ids
    collected_at TEXT NOT NULL,
    UNIQUE (state, park_id)
);

CREATE INDEX IF NOT EXISTS idx_parks_state ON parks (state);

CREATE TABLE IF NOT EXISTS cabins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    park_pk       INTEGER NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
    state         TEXT NOT NULL,
    cabin_id      TEXT NOT NULL,                   -- provider-native id
    cabin_name    TEXT NOT NULL,
    sleeps        INTEGER,
    bedrooms      INTEGER,
    bathrooms     REAL,
    pet_friendly  INTEGER,                         -- nullable boolean
    waterfront    INTEGER,
    latitude      REAL,
    longitude     REAL,
    reservation_url TEXT NOT NULL,
    collected_at  TEXT NOT NULL,
    UNIQUE (park_pk, cabin_id)
);

CREATE INDEX IF NOT EXISTS idx_cabins_state ON cabins (state);
CREATE INDEX IF NOT EXISTS idx_cabins_sleeps ON cabins (sleeps);

-- One row per (cabin, night).
CREATE TABLE IF NOT EXISTS availability (
    cabin_pk      INTEGER NOT NULL REFERENCES cabins(id) ON DELETE CASCADE,
    night         TEXT NOT NULL,                   -- ISO date; night *starting* on this day
    available     INTEGER NOT NULL,
    nightly_rate  REAL,
    collected_at  TEXT NOT NULL,
    PRIMARY KEY (cabin_pk, night)
);

CREATE INDEX IF NOT EXISTS idx_avail_night ON availability (night, available);
CREATE INDEX IF NOT EXISTS idx_avail_collected ON availability (collected_at);

-- Bookkeeping for incremental refresh: which (provider, month) windows have
-- been fetched and when. Lets the scheduler re-fetch only what has aged out.
CREATE TABLE IF NOT EXISTS refresh_log (
    provider     TEXT NOT NULL REFERENCES providers(name),
    park_id      TEXT NOT NULL DEFAULT '*',
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    refreshed_at TEXT NOT NULL,
    ok           INTEGER NOT NULL DEFAULT 1,
    error        TEXT,
    PRIMARY KEY (provider, park_id, window_start)
);
