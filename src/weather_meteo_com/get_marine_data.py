#!/usr/bin/env python3
"""Open-Meteo Marine API から過去の海況データを取得して JSON に保存する。
使い方: python3 get_marine_data.py [開始日] [終了日]"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

LATITUDE = 33.755
LONGITUDE = -118.140

HOURLY_VARS = [
    "wave_height", "wave_direction", "wave_period",
    "wind_wave_height",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "sea_surface_temperature",
    "ocean_current_velocity", "ocean_current_direction",
    "sea_level_height_msl",
]


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2025-11-06"
    end = sys.argv[2] if len(sys.argv) > 2 else start

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "America/Los_Angeles",
        "cell_selection": "sea",
    }
    url = "https://marine-api.open-meteo.com/v1/marine?" + urllib.parse.urlencode(params)
    print("Request:", url)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        print("Error:", e.code, e.read().decode())
        sys.exit(1)

    outfile = f"belmont_marine_{start}_{end}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    n = len(data.get("hourly", {}).get("time", []))
    print(f"Saved {n} hourly records -> {outfile}")


if __name__ == "__main__":
    main()
