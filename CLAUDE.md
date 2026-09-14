# CLAUDE.md

Context for working in this repo that isn't derivable from reading the source. Code docstrings already explain *how* each script works and why (join paths, unit gotchas, etc.) - this file is for things that live outside any single file: infra decisions, tool requirements, and what's been deliberately left undone.

## Repo/branch structure

- **Everything lives on `gh-pages`.** There is no separate source/main branch feeding a build step - this branch *is* the site, scripts and all.
- **`gh-pages` is also the repo's default branch** (changed from `master` partway through). This wasn't cosmetic: GitHub only lets you dispatch a `workflow_dispatch` workflow (via UI or `gh workflow run`) if the workflow file exists on the default branch, even though the workflow itself can run against any branch. Keep them the same branch, or workflow dispatch silently 404s.
- `master` still exists on the remote but is stale/unused. Don't assume it reflects the real state of anything.

## Access requirements for this repo

- **`gh` CLI may or may not be on PATH** depending on the environment - check before assuming it's available for triggering workflows or checking run status.

## Map tiles: why Esri, not the more obvious choices

- OSM's own tile servers are explicitly against usage policy for this kind of app - never use `tile.openstreetmap.org` directly.
- CARTO's `basemaps.cartocdn.com` (a very commonly cited "free, no key" option in tutorials) **now requires an API key** - it returns HTTP 200 to a bare `curl`, but renders an "API KEY REQUIRED" watermark when actually loaded in a browser context. Curl alone won't catch this; you have to render it.
- Esri's `World_Street_Map` REST endpoint works with no key and no signup for this kind of low-traffic personal use, and is what's actually wired up in `js/app.js`.
- If Esri ever locks down too, the next things to try are Stadia Maps or MapTiler - both need an account/API key (can't be set up without the account owner), so that's a bigger lift than a tile-URL swap.

## FCC data sources: gotchas that aren't obvious from the fetch scripts alone

- `enterpriseefiling.fcc.gov` (LMS bulk dump) is behind Akamai and blocks plain HTTP clients (curl, wget, Python `requests`) with a 403 - but a real headless-Chromium navigation (Playwright) gets through cleanly, including for the biggest files (250MB+). This isn't IP-reputation-based, since the same block/bypass pattern held on a fresh GitHub Actions runner too.
- `transition.fcc.gov` (a CDBS mirror) is *also* behind Akamai, but its rule is stricter - it blocks headless Chromium outright, unlike the LMS host. Don't assume "use a real browser" is a universal fix for Akamai; test each host.
- `ftp.fcc.gov`'s HTTPS gateway is broken for GET requests specifically (HEAD succeeds, GET hangs/times out) - confirmed across three unrelated networks (this sandbox, a GitHub Actions runner, and Anthropic's own WebFetch infra). The underlying plain `ftp://` protocol works instantly. Python's own `urllib`/`ftplib` FTP support also hung against this server for reasons never root-caused - `fetch_cdbs_data.py` shells out to `curl` instead, which just works.
- The LMS dump lives under a folder named for today's date (`09-12-2026/`, etc.) - the fetch script scrapes the index page for that folder name rather than computing today's date, since there's no guarantee it matches wall-clock time exactly (e.g. weekends, delayed runs).

## Data model: what "backfill" actually means here

CDBS backfill isn't a minor edge case - **53.9% of licensed AM stations and 29.0% of licensed FM stations have zero matching engineering data in LMS** (they haven't been re-filed since LMS launched in 2014). Any future change to the join logic needs to be checked against both LMS-resolved and CDBS-resolved stations, not just LMS.

`facility_id` is a stable identifier across the CDBS→LMS migration - confirmed empirically (WABC is `70658` in both systems), not documented anywhere by the FCC. This is what makes the backfill join possible at all.

## Known-good reference stations (informal regression check)

There's no automated test suite yet. These were spot-checked by hand against real, independently-known values during development - if a future change to `parse_stations.py` or `am_groundwave.py` makes any of these come out differently, that's a signal something broke, not a coincidence:

