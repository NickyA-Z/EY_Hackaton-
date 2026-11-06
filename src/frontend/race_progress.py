"""Race-scoped recorded tracks and estimated first-buoy arrivals."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import paths  # noqa: E402

RACE_DAY = "2026-07-19"
RANKINGS = {
    1: ("Rasmus Granzin", "Lawson McAullay", "Clemente Seguel Lacámara"),
    2: ("Duko Bos", "Pavlos Kontides", "Dimitri Peroni"),
}
RANK_LABELS = ("1st", "2nd", "3rd")
RANKING_TRACK_IDS = {
    "Rasmus Granzin": 15367,
    "Lawson McAullay": 15344,
    "Clemente Seguel Lacámara": 15391,
    "Duko Bos": 15361,
    "Pavlos Kontides": 15364,
    "Dimitri Peroni": 15372,
}


def first_buoy_arrival(track, gun, mark, radius_m=80):
    """Estimate first approach within 25 minutes; never infer arrival across a GPS gap."""
    window = track[track.time_epoch.between(gun + 120, gun + 1500)]
    if window.empty:
        return None
    north = (window.lat - mark[0]) * 111_320
    east = (window.lng - mark[1]) * 111_320 * np.cos(np.radians(mark[0]))
    nearby = window[np.hypot(north, east) <= radius_m]
    return float(nearby.iloc[0].time_epoch) if not nearby.empty else None


def race_track_window(track, race, first_beat=True):
    """Exclude other races and stop each first-beat track at its estimated arrival."""
    arrival = first_buoy_arrival(track, race["gun"], race["mark1"],
                                 max(35, race["mark1_uncertainty_m"])) if first_beat else None
    end = race["end"]
    if first_beat:
        end = arrival or race["first_beat_end"]
        if arrival is None:
            approach = track[track.time_epoch.between(race["gun"] + 120, end)]
            if not approach.empty:
                north = (approach.lat - race["mark1"][0]) * 111_320
                east = ((approach.lng - race["mark1"][1]) * 111_320 *
                        np.cos(np.radians(race["mark1"][0])))
                end = float(approach.loc[np.hypot(north, east).idxmin(), "time_epoch"])
    window = track[track.time_epoch.between(race["gun"], end)].copy()
    return window.reset_index(drop=True), arrival


def illustrated_mark_track(race, name, observed):
    """Continue a ranked boat's first beat from its last GPS fix at 6 kt."""
    if name not in RANKINGS[race["race"]] or len(observed) < 2:
        return None
    last = observed.iloc[-1]
    north = (last.lat - race["mark1"][0]) * 111_320
    east = ((last.lng - race["mark1"][1]) * 111_320 *
            np.cos(np.radians(race["mark1"][0])))
    # The reconstructed buoy and the missing GPS fixes cannot establish a
    # rounding time. This constant speed is display-only, not a race result.
    arrival = float(last.time_epoch) + np.hypot(north, east) / (6 / 1.943844)
    return {
        "arrival": arrival,
        "recorded_until": float(last.time_epoch),
        "points": observed[["time_epoch", "lat", "lng"]].dropna().values.tolist()
                  + [[arrival, *race["mark1"]]],
        "synthetic": True,
    }


def load_race_progress(course_file=None, track_dir=None):
    """Recorded tracks and rankings of the replayed race day. Folders come from backend.paths unless given (tests)."""
    course_path = Path(course_file) if course_file else paths.LOCATION_AGENT_COURSE_DIR / f"{RACE_DAY}.json"
    if not course_path.exists():
        return []
    courses = [course for course in json.loads(course_path.read_text())["races"]
               if course["race"] in RANKINGS]
    track_dir = Path(track_dir) if track_dir else paths.SAILSYNC_DIR
    tracks_by_name = {}
    for name in {name for ranking in RANKINGS.values() for name in ranking}:
        files = sorted(track_dir.rglob(f"2796_{RANKING_TRACK_IDS[name]}_*.csv"))
        if files:
            tracks_by_name[name] = pd.read_csv(files[0]).sort_values("time_epoch")
    races = []
    for i, course in enumerate(courses):
        number = course["race"]
        gun = pd.Timestamp(f"2026-07-19 {course['gun_local']}", tz="America/Los_Angeles").timestamp()
        next_gun = (pd.Timestamp(f"2026-07-19 {courses[i + 1]['gun_local']}",
                                 tz="America/Los_Angeles").timestamp()
                    if i + 1 < len(courses) else gun + 5400)
        finish = course.get("finish")
        race = {"race": number, "gun": gun, "end": min(gun + 2700, next_gun - 60),
                "first_beat_end": gun + 1500,
                "start_line": [[course["start_line"][end]["lat"], course["start_line"][end]["lon"]]
                               for end in ("left_end", "right_end")],
                "mark1": [course["mark1"]["lat"], course["mark1"]["lon"]],
                "mark1_method": course["mark1"]["method"],
                "mark1_uncertainty_m": course["mark1"].get("spread_m", 80),
                "finish": [finish["lat"], finish["lon"]] if finish else None,
                "other_marks": [[course[key]["lat"], course[key]["lon"]]
                                for key in ("mark2",) if course.get(key)] +
                               [[mark["lat"], mark["lon"]] for mark in course.get("gate3", [])],
                "rankings": [{"position": label, "name": name, "gps_available": name in tracks_by_name}
                             for label, name in zip(RANK_LABELS, RANKINGS[number])],
                "tracks": []}
        path = paths.LOCATION_AGENT_OUTPUT_DIR / f"{RACE_DAY}_port_la_course" / "sim" / f"race{number}_agent.csv"
        agent = pd.read_csv(path).sort_values("time_epoch") if path.exists() else pd.DataFrame()
        full_path = path.with_name(f"race{number}_agent_full.csv")
        full_agent = pd.read_csv(full_path).sort_values("time_epoch") if full_path.exists() else pd.DataFrame()
        if agent.empty:
            agent = full_agent
        for name, track in [(name, tracks_by_name.get(name, pd.DataFrame())) for name in RANKINGS[number]] + [
            ("Your agent", agent)
        ]:
            if track.empty:
                race["tracks"].append({"name": name, "agent": name == "Your agent", "arrival": None,
                                       "points": [], "full_points": []})
                continue
            window, arrival = race_track_window(track, race)
            full_source = full_agent if name == "Your agent" else track
            full_window, _ = race_track_window(full_source, race, first_beat=False)
            first_beat_track = illustrated_mark_track(race, name, window) if arrival is None else None
            race["tracks"].append({"name": name, "agent": name == "Your agent",
                                   "arrival": first_beat_track["arrival"] if first_beat_track else arrival,
                                   "synthetic": bool(first_beat_track),
                                   "recorded_until": first_beat_track["recorded_until"] if first_beat_track else None,
                                   "full_points": full_window[["time_epoch", "lat", "lng"]].dropna().values.tolist(),
                                   "points": first_beat_track["points"] if first_beat_track else
                                   window[["time_epoch", "lat", "lng"]].dropna().values.tolist()})
        previous_arrival = race["gun"]
        for ranked_track in race["tracks"][:len(RANKINGS[number])]:
            if ranked_track["arrival"] is None:
                continue
            if ranked_track["synthetic"]:
                ranked_track["arrival"] = max(ranked_track["arrival"], previous_arrival + 5)
                ranked_track["points"][-1][0] = ranked_track["arrival"]
            previous_arrival = ranked_track["arrival"]
        races.append(race)
    return races
