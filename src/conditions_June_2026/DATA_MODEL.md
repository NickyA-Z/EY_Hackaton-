# Processed data model (`data/processed/`)

What the ingest layer (`ingest/`) produces from the files in `data/raw/`, and how to use it.

```
data/raw/  (4 native formats)  ──►  ingest/<source>.py parse()  ──►  run.py  ──►  data/processed/
  metar/*.csv          METAR text                                      observations.parquet
  noaa_coops/*.csv     CO-OPS CSV                                      tide_events.parquet
  ndbc/*.txt.gz        NDBC fixed-width
  open_meteo/*.json    Open-Meteo JSON
```

Regenerate with:

```bash
cd src/conditions_June_2026
../../.venv/bin/python ingest/run.py        # writes parquet + prints a verification report
../../.venv/bin/python -m pytest -q         # parser tests
```

---

## 1. `observations.parquet`

**One row = one source × one location × one timestamp.** It is a long (tidy) table: every
source has the same columns. A source that doesn't measure a quantity leaves that column empty (NaN).

| column | type | unit / meaning |
|---|---|---|
| `time_utc` | datetime, tz = UTC | observation time |
| `lat`, `lon` | float | WGS84 position of the station / buoy / grid cell |
| `source` | string | `metar`, `coops`, `ndbc`, `open_meteo` (later: `gpx`, `debrief`, …) |
| `source_id` | string | station id, buoy id or point name |
| `wind_dir_deg` | float | direction the wind blows **from**, 0–360°. NaN when the wind is calm or variable |
| `wind_speed_kn` | float | knots |
| `wind_gust_kn` | float | knots, nullable |
| `air_temp_c` | float | °C, nullable |
| `water_temp_c` | float | °C, nullable |
| `wave_height_m` | float | significant wave height in m, nullable |
| `cloud_cover_pct` | float | 0–100 %, nullable |
| `is_sample` | bool | `True` for hand-made sample files (no real coach data yet) |

Key: `(source, source_id, time_utc)` is unique.

### Example (2026-06-15, 21:00 UTC = 14:00 local time)

| time_utc | source | source_id | dir° | kn | gust | air °C | water °C | wave m | cloud % |
|---|---|---|---|---|---|---|---|---|---|
| 21:00 | coops | 9410665 | 254 | 18.7 | 19.4 | | | | |
| 21:00 | coops | 9410670 | 276 | 2.7 | 3.9 | 24.5 | | | |
| 21:53 | metar | LGB | 300 | 10.0 | 17.0 | 24.4 | | | 0 |
| 21:00 | ndbc | 46025 | 270 | 10.1 | 12.2 | 16.7 | 19.0 | | |
| 21:26 | ndbc | 46222 | | | | | 20.1 | 0.7 | |
| 21:00 | open_meteo | racecourse_belmont | 246 | 7.7 | 21.0 | 25.9 | | | 4 |

### What each source contributes

| source | source_id(s) | location | time step | provides |
|---|---|---|---|---|
| `metar` | `LGB` | Long Beach Airport (33.8118, -118.1472) | hourly at :53, plus specials | wind, gust, air temp, cloud cover |
| `coops` | `9410665` Pier J, `9410670` Pier F, `9410692` Pier S | Port of Long Beach piers | hourly | wind, gust; air temp at 9410670 only |
| `ndbc` | `46025` Santa Monica Basin | offshore (33.765, -119.077) | 10 min | wind, gust, air & water temp, waves (hourly) |
| `ndbc` | `46222` San Pedro | (33.614, -118.314) | 30 min | water temp, waves only (no anemometer) |
| `open_meteo` | `racecourse_belmont`, `outside_breakwater`, `shore_belmont`, `inland_lakewood`, `palos_verdes` | model grid cell (see caveats) | hourly | wind, gust, air temp, cloud cover |

### Current contents (June 2021–2026)

| source | rows | first | last |
|---|---|---|---|
| coops | 11,187 | 2021-06-01 00:00 | 2026-06-30 23:00 |
| metar | 5,044 | 2021-06-01 00:53 | 2026-06-30 23:53 |
| ndbc | 34,514 | 2021-06-01 00:00 | 2026-06-30 23:56 |
| open_meteo | 21,360 | 2021-06-01 08:00 | 2026-06-30 23:00 |
| **total** | **72,105** | | |

June 2026 is the "live" replay month; June 2021–2025 is history for statistics.

---

## 2. `tide_events.parquet`

Tide **predictions** for high and low water. These are events, not observations, so they live in a separate table.

| column | type | meaning |
|---|---|---|
| `time_utc` | datetime, tz = UTC | time of high / low water |
| `station_id` | string | `9410660` (Los Angeles) |
| `height_m` | float | metres above **MLLW** |
| `type` | string | `H` = high, `L` = low |

696 rows (about 4 per day). Example:

| time_utc | station_id | height_m | type |
|---|---|---|---|
| 2026-06-15 04:03 | 9410660 | 2.188 | H |
| 2026-06-15 11:30 | 9410660 | -0.572 | L |
| 2026-06-15 18:09 | 9410660 | 1.172 | H |
| 2026-06-15 22:31 | 9410660 | 0.656 | L |

---

## 3. What happens to the raw values

### Per-source parsing

