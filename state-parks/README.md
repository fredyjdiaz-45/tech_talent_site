# State Parks Cabin Aggregator

Finds cabin availability across seven state park systems — North Carolina,
South Carolina, Virginia, Georgia, Tennessee, Delaware and Maryland — and
exposes it through one normalized API, regardless of which reservation platform
the data came from.

## Status, honestly

The architecture, storage, API, scheduler and tests are complete and working
(117 tests, all passing). **What is not complete is live verification of the
providers' request formats**, because the environment this was built in blocks
outbound HTTPS to all seven reservation hosts at the egress proxy. The
network-tab reverse engineering the brief asks for first could not be done here.

So each provider is explicit about its confidence level, and there is a
`verify` command to close the gap from a machine with normal network access:

| State | Platform | Status |
|---|---|---|
| VA | UseDirect | Wire format from a working open-source client; needs its RDR host confirmed |
| MD | Aspira Connect | Wire format from a working open-source client; needs Maryland's ids (`cli discover MD`) |
| NC, GA, DE | ReserveAmerica | HTML parser follows the platform's known markup; needs selectors + `parkId`s confirmed |
| SC, TN | Itinio | Endpoints genuinely unknown — **disabled by default**, raises rather than returning misleading empties |

`GET /providers` reports this at runtime. See [docs/PLATFORMS.md](docs/PLATFORMS.md)
for the full research record and what to confirm.

```bash
python -m state_parks.cli verify          # probe all seven, report findings
python -m state_parks.cli verify NC --save-fixture
```

## Quick start

```bash
pip install -e ".[dev]"

python -m state_parks.cli verify VA       # check a provider first
python -m state_parks.cli refresh --months 12
python -m state_parks.cli search --arrival 2026-09-04 --departure 2026-09-06
python -m state_parks.cli serve           # http://127.0.0.1:8000/docs
python -m state_parks.cli schedule        # background refresh loop
```

## API

```
GET  /parks                  ?state
GET  /cabins                 ?state &park &limit &offset
GET  /availability           ?arrival &departure &state &park &guests &pets
                             &sleeps &waterfront &available_only
GET  /availability/weekends  ?start &weeks &state &guests &pets &sleeps &waterfront
GET  /search                 ?...&source=cache|live
GET  /providers              provider health + verification state
POST /refresh                ?state &months &force
```

`state` is repeatable: `?state=NC&state=VA`. `source=live` bypasses the cache
and queries the parks directly (slower — please use sparingly).

## Architecture

```
state_parks/
    models/          Cabin, Park, SearchQuery, ProviderStatus  (pydantic)
    providers/
        base.py                StateProvider interface + polite HTTP client
        platforms/             one adapter per reservation platform
            reserve_america.py     NC, GA, DE   (HTML — see below)
            itinio.py              SC, TN
            usedirect.py           VA           (JSON)
            aspira_connect.py      MD           (JSON)
        north_carolina.py …    seven states, configuration only
    database/        SQLite schema + repository (the only module with SQL)
    services/        search, incremental refresh, notification hooks
    api/             FastAPI app
    scheduler/       APScheduler refresh loop
    cli.py           verify / discover / refresh / search / serve / schedule
```

Seven states run on **four** platforms, so states are thin: a new state on a
known platform is ~40 lines of catalog. Nothing above `providers/` knows which
platform answered.

### Why one provider parses HTML

The brief says to prefer JSON endpoints and only scrape as a last resort. That
holds for six states. ReserveAmerica (NC, GA, DE) is the exception and it is
genuinely forced: Aspira's public API is XML-only, contains no availability
data, and requires a commercial key, while the booking site is a server-rendered
Struts app with no JSON layer behind it. Parsing is confined to one pure
function with fixture tests. Playwright is not used anywhere — no platform here
needs a rendered page.

### Storage

Availability is stored **per night**, not per stay, so any arrival/departure
window can be answered from cache without the cache becoming combinatorial. A
stay is bookable when every night in its range has an available row — a `COUNT`
in SQL.

### Incremental refresh

The scheduler proposes the full 12 months every run; only windows never fetched
or older than `stale_after_hours` actually hit the network. Windows are fetched
soonest-first (cancellations matter most for near dates), failures leave a
window stale so it retries, and a provider whose parks *all* fail raises rather
than caching "no cabins" for a day.

## Being a good citizen

These are small public agencies. The client defaults to one in-flight request
per provider, a delay between requests, retries only on 429/5xx (never on 4xx),
and exponential backoff with jitter. Please don't tune these up.

## Tests

```bash
pytest                        # 117 tests, no network required
```

Parsers are pure functions tested against fixtures; providers are tested through
mocked HTTP (`respx`); the API through `TestClient`. The fixtures are
hand-built to the documented wire formats rather than captured live, so they
verify *parser logic* — not that the upstream shape is correct. `cli verify
--save-fixture` replaces them with real captures.

## Later

Cancellation alerts, email/SMS/push notifications, price and availability
history, AI trip recommendations, map search and weather are not implemented.
The seams exist: `services/notifications.py` has an event bus with a logging
subscriber, availability rows are timestamped so history is a matter of not
deleting them, and parks/cabins already carry lat/lon for map and weather work.
See [docs/ROADMAP.md](docs/ROADMAP.md).
