#!/usr/bin/env python3
"""
Step 1 - ingest + standardise.

Reads every July time-series source in the repo (native formats) and writes ONE long table:

    data/location_agent/conditions_july.parquet

  column     meaning
  ---------  ----------------------------------------------------------------
  time_utc   timestamp, UTC (timezone-aware)
  site       short site key (see SITES)
  lat, lon   WGS84 position of the site
  variable   wind_speed | wind_gust | wind_dir_from | air_temp | water_temp |
             wave_height | wave_period | wave_dir_from | tack_angle |
             tide_height | tide_high | tide_low | current_speed | current_dir_to
  value      number in the unit below
  unit       kn (speed), deg (direction the wind/waves come FROM), deg_towards (current flows TO),
             degC, m, m_MLLW (tide height above chart datum), s
  source     hrrr | hrrr_dayahead | coops | ndbc | open_meteo | gps
  quality    model | forecast_day_ahead | measured | predicted | gps_derived

Sources:
  data/location_agent/raw/hrrr/*.json            HRRR model, 15 min (local time)
  data/location_agent/raw/hrrr_dayahead/*.json   HRRR forecast issued ~24 h ahead, hourly (from 2024)
  data/location_agent/raw/noaa_coops/*.csv       CO-OPS stations, hourly, m/s, GMT
  data/location_agent/raw/noaa_coops/9410660_predictions-*  tide predictions (hourly + high/low), GMT
  data/location_agent/raw/open_meteo_marine/*.json  modelled surface current, hourly, GMT, km/h
  data/weather/raw/ndbc/*.txt.gz     NDBC buoys (yearly files; July rows), UTC, m/s
  data/location_agent/gps_results/wind_from_gps.csv  wind derived from race tracks (19 Jul 2026)

Run from the repo root:  PYTHONPATH=src python -m backend.location_agent.ingest
"""
from __future__ import annotations

import csv
import gzip
import json

import numpy as np
import pandas as pd

from backend import paths

ROOT = paths.ROOT
OUT = paths.LOCATION_AGENT_CONDITIONS_FILE
TZ = "America/Los_Angeles"
MS_TO_KN = 1.94384
MONTH = 7

HRRR_DIR = paths.LOCATION_AGENT_RAW_DIR / "hrrr"
HRRR_DAYAHEAD_DIR = paths.LOCATION_AGENT_RAW_DIR / "hrrr_dayahead"
HRRR_CLOUD_DIR = paths.LOCATION_AGENT_RAW_DIR / "hrrr_cloud"
HRRR_CLOUD_DAYAHEAD_DIR = paths.LOCATION_AGENT_RAW_DIR / "hrrr_cloud_dayahead"
COOPS_DIR = paths.LOCATION_AGENT_RAW_DIR / "noaa_coops"
NDBC_DIR = paths.CONDITIONS_RAW_DIR / "ndbc"
GPS_WIND = paths.LOCATION_AGENT_GPS_RESULTS_DIR / "wind_from_gps.csv"
MARINE_DIR = paths.LOCATION_AGENT_RAW_DIR / "open_meteo_marine"
KMH_TO_KN = 0.539957

# site key -> (lat, lon, description). HRRR positions are replaced by the model grid cell actually used.
SITES = {
    "port_la_course":   (33.687, -118.271, "HRRR sea cell at the Port of LA boat course"),
    "belmont_course":   (33.748, -118.140, "HRRR sea cell at the Belmont Shore board course"),
    "inland_lakewood":  (33.850, -118.130, "HRRR land cell inland (land temperature)"),
    "angels_gate":      (33.71583, -118.24611, "CO-OPS 9410647 Angels Gate (breakwater entrance)"),
    "pier_400":         (33.735195, -118.2413, "CO-OPS 9410666 Los Angeles Pier 400"),
    "pier_j":           (33.733, -118.18569, "CO-OPS 9410665 Long Beach Pier J"),
    "buoy_46222":       (33.614, -118.314, "NDBC 46222 San Pedro (waves, sea temperature)"),
    "buoy_46025":       (33.765, -119.077, "NDBC 46025 Santa Monica Basin (offshore wind, waves)"),
    "course_gps":       (33.687, -118.271, "Wind derived from ILCA GPS tracks, 19 Jul 2026"),
    "tide_los_angeles": (33.72, -118.272, "CO-OPS 9410660 Los Angeles tide predictions"),
}
COOPS_SITE = {"9410647": "angels_gate", "9410666": "pier_400", "9410665": "pier_j"}


def _frame(t_utc, site, variable, values, unit, source, quality):
    lat, lon, _ = SITES[site]
    v = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    return pd.DataFrame({"time_utc": t_utc, "site": site, "lat": lat, "lon": lon, "variable": variable,
                         "value": v, "unit": unit, "source": source, "quality": quality})


