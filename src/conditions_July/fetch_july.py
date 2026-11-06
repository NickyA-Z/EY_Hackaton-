#!/usr/bin/env python3
"""
Location Agent - July wind / temperature pull for the LA28 race courses.

Companion to ../conditions_June_2026/fetch_long_beach_data.py (same style, native formats).
Pulls JULY only, for the years given (default 2021-2026):

  1. HRRR model via Open-Meteo historical-forecast API (JSON)
       - NOAA HRRR, ~3 km, every 15 min, SEA grid cells (cell_selection=sea) so the
         wind is the over-water wind, not a land cell (land cells underestimate it).
       - points: Port of LA course (from the 19 Jul 2026 ILCA GPS tracks), Belmont course,
         inland Lakewood (land cell, for the land-sea temperature difference).
  2. NOAA CO-OPS measured stations (CSV, hourly, metric, GMT)
       - wind, air temperature, water temperature at Angels Gate, Pier 400 (Port of LA
         course) and Long Beach Pier J (Belmont). Ground truth to check HRRR.
  3. NOAA CO-OPS tide predictions, Los Angeles 9410660 (hourly + high/low, MLLW)
  4. Open-Meteo marine modelled surface currents (hourly)
  5. HRRR DAY-AHEAD forecasts via Open-Meteo previous-runs API (hourly, available from 2024):
       the value for each hour as forecast by the HRRR run ~24 h earlier (`*_previous_day1`).
       This is what a coach could really have seen the day before / morning of a race.
  6. HRRR CLOUD COVER (hourly, %): total + low cloud (marine layer), near-real-time July 2021-2026,
       plus the day-ahead total cloud (2024-2026; the previous-runs API has no low-cloud values).
       Morning marine layer delays land heating -> later / weaker sea breeze.

Usage (from this folder):
  python fetch_july.py                       # July 2021-2026, all sources
  python fetch_july.py --years 2026          # quick test
  python fetch_july.py --only hrrr           # one source (hrrr, coops, tides, currents, dayahead, cloud)

All sources are free and need no API key. The script pauses between calls.
"""
import argparse
import datetime as dt
import json
import time
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "data" / "raw"
UA = {"User-Agent": "location-agent-hackathon/0.1"}
MONTH = 7  # July only

# --- HRRR points (lat, lon, cell_selection) -----------------------------------
HRRR_POINTS = {
    "port_la_course": (33.687, -118.271, "sea"),    # centre of the 19 Jul 2026 ILCA 7 GPS tracks
    "belmont_course": (33.748, -118.140, "sea"),    # boards course off Belmont Shore
    "inland_lakewood": (33.850, -118.130, "land"),  # inland temperature (sea-breeze driver)
}
HRRR_VARS = "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m"

# --- CO-OPS measured stations ---------------------------------------------------
COOPS_STATIONS = {
    "9410647": "Angels Gate",          # San Pedro breakwater entrance, next to the Port of LA course
    "9410666": "Los Angeles Pier 400",
    "9410665": "Long Beach Pier J",    # Belmont side
}
COOPS_PRODUCTS = ("wind", "air_temperature", "water_temperature")
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
HRRR_API = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            if r.status_code == 200:
                return r
            print(f"   HTTP {r.status_code}: {r.text[:120]}")
            if r.status_code in (400, 404):
                return None
        except requests.RequestException as e:
            print(f"   error: {e}")
        time.sleep(2 * (i + 1))
    return None


def july_ranges(years):
    """(first_day, last_day) of July for each year, never past yesterday."""
    yesterday = dt.date.today() - dt.timedelta(days=1)
    for y in years:
        s, e = dt.date(y, MONTH, 1), dt.date(y, MONTH, 31)
        if s <= yesterday:
            yield s, min(e, yesterday)


# 1. HRRR ------------------------------------------------------------------------
def fetch_hrrr(ranges):
    d = OUT / "hrrr"; d.mkdir(parents=True, exist_ok=True)
    print("[1] HRRR via Open-Meteo (15-min)")
    for name, (lat, lon, cell) in HRRR_POINTS.items():
        for s, e in ranges:
            params = {
                "latitude": lat, "longitude": lon, "start_date": s.isoformat(), "end_date": e.isoformat(),
                "minutely_15": HRRR_VARS, "models": "ncep_hrrr_conus", "cell_selection": cell,
                "wind_speed_unit": "kn", "timezone": "America/Los_Angeles",
            }
            r = get(HRRR_API, params)
            if r:
                (d / f"{name}_{s:%Y%m}.json").write_text(json.dumps(r.json(), separators=(",", ":")), encoding="utf-8")
                print(f"   {name} {s:%Y-%m} ok")
            time.sleep(1)


# 2. CO-OPS ----------------------------------------------------------------------
def fetch_coops(ranges):
    d = OUT / "noaa_coops"; d.mkdir(parents=True, exist_ok=True)
    print("[2] NOAA CO-OPS (hourly)")
    (d / "stations.json").write_text(json.dumps(COOPS_STATIONS, indent=2))
    for sid, sname in COOPS_STATIONS.items():
        for product in COOPS_PRODUCTS:
            for s, e in ranges:
                params = {
                    "station": sid, "product": product, "units": "metric", "time_zone": "gmt",
                    "format": "csv", "application": "location_agent_hackathon", "interval": "h",
                    "begin_date": s.strftime("%Y%m%d"), "end_date": e.strftime("%Y%m%d"),
                }
                r = get(COOPS, params)
                if r and "Error" not in r.text[:200]:
                    (d / f"{sid}_{product}_{s:%Y%m}.csv").write_text(r.text)
                elif r:
                    print(f"   {sid} {product} {s:%Y-%m}: not available ({r.text.strip()[:80]})")
                time.sleep(0.5)
            print(f"   done: {sid} {sname} {product}")


