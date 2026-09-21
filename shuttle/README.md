# USDA GWCC ↔ Greenbelt Shuttle

An unofficial, public, static web app for USDA employees who work out of the
**George Washington Carver Center (GWCC)**, 5601 Sunnyside Ave, Beltsville, MD,
and commute via the **Greenbelt Metro** station (Green / Yellow line).

Open `shuttle/index.html` — no build step; hosts anywhere (GitHub Pages, Netlify, S3).

## What it does

- **Next shuttle** — live countdown to the next departure in each direction, from the official schedule.
- **Map & stops** — the real GWCC and Greenbelt Metro stop locations and route.
- **Full schedule** — the timetable with the next departure highlighted.
- **Performance** — crowd-sourced on-time rate from riders' own logs.

## The data (and an honest note on "live" tracking)

| Layer | Source |
|---|---|
| Schedule & predictions | Official published ARS GWCC shuttle timetable (rev. 3/13/2025) — [`schedule.json`](schedule.json). ~every 20 min, weekdays. |
| Map | Real stop coordinates on OpenStreetMap tiles. |
| Performance | Riders' opt-in on-time / late logs, stored per-device. |

**There is no public, unauthenticated real-time GPS feed for this shuttle.**
It is run on **BusWhere / WheresTheBus** (the official *USDA Shuttle* app,
`com.bishoppeaktech.android.usdashuttle`). BusWhere's only documented API is the
authenticated school-bus "parent app" (email/password → session), and the public
`buswhere.com/<org>` viewer URLs now just redirect to their marketing site. Live
vehicle positions therefore live only inside the official app, which this site
links to rather than fake a feed. (An earlier draft pointed at
`usda.ridesystems.net`; that host is a dead placeholder and was never the real feed.)

If you have official access to the shuttle's live data (an app account or an
agency-provided feed URL), a small serverless proxy could relay positions into
this page — that's the only way to add a live map here.

## Deploy

- **GitHub Pages:** the workflow at `.github/workflows/pages.yml` publishes the repo
  root on every push to `main` (app at `/shuttle/`).
- **Netlify:** `netlify.toml` serves the app at the site root; git-link the repo or
  run `netlify deploy --prod --dir=.`.

## Disclaimer

Community tool, not affiliated with or endorsed by USDA. Confirm times with the
official USDA Shuttle app and the
[ARS Rail Service Options](https://www.ars.usda.gov/northeast-area/docs/visitor-information/rail-service-options/) page.
