#!/usr/bin/env python3
"""
Location Agent – Belmont Shore / Long Beach data fetcher (hackathon demo)

Demo story: "today" is June 2026.
  - June 2026            -> replayed as if live
  - June 2021–2025       -> history for the statistics / playbook

Downloads 4 public data sources in their *native* formats into data/raw/,
so the ingest layer can later show "any format -> one data model".

  1. Airport METAR (raw text)   – Iowa Environmental Mesonet, station LGB
  2. NOAA CO-OPS CSV            – tides + nearby met stations (wind, air/water temp)
  3. NDBC buoy (fixed-width)    – 46222 San Pedro (waves), 46025 Santa Monica Basin (wind)
  4. Open-Meteo JSON            – hourly reanalysis at several points (sea / shore / inland)

Usage:
  pip install requests
  python -m backend.scripts.fetch_long_beach_data                       # June 2021–2026 (default)
  python -m backend.scripts.fetch_long_beach_data --years 2026 --only openmeteo   # quick test
  python -m backend.scripts.fetch_long_beach_data --years 2019-2026 --months 5,6,7

All sources are free and need no API key. Be polite: the script sleeps between calls.
"""
import argparse
import datetime as dt
import json
import math
import time

import requests

from backend import paths

OUT = paths.CONDITIONS_RAW_DIR
UA = {"User-Agent": "location-agent-hackathon/0.1"}

# --- Points of interest (lat, lon) -------------------------------------------
POINTS = {
    "racecourse_belmont": (33.745, -118.130),
    "outside_breakwater": (33.700, -118.120),
    "shore_belmont":      (33.758, -118.135),
    "inland_lakewood":    (33.850, -118.130),
    "palos_verdes":       (33.760, -118.360),
}
CENTER = POINTS["racecourse_belmont"]


def get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            if r.status_code == 200:
                return r
            print(f"   HTTP {r.status_code}: {r.url[:120]}")
            if r.status_code == 404:
                return None
        except requests.RequestException as e:
            print(f"   error: {e}")
        time.sleep(2 * (i + 1))
    return None


def month_ranges(years, months):
    """Yield (first_day, last_day) for every selected month, never past yesterday."""
    yesterday = dt.date.today() - dt.timedelta(days=1)
    for y in years:
        for m in months:
            s = dt.date(y, m, 1)
            e = (s.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            if s > yesterday:
                continue
            yield s, min(e, yesterday)


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# 1. METAR ---------------------------------------------------------------------
def fetch_metar(ranges):
    d = OUT / "metar"; d.mkdir(parents=True, exist_ok=True)
    print("[1] METAR – Long Beach Airport (LGB)")
    for s, e in ranges:
        e1 = e + dt.timedelta(days=1)
        params = {
            "station": "LGB", "data": "metar", "tz": "Etc/UTC", "format": "onlycomma",
            "latlon": "no", "missing": "M", "trace": "T",
            "report_type": [3, 4],  # routine + specials
            "year1": s.year, "month1": s.month, "day1": s.day,
            "year2": e1.year, "month2": e1.month, "day2": e1.day,
        }
        r = get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params)
        if r:
            p = d / f"LGB_{s:%Y%m}.csv"; p.write_text(r.text)
            print(f"   {p}  ({r.text.count(chr(10))} lines)")
        time.sleep(2)


# 2. NOAA CO-OPS ---------------------------------------------------------------
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

def nearby_coops_met_stations(radius_km=25):
    r = get("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json", {"type": "met"})
    if not r:
        return []
    out = []
    for s in r.json().get("stations", []):
        dist = km(CENTER, (float(s["lat"]), float(s["lng"])))
        if dist <= radius_km:
            out.append((round(dist, 1), s["id"], s["name"]))
    return sorted(out)