| Station | Band | Path | Should resolve to |
|---|---|---|---|
| WABC (770, NYC) | AM | CDBS backfill | 50kW day+night, non-directional, Lodi NJ site (~40.88, -74.07) |
| WFAN (660, NYC) | AM | LMS | 50kW day+night, non-directional, Meadowlands NJ |
| WKTU (103.5, NYC) | FM | LMS | 8.5kW ERP, 415m HAAT, non-directional, Empire State Building site |
| WMOC (88.7, Lumber City GA) | FM | CDBS backfill | 50kW ERP (Class C2), 64m HAAT |

## AM groundwave curves: FCC's own Graphs 1-20, not GRWAVE

`scripts/am_groundwave.py` used to shell out to the `grwave` Python package (`git+https://github.com/space-physics/grwave`), which compiles a 1985 Fortran file carrying an unresolved corporate copyright claim (`COPYRIGHT (C) GEC PLC 1985`) with no accompanying license anywhere in that repo - a real problem for a dependency a public CI workflow re-downloads and compiles weekly. Replaced with `scripts/fcc_groundwave_curves.py`: the actual FCC groundwave curves under 47 CFR 73.184/73.190 ("Graphs 1-20"), a public domain U.S. government work and literally the regulatory basis GRWAVE was only ever a numerical stand-in for.

- The 20 graph PDFs (one per representative AM frequency) were downloaded from `fcc.gov/media/radio/am-groundwave-field-strength-graphs` - `fcc.gov` 403s a plain `curl`/`WebFetch` the same way other FCC hosts do (see below), so this needed a real browser. One-time acquisition, not a recurring fetch - these regulatory graphs don't change.
- They're vector PDFs, not scans: the digitization script reads the embedded vector paths and axis-tick text directly (pixel-exact, not manually traced) to extract the 3 mS/m conductivity curve - this app's existing single "average US land" assumption - from each of the 20 frequency graphs. Cross-validated against the graphs' own printed "100 mV/m at 1 km" reference line (reproduced to within 1.2%) and against continuity between each graph's near-range (0.1-50km) and far-range (10-5000km) panels at their overlap point.
- FCC's curves are normalized to "100 mV/m unattenuated at 1 km," not tied to a specific real power. Converting to real station kW uses the standard AM broadcast industry constant of 305.768 mV/m at 1 km per kW for a quarter-wave monopole (so FCC's reference corresponds to ~107 W) - sourced from two independent broadcast-engineering references, not derived from first principles.
- **This produces materially different AM range numbers than the old GRWAVE-based curve** - not a rounding-level change. Cross-checking WABC (770kHz, 50kW) at 20 dBu: 405km (old) vs 434km (new), a modest 7% shift; but at higher thresholds the old GRWAVE curve simply never reached values above ~55 dBu-equivalent within its computed range (coming back `null`), while the new FCC-curve-based numbers reach cleanly up to 80 dBu (e.g. WABC city-grade/70dBu range: undefined under the old model, ~57km under the new one). The two curves almost certainly assume different reference antennas internally (GRWAVE models a generic near-ground theoretical source per its `TRANSMITTER_HEIGHT_M = 0`; FCC's graphs are calibrated to a real efficient broadcast tower) - this was a known, accepted tradeoff when making the switch, not an oversight, but it means stations will show as receivable at meaningfully larger radii at high signal-strength thresholds than they did before.

## Deliberately deferred, not forgotten

- **No terrain-aware propagation.** AM uses one national-average ground conductivity assumption (FCC's own 3 mS/m standard curve, see above) rather than FCC's real M3 conductivity map. This systematically *understates* range for stations actually sited on high-conductivity ground (e.g. WABC's real Meadowlands marsh site) and overstates it for stations on poor ground.
- **No directional antenna modeling.** Every station is treated as omnidirectional for reception purposes, even though the data carries a `directional` flag per station (currently unused by the frontend).
- **No AM nighttime skywave/DX modeling.** Out of scope by design - flagged in the UI disclaimer text, not modeled.
- **No failure alerting** on the scheduled workflow - if FCC changes their file layout or Akamai tightens further, the weekly run just silently fails until someone checks the Actions tab.
- 2 AM and ~1 FM station don't resolve even with CDBS backfill. Not investigated further - low priority given the scale (15,352 of 15,355 resolve).

## `data/plus4/*.json` and `data/plus4/manifest.json` are build artifacts

They're regenerated (and committed) by `build-station-data.yml` on every run. Don't hand-edit them expecting it to stick - the next scheduled run (or manual dispatch) overwrites them from scratch.