# 3. Tide predictions ---------------------------------------------------------------
TIDE_STATION = "9410660"  # Los Angeles (NOAA harmonic tide station)


def fetch_tides(ranges):
    d = OUT / "noaa_coops"; d.mkdir(parents=True, exist_ok=True)
    print("[3] NOAA CO-OPS tide predictions (hourly + high/low), MLLW")
    for interval in ("h", "hilo"):
        for s, e in ranges:
            params = {
                "station": TIDE_STATION, "product": "predictions", "datum": "MLLW", "units": "metric",
                "time_zone": "gmt", "format": "csv", "application": "location_agent_hackathon", "interval": interval,
                "begin_date": s.strftime("%Y%m%d"), "end_date": e.strftime("%Y%m%d"),
            }
            r = get(COOPS, params)
            if r and "Error" not in r.text[:200]:
                (d / f"{TIDE_STATION}_predictions-{interval}_{s:%Y%m}.csv").write_text(r.text)
                print(f"   tide {interval} {s:%Y-%m} ok")
            time.sleep(0.5)


# 4. Modelled surface currents (Open-Meteo Marine API) ---------------------------------
MARINE_API = "https://marine-api.open-meteo.com/v1/marine"
CURRENT_POINTS = {k: v for k, v in HRRR_POINTS.items() if v[2] == "sea"}


def fetch_currents(ranges):
    d = OUT / "open_meteo_marine"; d.mkdir(parents=True, exist_ok=True)
    print("[4] Open-Meteo marine currents (hourly, model)")
    for name, (lat, lon, _) in CURRENT_POINTS.items():
        for s, e in ranges:
            params = {"latitude": lat, "longitude": lon, "start_date": s.isoformat(), "end_date": e.isoformat(),
                      "hourly": "ocean_current_velocity,ocean_current_direction", "timezone": "GMT"}
            r = get(MARINE_API, params)
            if r:
                (d / f"{name}_{s:%Y%m}.json").write_text(json.dumps(r.json(), separators=(",", ":")), encoding="utf-8")
                print(f"   {name} {s:%Y-%m} ok")
            time.sleep(1)


# 5. HRRR day-ahead forecasts ----------------------------------------------------------
PREVIOUS_RUNS_API = "https://previous-runs-api.open-meteo.com/v1/forecast"
DAYAHEAD_VARS = ",".join(f"{v}_previous_day1" for v in HRRR_VARS.split(","))


def fetch_dayahead(ranges):
    d = OUT / "hrrr_dayahead"; d.mkdir(parents=True, exist_ok=True)
    print("[5] HRRR day-ahead forecasts (previous_day1, hourly; available from 2024)")
    for name, (lat, lon, cell) in HRRR_POINTS.items():
        for s, e in ranges:
            if s.year < 2024:
                continue
            params = {"latitude": lat, "longitude": lon, "start_date": s.isoformat(), "end_date": e.isoformat(),
                      "hourly": DAYAHEAD_VARS, "models": "ncep_hrrr_conus", "cell_selection": cell,
                      "wind_speed_unit": "kn", "timezone": "America/Los_Angeles"}
            r = get(PREVIOUS_RUNS_API, params)
            if r:
                (d / f"{name}_{s:%Y%m}.json").write_text(json.dumps(r.json(), separators=(",", ":")), encoding="utf-8")
                print(f"   {name} {s:%Y-%m} ok")
            time.sleep(1)


# 6. HRRR cloud cover -------------------------------------------------------------------
CLOUD_VARS = "cloud_cover,cloud_cover_low"
CLOUD_DAYAHEAD_VARS = "cloud_cover_previous_day1,cloud_cover_low_previous_day1"


def fetch_cloud(ranges):
    print("[6] HRRR cloud cover (hourly, %): near-real-time + day-ahead (from 2024)")
    jobs = (("hrrr_cloud", HRRR_API, CLOUD_VARS, 2021), ("hrrr_cloud_dayahead", PREVIOUS_RUNS_API, CLOUD_DAYAHEAD_VARS, 2024))
    for folder, api, hvars, first_year in jobs:
        d = OUT / folder; d.mkdir(parents=True, exist_ok=True)
        for name, (lat, lon, cell) in HRRR_POINTS.items():
            for s, e in ranges:
                if s.year < first_year:
                    continue
                params = {"latitude": lat, "longitude": lon, "start_date": s.isoformat(), "end_date": e.isoformat(),
                          "hourly": hvars, "models": "ncep_hrrr_conus", "cell_selection": cell,
                          "timezone": "America/Los_Angeles"}
                r = get(api, params)
                if r:
                    (d / f"{name}_{s:%Y%m}.json").write_text(json.dumps(r.json(), separators=(",", ":")), encoding="utf-8")
                    print(f"   {folder} {name} {s:%Y-%m} ok")
                time.sleep(1)


def parse_years(txt):
    if "-" in txt:
        a, b = map(int, txt.split("-"))
        return list(range(a, b + 1))
    return [int(y) for y in txt.split(",")]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--years", default="2021-2026")
    p.add_argument("--only", choices=["hrrr", "coops", "tides", "currents", "dayahead", "cloud"])
    a = p.parse_args()
    ranges = list(july_ranges(parse_years(a.years)))
    print("Months:", ", ".join(f"{s:%Y-%m}" for s, _ in ranges))
    for key, fn in (("hrrr", fetch_hrrr), ("coops", fetch_coops), ("tides", fetch_tides), ("currents", fetch_currents),
                    ("dayahead", fetch_dayahead), ("cloud", fetch_cloud)):
        if a.only in (None, key):
            fn(ranges)
    print("Done ->", OUT)
