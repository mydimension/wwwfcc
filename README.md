# What Can I Pick Up?

**[amfm.cc](https://amfm.cc)** — find which AM/FM radio stations you should be able to receive at a given location, based on real FCC license data and physical propagation models.

Click a spot on the map (or search a location, or use your device's GPS), and the app shows every station whose signal should reach you above a threshold you control, with AM and FM plotted separately and a reception-strength slider from "fringe" to "strong / city-grade."

## How it works

- **Station data** comes from the FCC's own license databases: LMS (current filings) and CDBS (the legacy system LMS replaced in 2014). Roughly 54% of licensed AM stations and 29% of licensed FM stations haven't been re-filed since the LMS migration, so this app backfills those from CDBS using `facility_id`, a stable identifier across both systems.
- **FM reception** is modeled as free-space field strength with a radio-horizon cutoff based on antenna height (HAAT).
- **AM reception** uses the FCC's own published groundwave curves (47 CFR 73.184/73.190, "Graphs 1-20") — the actual regulatory basis for AM groundwave range, digitized directly from the FCC's PDFs — rather than a generic formula, since AM groundwave propagation doesn't have one.
- Both models assume flat terrain, average ground conductivity, and no obstructions — see the in-app disclaimer for what's intentionally left out (terrain, directional antennas, AM nighttime skywave).

Station data is rebuilt weekly by a GitHub Actions workflow that pulls fresh FCC data, joins it, and partitions it into small per-region files the frontend fetches on demand as you pan around.

## Running it locally

This is a static site with no build step — `gh-pages` *is* the deployed site. Clone the repo and serve the directory with any static file server, e.g.:

```sh
python -m http.server 8000
```

then open `http://localhost:8000`.

## Repo layout

- `index.html`, `css/`, `js/` — the frontend (vanilla JS, [Leaflet](https://leafletjs.com/) for the map)
- `scripts/` — Python pipeline that fetches FCC data and builds `data/plus4/*.json` (regenerated weekly; don't hand-edit)
- `.github/workflows/` — the scheduled data-refresh workflow

See [`CLAUDE.md`](CLAUDE.md) for the deeper infra/data notes (why certain FCC hosts need special handling, known data gaps, reference stations used for regression-checking changes, etc).
