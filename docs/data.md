# Data

All data is in `data/`. Code never spells these folders out: it imports them from
[`src/backend/paths.py`](../src/backend/paths.py), so the second column below is the name to look for.

| Folder | `paths.py` name | What it holds | Where it came from | Read by |
| --- | --- | --- | --- | --- |
| `data/rag/` | `STRATEGY_CORPUS_DIR` | 12 Markdown files: an index (`00_README_corpus_index.md`) and team-strategy documents TS-01 to TS-11 (philosophy, wind, tide, sea breeze, venue playbook, pre-start routine) | **Synthetic**, written for the hackathon to test retrieval. Not real team material | `backend/rag`, the Previous strategy tab |
| `data/trajectories/sailsync/` | `SAILSYNC_DIR` | GPS tracks of 44 ILCA 7 boats (`2796_<id>_<name>.csv`, 4 of them in `winners/`), `trajectories.geojson`, and the API probe files (`events.json`, `probe_report.json`, `account_capabilities.json`) | SailSync, San Pedro OCR 2026, session 2796, 19 July 2026. Source URL in `winners/explain.md` | `backend/race_analysis`, `backend/previous_strategy`, `backend/ingest` |
| `data/weather/raw/` | `CONDITIONS_RAW_DIR` | Native-format files: `metar/` (airport METAR), `noaa_coops/` (tides, piers F, J, S), `ndbc/` (buoys 46222, 46025), `open_meteo/` (hourly model data at several points) | Public sources, fetched by `backend/scripts/fetch_long_beach_data.py` | `backend/ingest`, `backend/strategy`, `backend/previous_strategy` |
| `data/weather/processed/` | `CONDITIONS_PROCESSED_DIR` | `observations.parquet`, `tide_events.parquet`, `tracks.parquet`: the common tables built from the raw files | `python -m backend.ingest.run` (see [data_model.md](data_model.md)) | nothing in the app yet; only the ingest writes them |
| `data/weather/samples/` | `WEATHER_SAMPLES_DIR` | Two one-off Open-Meteo downloads for Belmont Shore: `belmont_marine_2025-11-03_2025-11-07.json` (waves, swell, current; made by `backend/scripts/get_marine_data.py`) and `belmont_hourly.json` (15-minute data; no script in the repo produced it) | Open-Meteo | nothing yet |
| `data/geo/` | `GEO_DIR` | `venues.yaml` (venues and candidate race areas) and `la28/`: bathymetry and terrain as GeoTIFF plus grid JSON in `la28/json/` | NOAA NCEI coastal DEM and Copernicus GLO-30, via `backend/geodata` (see [geodata.md](geodata.md)) | `backend/retrieval/geolocation`, the Previous strategy tab |
| `data/race_model/` | `RACE_MODEL_DIR` | Results, mark roundings and a few GPS tracks for the race model, per session | SailSync API, via `backend/race_model/fetch_data.py` | `backend/race_model` |
| `data/demo_uploads/` | `DEMO_UPLOADS_DIR` | Three sample coach uploads (debrief notes, a call transcript, a sailing-instructions excerpt) | Written for the demo | the Coach file tab |

## Not tracked (created locally)

| Path | What | How it is made |
| --- | --- | --- |
| `.chroma/` (repo root) | The RAG search index (`RAG_INDEX_DIR`) | `python -m backend.rag index`; needs an embedding API key |
| `data/weather/inbox/` | Files dropped into the inbox app, before they are confirmed | the inbox app; git-ignored |
| `data/geo/*/raw/` | Intermediate downloads of the geodata pipeline | `python -m backend.geodata.run`; git-ignored |

## Two things to know before trusting the data

- `data/trajectories/sailsync/` and `data/race_model/` both come from SailSync but are different files: the
  race-model tracks (`data/race_model/2796/tracks/`) are not copies of the ones in `sailsync/`.
- `data/weather/processed/*.parquet` were built by an earlier numpy/pandas than the one installed now. Rebuilding
  them gives the same rows and columns; only `course_deg` and `speed_kn` in `tracks.parquet` differ, by floating-point
  noise (about 1e-8 degrees).