def load_hrrr() -> list[pd.DataFrame]:
    out = []
    for f in sorted(HRRR_DIR.glob("*_*.json")):
        site = f.stem.rsplit("_", 1)[0]
        d = json.loads(f.read_text(encoding="utf-8"))
        SITES[site] = (round(d["latitude"], 5), round(d["longitude"], 5), SITES[site][2])  # actual grid cell
        m = d["minutely_15"]
        t = pd.to_datetime(m["time"]).tz_localize(TZ, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
        for src_var, var, unit in (("wind_speed_10m", "wind_speed", "kn"), ("wind_gusts_10m", "wind_gust", "kn"),
                                   ("wind_direction_10m", "wind_dir_from", "deg"), ("temperature_2m", "air_temp", "degC")):
            out.append(_frame(t, site, var, m[src_var], unit, "hrrr", "model"))
    return out


def load_hrrr_dayahead() -> list[pd.DataFrame]:
    """HRRR forecasts issued ~24 h ahead (Open-Meteo previous-runs API), hourly, local time.
    Stored under their own site key '<point>_dayahead' so they never mix with near-real-time HRRR."""
    out = []
    for f in sorted(HRRR_DAYAHEAD_DIR.glob("*_*.json")):
        point = f.stem.rsplit("_", 1)[0]
        site = f"{point}_dayahead"
        d = json.loads(f.read_text(encoding="utf-8"))
        SITES[site] = (round(d["latitude"], 5), round(d["longitude"], 5), f"HRRR day-ahead forecast (issued ~24 h before) at {point}")
        h = d["hourly"]
        t = pd.to_datetime(h["time"]).tz_localize(TZ, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
        for src_var, var, unit in (("wind_speed_10m", "wind_speed", "kn"), ("wind_gusts_10m", "wind_gust", "kn"),
                                   ("wind_direction_10m", "wind_dir_from", "deg"), ("temperature_2m", "air_temp", "degC")):
            out.append(_frame(t, site, var, h[f"{src_var}_previous_day1"], unit, "hrrr_dayahead", "forecast_day_ahead"))
    return out


def load_cloud() -> list[pd.DataFrame]:
    """HRRR hourly cloud cover (%), near-real-time (total + low = marine layer) and day-ahead (total only:
    the previous-runs API returns no low-cloud values). Same site keys as the wind ('<point>', '<point>_dayahead')."""
    out = []
    for folder, suffix, source, quality in ((HRRR_CLOUD_DIR, "", "hrrr", "model"),
                                            (HRRR_CLOUD_DAYAHEAD_DIR, "_previous_day1", "hrrr_dayahead", "forecast_day_ahead")):
        for f in sorted(folder.glob("*_*.json")):
            point = f.stem.rsplit("_", 1)[0]
            site = point + ("_dayahead" if suffix else "")
            if site not in SITES:
                d0 = json.loads(f.read_text(encoding="utf-8"))
                SITES[site] = (round(d0["latitude"], 5), round(d0["longitude"], 5), f"HRRR day-ahead forecast (issued ~24 h before) at {point}")
            h = json.loads(f.read_text(encoding="utf-8"))["hourly"]
            t = pd.to_datetime(h["time"]).tz_localize(TZ, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
            for var in ("cloud_cover", "cloud_cover_low"):
                vals = h.get(var + suffix)
                if vals is not None and any(v is not None for v in vals):
                    out.append(_frame(t, site, var, vals, "%", source, quality))
    return out


def load_coops() -> list[pd.DataFrame]:
    out = []
    for f in sorted(COOPS_DIR.glob("*_*_*.csv")):
        sid, rest = f.stem.split("_", 1)
        product = rest.rsplit("_", 1)[0]
        if sid not in COOPS_SITE:          # tide predictions are loaded by load_tides()
            continue
        rows = list(csv.reader(open(f, encoding="utf-8")))[1:]
        rows = [r for r in rows if r and r[0][:2] == "20"]
        t = pd.to_datetime([r[0] for r in rows]).tz_localize("UTC")
        site = COOPS_SITE[sid]
        if product == "wind":  # Date Time, Speed (m/s), Direction (deg), Direction (text), Gust, X, R
            spd = pd.to_numeric([r[1] for r in rows], errors="coerce") * MS_TO_KN
            gst = pd.to_numeric([r[4] for r in rows], errors="coerce") * MS_TO_KN
            out += [_frame(t, site, "wind_speed", spd, "kn", "coops", "measured"),
                    _frame(t, site, "wind_gust", gst, "kn", "coops", "measured"),
                    _frame(t, site, "wind_dir_from", [r[2] for r in rows], "deg", "coops", "measured")]
        elif product in ("air_temperature", "water_temperature"):
            var = "air_temp" if product == "air_temperature" else "water_temp"
            out.append(_frame(t, site, var, [r[1] for r in rows], "degC", "coops", "measured"))
    return out


NDBC_COLS = {"WDIR": ("wind_dir_from", "deg", 1.0, 999), "WSPD": ("wind_speed", "kn", MS_TO_KN, 99),
             "GST": ("wind_gust", "kn", MS_TO_KN, 99), "WVHT": ("wave_height", "m", 1.0, 99),
             "DPD": ("wave_period", "s", 1.0, 99), "MWD": ("wave_dir_from", "deg", 1.0, 999),
             "WTMP": ("water_temp", "degC", 1.0, 999), "ATMP": ("air_temp", "degC", 1.0, 999)}


def load_ndbc() -> list[pd.DataFrame]:
    out = []
    for f in sorted(NDBC_DIR.glob("*.txt.gz")):
        bid = f.name.split("_")[0]
        site = f"buoy_{bid}"
        with gzip.open(f, "rt") as fh:
            header = fh.readline().lstrip("#").split()
            fh.readline()  # units line
            df = pd.read_csv(fh, sep=r"\s+", names=header, dtype=str)
        df = df[pd.to_numeric(df["MM"], errors="coerce") == MONTH]
        if df.empty:
            continue
        t = pd.to_datetime(dict(year=df["YY"].astype(int), month=df["MM"].astype(int), day=df["DD"].astype(int),
                                hour=df["hh"].astype(int), minute=df["mm"].astype(int))).dt.tz_localize("UTC")
        for col, (var, unit, k, missing) in NDBC_COLS.items():
            if col not in df:
                continue
            v = pd.to_numeric(df[col], errors="coerce")
            v = v.where(v < missing) * k
            out.append(_frame(t.to_numpy(), site, var, v, unit, "ndbc", "measured"))
    return out


def load_tides() -> list[pd.DataFrame]:
    """CO-OPS tide predictions, Los Angeles 9410660, metres above MLLW, GMT.
    hourly -> tide_height; high/low -> tide_high / tide_low events (value = height)."""
    out = []
    for f in sorted(COOPS_DIR.glob("9410660_predictions-*_*.csv")):
        interval = f.stem.split("_")[1].split("-")[1]
        rows = [r for r in list(csv.reader(open(f, encoding="utf-8")))[1:] if r and r[0][:2] == "20"]
        t = pd.to_datetime([r[0] for r in rows]).tz_localize("UTC")
        h = [r[1] for r in rows]
        if interval == "h":
            out.append(_frame(t, "tide_los_angeles", "tide_height", h, "m_MLLW", "coops", "predicted"))
        else:
            kind = np.array([r[2].strip() for r in rows])
            for k, var in (("H", "tide_high"), ("L", "tide_low")):
                m = kind == k
                out.append(_frame(t[m], "tide_los_angeles", var, np.array(h)[m], "m_MLLW", "coops", "predicted"))
    return out


def load_currents() -> list[pd.DataFrame]:
    """Open-Meteo marine modelled surface current, hourly, GMT. km/h -> kn; direction = flowing TOWARDS."""
    out = []
    for f in sorted(MARINE_DIR.glob("*_*.json")):
        point = f.stem.rsplit("_", 1)[0]
        site = f"current_{point}"
        d = json.loads(f.read_text(encoding="utf-8"))
        SITES[site] = (round(d["latitude"], 5), round(d["longitude"], 5), f"Open-Meteo marine model cell nearest {point}")
        h = d["hourly"]
        t = pd.to_datetime(h["time"]).tz_localize("UTC")
        k = KMH_TO_KN if d["hourly_units"]["ocean_current_velocity"] == "km/h" else 1.0
        spd = pd.to_numeric(pd.Series(h["ocean_current_velocity"]), errors="coerce") * k
        out += [_frame(t, site, "current_speed", spd, "kn", "open_meteo", "model"),
                _frame(t, site, "current_dir_to", h["ocean_current_direction"], "deg_towards", "open_meteo", "model")]
    return out


def load_gps_wind() -> list[pd.DataFrame]:
    if not GPS_WIND.exists():
        return []
    d = pd.read_csv(GPS_WIND)
    t = pd.to_datetime(d["time"], utc=True)
    return [_frame(t, "course_gps", "wind_dir_from", d["twd_gps"], "deg", "gps", "gps_derived"),
            _frame(t, "course_gps", "tack_angle", d["tack_angle"], "deg", "gps", "gps_derived")]


def build() -> pd.DataFrame:
    parts = load_hrrr() + load_hrrr_dayahead() + load_cloud() + load_coops() + load_ndbc() + load_tides() + load_currents() + load_gps_wind()
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["time_utc", "value"])
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    # refresh HRRR site coordinates with the grid cell actually used
    for site, (lat, lon, _) in SITES.items():
        m = df["site"] == site
        df.loc[m, "lat"], df.loc[m, "lon"] = lat, lon
    df = df.sort_values(["site", "variable", "time_utc"]).drop_duplicates(["site", "variable", "time_utc"])
    return df.reset_index(drop=True)


def main():
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    (OUT.parent / "sites.json").write_text(json.dumps(
        {k: {"lat": v[0], "lon": v[1], "description": v[2]} for k, v in SITES.items()}, indent=2))
    summ = (df.assign(year=df.time_utc.dt.year)
              .groupby(["source", "quality", "site", "variable", "unit"])
              .agg(rows=("value", "size"), years=("year", lambda s: f"{s.min()}-{s.max()}"),
                   min=("value", "min"), max=("value", "max")).reset_index())
    pd.set_option("display.width", 200)
    print(summ.to_string(index=False))
    print(f"\n{len(df):,} rows -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
