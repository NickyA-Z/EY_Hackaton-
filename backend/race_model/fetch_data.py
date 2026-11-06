"""Download what the race model needs from the SailSync API into data/race_model/.

Run from the repo root (SAILSYNC_API_TOKEN comes from ~/.zshrc):
    .venv/bin/python -m backend.race_model.fetch_data

Every response is cached as a file and reruns skip what already exists, so when the
Standard plan rate limit (10/min, 60/hour) stops the run with a 429, run it again later.

Per session it saves analysis.json (leg directions) and per race:
  results.json   final position + finish time of every boat
  leg_<k>.json   per boat: start/end time of leg k (end = mark rounding) + wind on that leg
plus the GPS tracks (tracks/<track_id>.csv) of the TOP_N finishers of each race.
"""

import json
import os
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.sailsync.io/api/integrations/v1"
EVENT_ID = 2  # San Pedro OCR 2026 (ILCA 6, ILCA 7)
BOAT_CLASS = "ILCA 7"
DAYS = ["2026-07-19", "2026-07-20", "2026-07-22"]  # 8 races
TOP_N = 6  # tracks per race: enough to average the mark positions and compare the leaders

OUT = Path(__file__).resolve().parents[2] / "data" / "race_model"


def get(path, params=None, cache=None):
    """GET one API path, cached on disk. A 429 (rate limit) just stops the run: rerun later."""
    if cache and cache.exists():
        return json.loads(cache.read_text())
    headers = {"Authorization": f"Bearer {os.environ['SAILSYNC_API_TOKEN']}"}
    r = requests.get(BASE + path, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    return data


def save_track(session_id, track_id, target):
    """One boat's GPS points as CSV (time_epoch, lat, lng)."""
    if target.exists():
        return
    points, cursor = [], None
    while True:
        page = get(f"/sessions/{session_id}/data/tracks/{track_id}/points", {"limit": 5000, "cursor": cursor})
        points += page.get("points", [])
        if not (cursor := page.get("next_cursor")):
            break
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(points, columns=["time_epoch", "lat", "lng"]).to_csv(target, index=False)


def fetch_session(sid):
    folder = OUT / str(sid)
    analysis = get(f"/sessions/{sid}/data/analysis", cache=folder / "analysis.json")
    keep = set()
    for race in analysis.get("races", []):
        if not race.get("available"):
            print(f"  {race['label']}: no analysis ({race.get('reason')})")
            continue
        url, race_dir = f"/sessions/{sid}/data/races/{race['id']}/results", folder / race["id"]
        results = get(url, {"limit": 100}, race_dir / "results.json")["results"]
        for leg in race["legs"]:
            k = leg["leg_index"]
            get(url, {"limit": 100, "leg_index": k}, race_dir / f"leg_{k}.json")
        ranked = sorted((r for r in results if r.get("position")), key=lambda r: r["position"])
        keep |= {r["boat_id"] for r in ranked[:TOP_N]}
        print(f"  {race['label']}: {len(results)} boats, {len(race['legs'])} legs")
    for track_id in sorted(keep):
        save_track(sid, track_id, folder / "tracks" / f"{track_id}.csv")
    print(f"  tracks: {len(keep)}")


def main():
    event = get(f"/events/{EVENT_ID}", {"limit": 100}, OUT / "event.json")
    for s in event["sessions"]:
        if s["boat_class"] != BOAT_CLASS or s["date"] not in DAYS:
            continue
        print(f"{s['date']} {s['division']} (session {s['session_id']})")
        if s.get("access_allowed"):
            fetch_session(s["session_id"])
        else:
            print("  no access to this day")
    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
