"""Sail a strategy's action plan in a *forecast world*, for courses with no real race to compare against (Belmont).

``evaluate.py`` compares the plan with what 44 real boats did on the San Pedro course. Belmont has no tracks, no results
and no surveyed marks: its pack is built on a placeholder ("E-W beat ~1.25 km through the venue centre"). So this module
does the part that is still honest:

* course   the pack's placeholder start line and windward mark (one beat; no run is invented),
* wind     the day-ahead HRRR forecast for the site (what was known the day before), uniform over the course,
* boat     the pack's class priors (tack angle, upwind VMG); no measured boat data exists for this site,
* sailing  the same rule-following simulator as the real-race evaluation (``simulate.PlanPolicy``).

It answers "can this plan be sailed, how long is the beat, how many tacks, and does the side it chose matter under that
forecast?" by also sailing pure left / middle / right variants. It does NOT say whether the plan would have won: wind
is a forecast (no observed shifts), current is ignored, and there are no other boats.
"""

from __future__ import annotations

import copy
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from backend import paths
from backend.gps_analysis.analyse_tracks import TZ

from . import simulate as sim

SIDES = ("left", "middle", "right")


def _hms(seconds: float | None) -> str | None:
    return None if seconds is None else f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _forecast_wind(area: str, race_day: str, gun: float) -> sim.Wind:
    table = pd.read_parquet(paths.LOCATION_AGENT_CONDITIONS_FILE, columns=["time_utc", "site", "variable", "value"])
    rows = table[table.site == f"{area}_dayahead"]
    series = {}
    for variable in ("wind_dir_from", "wind_speed"):
        s = rows[rows.variable == variable].sort_values("time_utc")
        ts = sim.epoch_s(s.time_utc)
        keep = (ts >= gun - 3600) & (ts <= gun + 3 * 3600)
        series[variable] = (ts[keep], s.value.to_numpy(dtype=float)[keep])
    t, twd = series["wind_dir_from"]
    ts_speed, tws = series["wind_speed"]
    if len(t) < 2 or len(ts_speed) < 2:
        raise ValueError(f"no day-ahead wind forecast for {area} around {race_day}")
    return sim.Wind(t, twd, np.interp(t, ts_speed, tws))


def _course(pack: dict) -> dict:
    co = pack["context"]["course"]
    a, b = (sim.to_xy(*end) for end in co["start_line_ends"])
    mark = sim.to_xy(*co["windward_mark"])
    centre = (a + b) / 2
    rb = math.radians(co["rhumb_bearing_deg"])
    right = np.array([math.cos(rb), -math.sin(rb)])  # unit vector to the right when looking up the beat
    left_end, right_end = (a, b) if np.dot(a - b, right) < 0 else (b, a)
    d = mark - centre
    rhumb = math.degrees(math.atan2(d[0], d[1])) % 360
    leg = {"type": "beat", "to": "mark1", "mark": mark, "origin": centre, "rhumb_deg": rhumb, "uncertain": True, "spread_m": None}
    return {"left": left_end, "right": right_end, "mark": mark, "centre": centre, "rhumb_deg": rhumb,
            "mark_uncertainty_m": None, "mark_method": "placeholder", "legs": [leg]}


def _boat(pack: dict) -> sim.BoatModel:
    prior = pack["building_blocks"]["9_laylines"]["evidence"]["class_priors"]
    angle = float(prior["tack_angle_deg"])
    return sim.BoatModel(vup_kn=float(prior["upwind_vmg_kn"]) / math.cos(math.radians(angle / 2)), tack_angle=angle)


def _sail(plan: dict, course: dict, wind: sim.Wind, boat: sim.BoatModel, gun: float) -> dict:
    line = float(np.clip(plan["start"]["line_position"], 0, 1))
    start = course["left"] + line * (course["right"] - course["left"])
    result = sim.sail_race(start, plan["start"]["first_tack"], gun, wind, boat, course, sim.PlanPolicy(plan, gun))
    leg = result["legs"][0] if result["legs"] else {}
    seconds = leg.get("at_mark_s")
    lateral = sim.lateral_stats(result["track"], course) if result["track"] else None
    return {"reached_mark": seconds is not None, "seconds": seconds, "time": _hms(seconds), "tacks": leg.get("tacks", 0),
            "lateral_m": lateral, "track": result["track"]}


