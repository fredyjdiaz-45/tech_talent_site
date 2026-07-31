# Reservation platforms, per state

This is the research record behind the provider layer: which system each state
actually runs, how its requests work, and — importantly — **how confident you
should be in each provider**.

## Summary

| State | Booking host | Platform | Data format | Wire format verified |
|---|---|---|---|---|
| NC | `northcarolinastateparks.reserveamerica.com` | ReserveAmerica | HTML | ❌ |
| SC | `reserve.southcarolinaparks.com` | Itinio | unknown | ❌ (disabled) |
| VA | `reservevaparks.com/Web/` | UseDirect (US eDirect) | JSON | ⚠️ shape yes, host no |
| GA | `gastateparks.reserveamerica.com` | ReserveAmerica | HTML | ❌ |
| TN | `reserve.tnstateparks.com` | Itinio | unknown | ❌ (disabled) |
| DE | `delawarestateparks.reserveamerica.com` | ReserveAmerica | HTML | ❌ |
| MD | `parkreservations.maryland.gov` | Aspira Connect | JSON | ⚠️ shape yes, ids no |

Seven states, **four** platforms — which is what makes the provider/platform
split pay for itself. ReserveAmerica alone covers three states, Itinio two.

## Why nothing is marked fully verified

The environment this was built in blocks outbound HTTPS to every one of these
hosts at the egress proxy (403 on CONNECT), and the sites additionally return
403 to non-browser clients. So the one step the brief asks for first — open the
network tab and watch the XHRs — was not possible here.

Rather than invent plausible-looking endpoints and leave you to discover the
fiction later, each provider records what is known, from where, and what still
needs a browser. Two paths were used to get as far as possible:

1. **Vendor identification** — confirmed for all seven states from public
   sources (see Sources).