| raw input | becomes |
|---|---|
| METAR string `30010G17KT … 24/12 … RMK … T02440122` | dir 300, speed 10, gust 17, air temp 24.4 (the precise RMK T-group is preferred over `24/12`) |
| METAR `00000KT` (calm) | speed 0, dir NaN |
| METAR `VRB03KT` (variable) | speed 3, dir NaN |
| METAR `150V230` variability group | recognised but not stored |
| METAR sky `FEW / SCT / BKN / OVC` | 18.75 / 43.75 / 75 / 100 % (oktas midpoint); highest layer wins |
| METAR duplicate minute with `MADISHF` copy | the regular report is kept |
| CO-OPS ` Speed`, ` Gust` (m/s) | × 1.94384 → knots |
| CO-OPS two ` Direction` columns | the numeric one is used; compass text (`SW`) is ignored |
| NDBC `WSPD`, `GST` (m/s) | × 1.94384 → knots |
| NDBC `999`, `99.0`, `99.00`, `9999.0`, `MM` | NaN |
| NDBC annual file (Jan–Dec) | only requested months kept |
| Open-Meteo local `time` + `utc_offset_seconds` | UTC |
| Open-Meteo speeds (already in kn) | unchanged; other units would be converted |
| Station ids (CO-OPS, NDBC, METAR) | lat/lon from `ingest/config.py` |

All unit conversions are in `ingest/units.py`.

### Steps in `run.py` after parsing

1. **Month filter:** rows outside the requested UTC months (default June) are dropped. This removes 240 Open-Meteo rows that fall on 1 July in UTC.
2. **Empty rows dropped:** rows with no measurement at all are removed. This removes 2,054 rows, mostly CO-OPS hours where the sensor was offline.
3. **Merge:** rows with the same key are combined, taking the first non-null value per column. This is how CO-OPS `wind` and `air_temperature` files for the same station and hour become one row (4,038 merges).
4. **Calm rule:** `wind_dir_deg` is set to NaN wherever `wind_speed_kn == 0`, for every source.
5. **Validation:** dtypes, required columns, plausible ranges (wind direction 0–360, wind speed 0–60 kn, …) and no duplicate keys. The run exits non-zero if a check fails.

---

## 4. Caveats: read before analysing

- **Open-Meteo points overlap.** `racecourse_belmont`, `outside_breakwater` and `shore_belmont` all snap to the same grid cell (33.7786, -118.097). Their data is identical except air temperature, so on a map they are one point, not three. `lat`/`lon` are the grid cell, not the requested point.
- **Open-Meteo time offset is GMT-8, not PDT.** The files state `utc_offset_seconds = -28800`. This was verified by re-requesting with `timezone=GMT`. As a consequence, Open-Meteo has no data for 1 June 00:00–07:00 UTC in each year.
- **No water temperature from CO-OPS.** The nearby stations don't offer that product, so `water_temp_c` comes only from the NDBC buoys.
- **CO-OPS units are assumed.** The CSVs don't state units; they are metric because the downloader requests `units=metric`.
- **Mixed time steps.** METAR is about hourly, NDBC is every 10 or 30 minutes, the others are hourly. Resample before comparing sources, e.g. `df.set_index("time_utc").groupby("source_id").resample("1h").mean(numeric_only=True)`.
- **Pier stations differ a lot.** The piers are close together but their winds disagree strongly (e.g. Pier J 18.7 kn vs Pier F 2.7 kn in the same hour). This is not yet explained: it could be exposure or sheltering by port structures.
- **Missing share per source:** METAR direction 21 % (calm or VRB), NDBC wind 25 % (46222 has no anemometer), CO-OPS air temperature 64 % (only one station measures it).
- **Tide heights are MLLW-referenced.** The datum is not stored as a column.

---

## 5. Using the data

```python
import pandas as pd

obs = pd.read_parquet("data/processed/observations.parquet")
tides = pd.read_parquet("data/processed/tide_events.parquet")

# Local time for display (America/Los_Angeles, DST-aware)
obs["time_local"] = obs["time_utc"].dt.tz_convert("America/Los_Angeles")

# Mean wind by local hour of day, per location (history only)
hist = obs[obs["time_utc"].dt.year < 2026]
diurnal = (hist.groupby(["source_id", hist["time_local"].dt.hour])["wind_speed_kn"]
               .mean().unstack(0).round(1))

# "Live" replay: latest observation per location at a given moment
now = pd.Timestamp("2026-06-15 21:00", tz="UTC")
latest = (obs[obs["time_utc"] <= now].sort_values("time_utc")
             .groupby(["source", "source_id"]).tail(1))

# Tides during a race window
race = tides[tides["time_utc"].between("2026-06-15 18:00Z", "2026-06-16 01:00Z")]
```

---

## 6. Adding a new data format

The product's main point is that any coach file can join the same table:

1. Create `ingest/<format>.py` with `parse(path) -> DataFrame` that ends with
   `return schema.conform(df)`. Set `source`, `source_id`, `lat`/`lon` and
   `is_sample=True` for hand-made samples.
2. Add one `Source(...)` line in `ingest/registry.py`.
3. Add a tiny fixture and a test in `tests/`.

`run.py` warns about any file in `data/raw/` that no parser claims, so new formats don't go unnoticed.