def forecast_world(race_day: str, area: str, pack: dict, strategy: dict, out_dir: Path) -> dict:
    """Sail the strategy's plan and the three pure-side variants; write evaluation.json / evaluation.md into ``out_dir``."""
    answer = strategy["answer"]
    if "action_plan" not in answer:
        raise ValueError("the strategy has no action_plan - re-run the strategist")
    hour = int(pack["context"]["settings"]["race_window_local"][0])
    gun = pd.Timestamp(f"{race_day} {hour:02d}:00", tz=TZ).timestamp()
    wind, course, boat = _forecast_wind(area, race_day, gun), _course(pack), _boat(pack)

    plan = answer["action_plan"]
    chosen = _sail(plan, course, wind, boat, gun)
    variants = {}
    for side in SIDES:
        variant = copy.deepcopy(plan)
        variant["upwind"]["target_side"] = side
        variant["triggers"] = []  # a pure side: no mid-race switch
        variants[side] = _sail(variant, course, wind, boat, gun)

    twd0, tws0 = wind.at(gun)
    twd1, _ = wind.at(gun + 3600)
    off_wind = abs(float(sim.angdiff(twd0, course["rhumb_deg"])))  # how far the mark is from the direction the wind comes from
    fetchable = off_wind < boat.tack_angle / 2
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sim").mkdir(exist_ok=True)
    sim.write_track(out_dir / "sim" / "forecast_plan_track.csv", chosen["track"])
    strip = lambda r: {k: v for k, v in r.items() if k != "track"}  # noqa: E731
    result = {
        "kind": "forecast_world", "date": race_day, "area": area, "model": strategy["run"].get("served_by"),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "assumptions": [
            f"Course: {pack['context']['course']['source']}. One beat of {pack['context']['course']['beat_length_m']} m; no run or finish was invented.",
            f"Wind: day-ahead HRRR forecast for {area}, uniform over the course. At the gun {twd0:.0f}° from, {tws0:.1f} kn; "
            f"{(twd1 - twd0 + 180) % 360 - 180:+.0f}° over the next hour. No observed shifts, no current, no other boats.",
            *([f"WARNING: the placeholder mark is {off_wind:.0f}° off the wind, inside the boat's {boat.tack_angle / 2:.0f}° tacking "
               "half-angle, so it can be reached on one tack. The leg is a close reach, not a beat, and the side choice barely "
               "matters. The real course will be laid to the wind."] if fetchable else []),
            f"Boat: {pack['context']['boat_class']} class priors from the pack (tack angle {boat.tack_angle:.0f}°, upwind VMG "
            f"{pack['building_blocks']['9_laylines']['evidence']['class_priors']['upwind_vmg_kn']} kn); not measured at this site.",
        ],
        "mark_off_wind_deg": round(off_wind), "mark_fetchable_without_tacking": fetchable,
        "plan": strip(chosen), "alternatives": {s: strip(r) for s, r in variants.items()},
        "plan_side": plan["upwind"]["target_side"],
        "note": "A plausibility and sensitivity check. It is not a comparison with a real race: Belmont has none.",
    }
    (out_dir / "evaluation.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    (out_dir / "evaluation.md").write_text(markdown(result), encoding="utf-8")
    return result


def markdown(res: dict) -> str:
    rows = [("**The plan**", res["plan"])] + [(f"Pure {s}, no switch", r) for s, r in res["alternatives"].items()]
    lines = [f"# Forecast-world simulation - {res['date']} ({res['area']})", "", f"Model {res['model']}. {res['note']}", "",
             "## Assumptions", *[f"- {a}" for a in res["assumptions"]], "",
             "## Time to the windward mark", "", "| Option | Time | Tacks |", "|---|---|---|"]
    lines += [f"| {name} | {r['time'] or 'not reached'} | {r['tacks']} |" for name, r in rows]
    return "\n".join(lines) + "\n"
