# geo_data: bathymetry + terrain for the race venue

This folder is the **geographic-data workstream** of the EY hackathon repo. It pulls **water depth (bathymetry)** and **land height (terrain)** for a sailing race venue and saves them as GeoTIFF and standardized JSON for the AI coach agent. Wind, weather and currents come from other workstreams.

First venue: **LA 2028 Olympic sailing**, 16–28 July 2028.
- Boards race off Belmont Shore, Long Beach.
- Boats race at the Port of Los Angeles.

Official course areas aren't published yet, so `venues.yaml` holds **candidate areas**.

## Folder layout (inside `geo_data/`)
```
README.md            this file
requirements.txt     8 Python packages
.gitignore           excludes .venv, __pycache__, data/*/raw
venues.yaml          venues + race areas (edit this to add a home venue or fix course areas)
geodata/             the scripts (see below)
data/la28/           the extracted data for LA28 (see below)
```

## Scripts (`geodata/`)
| Script | What it does |
|---|---|
| `run.py` | **Entry point.** Runs 3 steps per venue: `bathymetry` → `terrain` → `json`. Tries the best source first and falls back if it's unavailable. Writes `catalog.json`. Options: `--venue`, `--steps`, `--force`, `--list`, `--list-sources`. |
| `config.py` | Reads `venues.yaml`. Computes the boxes to fetch: race areas + 2 km for bathymetry, + 10 km for terrain (upwind hills). Detects the region (us / europe / global). `raster_matches()` decides whether a saved file still fits the areas; if you move an area, it's re-fetched. |
| `sources/ncei_dem.py` | **Bathymetry, primary.** Asks NOAA which coastal elevation models cover the box, picks the finest (LA: `orange_county_13_navd88_2015`, ~10 m) and downloads only our box through NOAA's API. Saves `bathymetry_ncei.tif` and `bathymetry_ncei.meta.json`. |
| `sources/http.py` | Network helpers: an HTTP session with retries, and parallel tiled download from an ArcGIS image service (NOAA's server is slow with big requests, so it fetches 500-px tiles 6 at a time). |
| `bathy.py` | **Bathymetry, fallback** for venues without a NOAA coastal model (outside the US). Uses NOAA ETOPO 2022 (global, ~450 m), plus EMODnet (~115 m) for Europe. |
| `dem.py` | **Terrain.** Reads only our box from the Copernicus GLO-30 cloud files on AWS (~30 m, global). Saves `terrain.tif`. |
| `export_json.py` | **Standardization.** Converts each GeoTIFF into grid JSON (see the format below). Deterministic, offline, no AI. |
| `catalog.py` | Writes `data/<venue>/catalog.json`: for each dataset, the source, link, how it was accessed, licence, datum, resolution, date, box, file paths and stats. |

## Data (`data/la28/`, ~29 MB)
| File | Type | What it is |
|---|---|---|
| `json/bathymetry.json` | Grid JSON, 15.5 MB | **Main bathymetry deliverable.** 2184 × 1301 values, ~10 m spacing, race areas + 2 km. |
| `json/terrain.json` | Grid JSON, 5.6 MB | **Main terrain deliverable.** 1350 × 951 values, ~30 m spacing, race areas + 10 km. |
| `bathymetry_ncei.tif` | GeoTIFF, float32, 7.1 MB | The same bathymetry in raster form, for GIS tools (QGIS, rasterio). |
| `terrain.tif` | GeoTIFF, float32, 2.0 MB | The same terrain in raster form. |
| `bathymetry_ncei.meta.json` | JSON, 1 KB | Which NOAA model was chosen and the alternatives. Lets re-runs work offline. |
| `catalog.json` | JSON, ~8 KB | Metadata and stats for all of the above. |

### The two datasets
| | Bathymetry | Terrain |
|---|---|---|
| Source | NOAA NCEI coastal DEM `orange_county_13_navd88_2015` | Copernicus GLO-30 DSM (ESA / Airbus) |
| Link | https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer | https://registry.opendata.aws/copernicus-dem/ |
| Access | API call (no key), **once**, then saved | Window read of cloud files (no key), **once**, then saved |
| Data date | Model completed Sept 2015 (older surveys inside) | Satellite radar 2011–2015 |
| Time dimension | None (static snapshot) | None (static snapshot) |
| Value | Elevation in m, **negative = water depth** | Elevation in m; sea = 0; includes buildings and trees |
| Height reference | NAVD88 (US survey datum) | EGM2008 (~mean sea level) |
| Area centers | Belmont −6.8 m, Outer Harbor −15.2 m, outside breakwater −21.1 m | 0 m (sea); highest point 456 m, Palos Verdes Hills |
| Licence | US Government public domain | Copernicus DEM licence (free, with attribution) |

### Grid JSON format (`sail-geodata/grid-json v1`), the fields we'll use
Both JSON files have the same keys:
- **Identity**: `dataset` (`bathymetry` / `terrain`), `venue`, `venue_name`
- **Provenance**: `source`, `provider`, `link`, `access`, `license`, `data_date`, `extracted_at`, `converted_from`
- **Meaning of the numbers**: `value` (`elevation_m`, positive up), `units` (`m`), `vertical_datum`, `crs` (`EPSG:4326`, lat/lon), `nodata` (`null`), `resolution`
- **`grid`**: `west`, `north`, `south`, `east`, `step_deg` (cell size in degrees), `rows`, `cols`, `order`
- **`areas`**: the race areas (`key`, `lat`, `lon`, `radius_km`, `events`)
- **`stats`**: `cells`, `missing_cells`, `min`, `max`, `mean`, `below_zero_pct`, `value_at_area_centers`
- **`values`**: the data. A list of rows from north to south; each row runs west to east. Numbers are metres rounded to 0.1.

The location of `values[r][c]` (its cell center):
- lat = `north − (r + 0.5) × step_deg`
- lon = `west + (c + 0.5) × step_deg`

```python
import json, numpy as np
d = json.load(open("geo_data/data/la28/json/bathymetry.json"))   # path from the repo root
g, z = d["grid"], np.array(d["values"], dtype=float)          # z[r, c] in metres, NaN where null
def value_at(lat, lon):
    return z[int((g["north"] - lat) / g["step_deg"]), int((lon - g["west"]) / g["step_deg"])]
print(value_at(33.748, -118.140))                              # -6.8 (Belmont Shore)
```

### What the agent / coach can use it for
- **Depth** (bathymetry): water depth across each race area, shallow patches near the shore, and breakwaters and piers (positive values). These are inputs for where current and waves behave differently and for course placement.
- **Terrain**: the hills and built-up shoreline upwind of each course. Palos Verdes (456 m) lies west of the Port of LA, so in the westerly sea breeze it's the main source of wind shadow and shifts. Combine with the wind team's direction to find which parts of the course are sheltered.
- Both use plain lat/lon (EPSG:4326), so wind, current and weather data from the other teams can be looked up at the same points.

## Setup and run
All commands run from inside this folder (Windows shown; on macOS/Linux use `python3 -m venv .venv` and `.venv/bin/python`):
```bash
cd geo_data
```
```bash
py -m venv .venv
```
```bash
.venv\Scripts\python -m pip install -r requirements.txt
```
```bash
.venv\Scripts\python -m geodata.run --venue la28
```
- With the data already in `data/la28/`, this runs offline in about 2 seconds.
- Use `--force` to re-fetch from the APIs. NOAA's server can take 1–5 minutes.
- If you change an area in `venues.yaml`, the next run re-fetches automatically.
- Add a venue with the short form (`lat`, `lon`, `race_radius_km`). Outside the US the global bathymetry fallback is used (tested on Cádiz: ETOPO + EMODnet in ~3 s).