def fetch_coops(ranges):
    d = OUT / "noaa_coops"; d.mkdir(parents=True, exist_ok=True)
    print("[2] NOAA CO-OPS")
    stations = nearby_coops_met_stations()
    for dist, sid, name in stations:
        print(f"   met station {sid} {name} ({dist} km)")
    (d / "stations_nearby.json").write_text(json.dumps(stations, indent=2))

    jobs = [("9410660", "predictions", {"datum": "MLLW", "interval": "hilo"})]  # LA tide predictions
    for _, sid, _ in stations[:3]:
        for product in ("wind", "air_temperature", "water_temperature"):
            jobs.append((sid, product, {"interval": "h"}))

    for sid, product, extra in jobs:
        for s, e in ranges:
            params = {
                "station": sid, "product": product, "units": "metric", "time_zone": "gmt",
                "format": "csv", "application": "location_agent_hackathon",
                "begin_date": s.strftime("%Y%m%d"), "end_date": e.strftime("%Y%m%d"), **extra,
            }
            r = get(COOPS, params)
            if r and "Error" not in r.text[:200]:
                (d / f"{sid}_{product}_{s:%Y%m}.csv").write_text(r.text)
            elif r:
                print(f"   {sid} {product} {s:%Y-%m}: {r.text.strip()[:100]}")
            time.sleep(0.5)
        print(f"   done: {sid} {product}")


# 3. NDBC buoys ----------------------------------------------------------------
BUOYS = {"46222": "San Pedro (waves)", "46025": "Santa Monica Basin (wind+waves)"}
MON_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_CODE = "123456789abc"

def fetch_ndbc(ranges):
    """Past years: one annual file. Current year: monthly files (annual not published yet)."""
    d = OUT / "ndbc"; d.mkdir(parents=True, exist_ok=True)
    print("[3] NDBC buoys")
    this_year = dt.date.today().year
    for bid, name in BUOYS.items():
        print(f"   {bid} {name}")
        done_years = set()
        for s, _ in ranges:
            if s.year < this_year:
                if s.year in done_years:
                    continue
                done_years.add(s.year)
                url = f"https://www.ndbc.noaa.gov/data/historical/stdmet/{bid}h{s.year}.txt.gz"
                fname = f"{bid}_{s.year}.txt.gz"
            else:
                url = (f"https://www.ndbc.noaa.gov/data/stdmet/{MON_ABBR[s.month-1]}/"
                       f"{bid}{MON_CODE[s.month-1]}{s.year}.txt.gz")
                fname = f"{bid}_{s:%Y%m}.txt.gz"
            r = get(url)
            if r:
                (d / fname).write_bytes(r.content); print(f"   {d / fname}")
            else:
                print(f"   not found: {url}")
            time.sleep(1)


# 4. Open-Meteo ----------------------------------------------------------------
def fetch_open_meteo(ranges):
    d = OUT / "open_meteo"; d.mkdir(parents=True, exist_ok=True)
    print("[4] Open-Meteo historical")
    hourly = ",".join([
        "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
        "temperature_2m", "pressure_msl", "cloud_cover",
    ])
    for name, (lat, lon) in POINTS.items():
        for s, e in ranges:
            params = {
                "latitude": lat, "longitude": lon,
                "start_date": s.isoformat(), "end_date": e.isoformat(),
                "hourly": hourly, "wind_speed_unit": "kn", "timezone": "America/Los_Angeles",
            }
            r = get("https://archive-api.open-meteo.com/v1/archive", params)
            if r:
                (d / f"{name}_{s:%Y%m}.json").write_text(json.dumps(r.json(), indent=2, ensure_ascii=False), encoding="utf-8")
            time.sleep(1)
        print(f"   done: {name}")


def parse_years(txt):
    if "-" in txt:
        a, b = map(int, txt.split("-"))
        return list(range(a, b + 1))
    return [int(y) for y in txt.split(",")]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2021-2026", help="e.g. 2021-2026 or 2024,2026")
    ap.add_argument("--months", default="6", help="e.g. 6 or 5,6,7")
    ap.add_argument("--only", choices=["metar", "coops", "ndbc", "openmeteo"])
    a = ap.parse_args()
    ranges = list(month_ranges(parse_years(a.years), [int(m) for m in a.months.split(",")]))
    print("Months:", ", ".join(f"{s:%Y-%m}" for s, _ in ranges))

    steps = {"metar": fetch_metar, "coops": fetch_coops, "ndbc": fetch_ndbc, "openmeteo": fetch_open_meteo}
    for key, fn in steps.items():
        if a.only in (None, key):
            fn(ranges)
    print("\nDone. Raw files are in", OUT.resolve())