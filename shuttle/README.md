# USDA GWCC ↔ Greenbelt Shuttle Tracker

An unofficial, public, static web app for USDA employees who work out of the
**George Washington Carver Center (GWCC)**, 5601 Sunnyside Ave, Beltsville, MD,
and commute via the **Greenbelt Metro** station (Green / Yellow line).

Open `shuttle/index.html` — no build step, hosts anywhere (GitHub Pages, Netlify, S3).

## What it does

- **Next shuttle** — live countdown to the next departure in each direction.
- **Live map** — real-time shuttle positions when the GPS feed is reachable.
- **Full schedule** — the published timetable with the next departure highlighted.
- **Performance** — on-time rate, average wait and coverage, by hour.
- **Observations** — riders can log on-time/late catches (stored per-device).

## The data

| Layer | Source |
|---|---|
| Schedule | Published ARS GWCC shuttle timetable (rev. 3/13/2025) — [`schedule.json`](schedule.json). ~every 20 min, weekdays, 6:00 AM–6:20 PM. |
| Live positions / ETAs | USDA shuttle GPS feed, Ride Systems / TransLoc: `https://usda.ridesystems.net` (endpoint `Services/JSONPRelay.svc/*`). Read **client-side** by the browser, so it works on the open internet even though the site is static. |
| Performance | Computed by comparing the live feed against the schedule over time (see the monitor below). |

The app **always** works in schedule mode; live data upgrades it when available.
Some restricted networks (and this build sandbox) block `ridesystems.net`, so the
live map/ETAs only light up in a normal browser. The API key and base URL are
configurable under **About › Live data settings**, or via `?apikey=...&base=...`.

## Automated performance monitor (optional)

[`scripts/collect-shuttle.mjs`](../scripts/collect-shuttle.mjs) polls the live
feed, appends a sample to `data/samples.ndjson`, and recomputes the public
rollup at [`data/performance.json`](../data/performance.json) that the app reads.

Run it anywhere with open network access. It's wired to GitHub Actions in
[`.github/workflows/shuttle-monitor.yml`](../.github/workflows/shuttle-monitor.yml)
(every 10 min on weekday work hours):

1. Enable the workflow (scheduled runs only fire from the default branch).
2. Optional: set repo **Variable** `RIDESYSTEMS_BASE` and **Secret** `RIDESYSTEMS_APIKEY`
   if the defaults don't match the current USDA feed.
3. The action commits `data/*` back to the repo; the app picks it up automatically.

Manual run: `node scripts/collect-shuttle.mjs`

## Disclaimer

Community tool, not affiliated with or endorsed by USDA. Always confirm times
with the official USDA Shuttle app / `usda.ridesystems.net` and the
[ARS Rail Service Options](https://www.ars.usda.gov/northeast-area/docs/visitor-information/rail-service-options/) page.
