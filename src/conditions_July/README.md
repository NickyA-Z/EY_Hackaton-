# July conditions (2021–2026): wind, temperature, tides and currents at the LA28 race courses

This is the companion to `../conditions_June_2026/`, using the same style and native file formats. It covers **July only**, the LA28 sailing month (16–28 July 2028), and focuses on the **Port of LA boat course**, the real 2026 test-event course taken from the GPS tracks in `sailsync_api_results/`, plus Belmont.

## Sources
| # | Source | Format | Points / stations | Cadence |
|---|---|---|---|---|
| 1 | **NOAA HRRR model** via Open-Meteo historical-forecast API (`models=ncep_hrrr_conus`) | JSON (`minutely_15`) | `port_la_course` 33.687, −118.271 · `belmont_course` 33.748, −118.140 (both **sea** cells) · `inland_lakewood` 33.850, −118.130 (land cell) | 15 min |
| 2 | **NOAA CO-OPS measured stations** | CSV (metric, GMT) | 9410647 Angels Gate · 9410666 Los Angeles Pier 400 · 9410665 Long Beach Pier J | hourly |
| 3 | **NOAA CO-OPS tide predictions** (`product=predictions`, MLLW) | CSV (metric, GMT) | 9410660 Los Angeles | hourly + high/low |
| 4 | **Open-Meteo marine surface current** (model) | JSON (GMT) | cells nearest `port_la_course` (33.708, −118.292) and `belmont_course` | hourly, from 2022 |
| 5 | **HRRR day-ahead forecast** via Open-Meteo previous-runs API (`*_previous_day1`) | JSON | same 3 HRRR points | hourly, from 2024 |
| 6 | **HRRR cloud cover** (`cloud_cover`, `cloud_cover_low`, %), historical-forecast API, plus the day-ahead `cloud_cover_previous_day1` from the previous-runs API | JSON | same 3 HRRR points | hourly; day-ahead from 2024 |

- Cloud cover:
  - `cloud_cover_low` is the marine layer ("June gloom"). Morning low cloud delays land heating, which makes the sea breeze later and weaker.
  - The previous-runs (day-ahead) API **returns no values for `cloud_cover_low`**, so the day-ahead files only have **total** cloud. At this coast, total and low cloud are almost identical in the morning (19 Jul 2026: 100 % until 08:00 at both, 7 % at 11:00).

- Tides: `Prediction` = metres above MLLW (chart datum). The high/low file adds `Type` = H/L. These are exact harmonic predictions.
- Currents: `ocean_current_velocity` is in km/h (the ingest converts to kn); `ocean_current_direction` is the direction the water flows **towards**. It's a coarse model (several km), so treat it as background drift only. NOAA has no current station on the course; the nearest current-prediction station, Queens Gate, is in the Long Beach harbour channel 8.6 km away.

- HRRR variables: `wind_speed_10m` (kn), `wind_direction_10m` (°, direction the wind comes from), `wind_gusts_10m` (kn), `temperature_2m` (°C). Times are local (America/Los_Angeles).
- CO-OPS: `wind` (Speed in m/s, Direction in °, Gust) at all three stations. `air_temperature` at Angels Gate only. **No `water_temperature`** at these stations; use NDBC buoy water temperature in `../conditions_June_2026/data/raw/ndbc/` (those yearly files include July). Times are GMT (PDT = GMT − 7 h).
- **Why sea cells:** by default Open-Meteo picks a land grid cell near the coast, which underestimates over-water wind. `cell_selection=sea` fixes this.

## Files
```
fetch_july.py                  re-run the pull
data/raw/hrrr/<point>_<YYYY07>.json
data/raw/noaa_coops/<station>_<product>_<YYYY07>.csv
data/raw/noaa_coops/stations.json
data/raw/noaa_coops/9410660_predictions-h_<YYYY07>.csv      tide, hourly
data/raw/noaa_coops/9410660_predictions-hilo_<YYYY07>.csv   tide, high/low
data/raw/open_meteo_marine/<point>_<YYYY07>.json            current, hourly
data/raw/hrrr_dayahead/<point>_<YYYY07>.json                day-ahead wind / temperature, 2024+
data/raw/hrrr_cloud/<point>_<YYYY07>.json                   cloud cover (total + low), hourly
data/raw/hrrr_cloud_dayahead/<point>_<YYYY07>.json          day-ahead total cloud, 2024+
```

## Check against race day (19 July 2026, San Pedro test regatta)
| PDT | HRRR at course | Angels Gate measured |
|---|---|---|
| 12:00 | 11.7 kt, 252° | 11.3 kt, 226° |
| 14:00 | 14.8 kt, 259° | 11.7 kt, 231° |
| 16:00 | 17.6 kt, 267° | 12.2 kt, 245° |
| 17:00 | 15.2 kt, 268° | 16.7 kt, 250° |

- **Speed: HRRR is usable** (World Sailing reported 12–18 kt).
- **Direction:** the GPS tracks show the wind *on the course* was 266–274° (see `strategy/gps_analysis/FINDINGS.md`).
  - **HRRR matches that (within ~5–10°).**
  - **Angels Gate reads 25–40° too far left**, probably bent locally by the breakwater and Palos Verdes.
  - So use **HRRR for course direction**, and the station only for **trend and timing**: it shows the sea-breeze veer of about +5°/h.

## Completeness (pulled 2026-11-05)
- **HRRR:** all 18 point-months complete (2,976 15-min rows each, no missing values).
- **CO-OPS:** 24 CSVs. **2025–2026 are complete.** In **2021–2024**, Angels Gate and Pier 400 have about 1/3 of hourly rows empty (~40–50 % during 11:00–18:00 PDT, spread over every day), and Pier J is patchy in 2022–2023.
  - The hourly product only takes the reading at the top of the hour.
  - Pulling the 6-minute product and averaging it per hour would probably fill most gaps (~10× larger files, roughly +4 MB).
- **Tides:** 12 files (hourly + high/low), complete. **Currents:** 12 files, values from 2022 (2021 is empty in the model).
- Total: 67 files, ~3.1 MB.
- **Cloud cover** (pulled 2026-11-06): 27 files, ~0.5 MB. All 18 near-real-time point-months are complete (744 hours each, total and low cloud). The 9 day-ahead files have complete total cloud; low cloud is empty, as described under Sources.

## Re-run
```bash
cd src/conditions_July
python fetch_july.py
python fetch_july.py --years 2026 --only coops
python fetch_july.py --only tides
python fetch_july.py --only currents
python fetch_july.py --only cloud
```
The only dependency is `requests`. No API keys are needed. The full pull is ~100 small requests, about 3–4 minutes.
