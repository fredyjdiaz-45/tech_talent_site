# Roadmap

None of this is implemented. It is recorded here because the current design was
shaped to make each item additive rather than a rewrite — this note explains
which seam each one attaches to.

## Cancellation alerts

The highest-value feature, and the reason refresh is ordered soonest-first.

`availability` is already an upsert-per-night table, so detecting a change means
comparing the incoming value against the stored one before writing — the row is
right there. Emit `AvailabilityChanged` from
`Repository.store_cabins` (or a thin wrapper) and the rest is subscribers.

Needed: a `watches` table (state/park/date range/party size), and a matcher run
after each refresh.

## Email / SMS / push notifications

`services/notifications.py` is an async event bus with `subscribe()` and a
default logging subscriber. Each channel is one more subscriber:

- email — `aiosmtplib` against any SMTP account
- SMS — Twilio, or a carrier email gateway to stay free
- push — ntfy.sh or Pushover, both of which are a single HTTP POST

Add per-watch channel preferences and a rate limit so one cabin flickering in
and out cannot send fifty messages.

## Price history and availability history

Already most of the way there: `availability` carries `nightly_rate` and
`collected_at`, and `refresh_log` records every fetch. Today an upsert
overwrites the previous value; history is a matter of writing to an
append-only `availability_history` table on change instead of discarding.

That enables "is this cheaper than usual", "how fast does this cabin book up",
and "how often does it free up in the last week" — the questions that make
cancellation hunting actually work.

## Map search

`parks` and `cabins` both store `latitude`/`longitude`, and every provider
populates them where upstream offers them. A bounding-box or radius filter is a
`WHERE` clause plus a query parameter; SQLite's R*Tree module handles it if it
ever gets slow. A static Leaflet page against `/cabins` would be enough.

## Weather integration

Attach to search results by lat/lon at read time. NWS
(`api.weather.gov`) is free, needs no key, and covers all seven states. Cache
per (grid point, day) — forecasts change far more slowly than the request rate.

Worth it mainly for the weekend endpoint: "free cabins next month, in places
where it will not be raining".

## AI trip recommendations

Only worth doing once history exists. With price and availability history plus
weather, useful prompts become answerable — "quiet waterfront cabin for four,
somewhere within a four-hour drive, first weekend it is both free and dry". The
normalized `Cabin` model is already a reasonable serialization for a model
context; drive-time needs a distance matrix, which is the only new dependency.

## Provider work

Ranked by what actually blocks results today:

1. **SC and TN (Itinio)** — capture the availability endpoint from a browser,
   set `availability_path`, save a fixture, enable. Unblocks two states.
2. **MD** — run `cli discover MD` to populate the catalog. Everything else is
   written.
3. **VA** — confirm which host serves `/rdr/rdr/...`.
4. **NC, GA, DE** — confirm the calendar selectors and fill in real `parkId`
   values with `cli verify --save-fixture`.
5. Widen the park catalogs. They are starter sets of known cabin parks, not
   exhaustive — Georgia alone has roughly 250 cottages.