2. **Wire formats** — taken from [`camply`](https://github.com/juftin/camply)
   (MIT), a maintained open-source client that talks to live UseDirect and
   GoingToCamp/Aspira Connect deployments. Endpoint paths, parameter names and
   response fields for those two platforms come from there, so the *shape* is
   trustworthy even though this project could not exercise it.

`GET /providers` on the running API reports `wire_format_verified` per state, so
this uncertainty is visible at runtime and not just in a document.

## Finishing verification

```bash
python -m state_parks.cli verify NC --save-fixture   # one state
python -m state_parks.cli verify                     # all seven
```

`verify` hits the real endpoints, reports what each returned, and (for HTML
platforms) saves a sample into `tests/fixtures/` so the parser can be corrected
against reality. For Itinio it additionally probes a list of candidate endpoint
paths and reports which exist and which return JSON.

---

## ReserveAmerica (NC, GA, DE)

Vendor: ReserveAmerica, owned by Aspira since 2017. Branded subdomain per
agency plus a `contractCode` (`NC`, `GA`, `DE`).

**This is the one place HTML parsing is used, and it is unavoidable.** The
brief says not to scrape HTML unless absolutely necessary; ReserveAmerica is
that case:

- Aspira's public Campground API (`developer.active.com`) is **XML-only**, is
  documented as containing **no availability data**, and needs a commercial key.
- The booking site is a server-rendered Struts app — every URL ends in `.do`
  and returns HTML. There is no XHR/JSON layer behind it to reverse engineer.

Request used:

```
GET /campsiteCalendar.do?page=calendar&contractCode=NC&parkId=<id>
    &calarvdate=MM/DD/YYYY&sitepage=true
```

Returns a 14-night grid: `table#calendar`, one row per site, `td.sn` naming it,
and one `td.status` per night whose CSS class carries availability (`a` free,
`r`/`x`/`n` blocked). Parsing lives in a single pure function,
`parse_campsite_calendar`, with fixture-backed tests, so markup drift breaks one
function rather than the provider.

**Needs confirming:** the CSS classes, and every `parkId` in the catalogs.

## UseDirect / US eDirect (VA)

Virginia DCR moved off ReserveAmerica to US eDirect. Same platform as
California, Texas, Arizona and Florida, so this adapter is reusable.

```
GET  {rdr}/rdr/rdr/search/places
GET  {rdr}/rdr/rdr/search/facilities
POST {rdr}/rdr/rdr/search/availability
```

Availability body (empty values stripped — some builds 500 on unexpected nulls):

```json
{"FacilityId": "1", "StartDate": "2026-09-04", "EndDate": "2026-09-06",
 "MinVehicleLength": 0, "IsADA": false, "WebOnly": true,
 "InSeasonOnly": true, "UnitSort": "orderby"}
```

Response: `Facility.Units[].Slices[].IsFree` — a unit is bookable when every
night's slice is free.

**Needs confirming:** `rdr_base_url`. UseDirect deployments serve RDR either
from the booking host or from a dedicated `<state>rdr.usedirect.com` host; both
candidates are noted in `providers/virginia.py`. Also the `FacilityId` values.

## Aspira Connect / GoingToCamp (MD)

Maryland Park Service launched on this in February 2026. Same codebase as
`*.goingtocamp.com`. Note it is **not** ReserveAmerica despite both being
Aspira — Connect is a JSON-backed SPA, ReserveAmerica is the legacy
server-rendered system, and they share no endpoints. The `/create-booking` route
in Maryland's public links is the signature.

```
GET /api/resourceLocation
GET /api/maps
GET /api/availability/map?mapId=..&resourceLocationId=..&bookingCategoryId=..
    &startDate=..&endDate=..&partySize=..&getDailyAvailability=true
```

Response: `resourceAvailabilities: {resourceId: [{availability: 0}, ...]}`,
one entry per night. **`availability == 0` means AVAILABLE** — the most
error-prone detail in this whole project, and the reason it has its own test.

**Needs confirming:** Maryland's `resourceLocationId` / `mapId` /
`bookingCategoryId`. Because the system is new, none are published. Run
`python -m state_parks.cli discover MD` — it walks the two catalog endpoints and
writes a populated catalog file.

## Itinio (SC, TN)

Both states run the same product; the identical URL scheme
(`/<park-slug>/cabins`, `/myaccount/`) is what links them, and Tennessee's pages
being served from `tsp.itinio.com` is what names the vendor.

**This is the weakest adapter and it is disabled by default.** Unlike the other
two JSON platforms, Itinio has no open-source client to use as a reference, and
the hosts were unreachable, so its endpoints are genuinely unknown. Inventing
endpoint names would have produced code that looks finished and silently
returns nothing.

Instead:

- `search_cabins` raises `NotVerifiedError` with instructions rather than
  returning a misleading empty list.
- `probe()` tries candidate endpoints and reports status + content type, so
  `cli verify SC` tells you what the real API is.
- The inventory scrape of `/<park>/cabins` **works today** and seeds the cabin
  catalog, so the states are not dead weight in the meantime.

Finishing it is a one-line change (`availability_path`) plus a fixture, once a
real response is in hand.

## Sources

- [NC State Parks — reservations](https://www.ncparks.gov/recreation/camping/reserving-campsites) · [booking host](https://northcarolinastateparks.reserveamerica.com/)
- [SC State Parks — reservations](https://reserve.southcarolinaparks.com/)
- [Virginia DCR — new reservation system](https://www.dcr.virginia.gov/state-parks/new-reservations) · [booking host](https://www.reservevaparks.com/Web/)
- [Georgia State Parks — reservations](https://gastateparks.org/Reservations) · [booking host](https://gastateparks.reserveamerica.com/)
- [Tennessee State Parks — reservations](https://reserve.tnstateparks.com/) · [Itinio-served pages](https://tsp.itinio.com/cumberland-mountain/cabins/)
- [Delaware State Parks — reservation information](https://www.destateparks.com/reservation-information/) · [booking host](https://delawarestateparks.reserveamerica.com/)
- [Maryland DNR — new reservation system (Aspira)](https://news.maryland.gov/dnr/2026/03/05/maryland-park-service-online-reservations-system-upgraded-ahead-of-2026-camping-season/) · [booking host](https://parkreservations.maryland.gov/create-booking)
- [Aspira Connect — state parks clients](https://aspiraconnect.com/state-parks) · [ReserveAmerica ownership](https://en.wikipedia.org/wiki/ReserveAmerica)
- [ACTIVE/Aspira Campground API — XML only, no availability](https://developer.active.com/docs/read/Campground_Search_API)
- [`camply`](https://github.com/juftin/camply) (MIT) — reference for the UseDirect and GoingToCamp wire formats
