#!/usr/bin/env python3
"""
Step 4 - race simulator: sails the strategy's action_plan and the real boats' own decisions in the
SAME reconstructed wind, so their routes can be compared fairly. First beat only (gun -> windward mark 1),
where the side and start-line decisions are made.

Inputs (after the race - this is the evaluation side, never fed to the strategist):
  - course        location_agent/course/<date>.json (start line, windward mark 1 per race)
  - truth wind    direction every 2 min from ALL boats' tacking angles (strategy/gps_analysis method),
                  speed from near-real-time HRRR at the course; uniform over the course (no left/right
                  pressure difference - the data cannot resolve it)
  - boat model    per race: upwind speed = fleet median upwind speed over ground, tack angle = measured,
                  tack loss = TACK_LOSS_S of no progress
  - real tracks   sailsync_api_results/ (44 boats): gun position and tack times -> "ghost" boats

Every simulated boat is written as a track CSV in the SailSync format (time_epoch, lat, lng).
Used by location_agent/evaluate.py.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent
sys.path.insert(0, str(ROOT / "strategy" / "gps_analysis"))
from analyse_tracks import (KN, KX, KY, LAT0, LON0, TZ, angdiff, circmean, classify, gps_wind,  # noqa: E402
                            legs_of, load_track)

TRACK_DIR = ROOT / "sailsync_api_results"
COURSE_DIR = PKG / "course"
CONDITIONS = PKG / "data" / "conditions_july.parquet"

DT_S = 2                 # simulation step
TACK_LOSS_S = 6          # seconds of no progress per tack
MIN_TACK_GAP_S = 20      # a boat cannot tack again within this
MARK_RADIUS_M = 15       # rounding = within this of the mark
REAL_MARK_RADIUS_M = 80  # a real track "reaches" the mark within this (marks are uncertain by tens of m)
MAX_BEAT_S = 3600
HEADER_MEMORY_S = 600    # sailor's reference wind = mean of the last 10 min


def unit(bearing_deg: float) -> np.ndarray:
    return np.array([math.sin(math.radians(bearing_deg)), math.cos(math.radians(bearing_deg))])


def to_xy(lat, lon):
    return np.array([(lon - LON0) * KX, (lat - LAT0) * KY])


def to_latlon(xy):
    return LAT0 + xy[1] / KY, LON0 + xy[0] / KX


# ------------------------------------------------------------------ inputs
@dataclass
class Wind:
    t: np.ndarray       # epoch s
    twd: np.ndarray     # deg FROM
    tws: np.ndarray     # kn

    def at(self, t):
        r = np.radians(self.twd)
        s, c = np.interp(t, self.t, np.sin(r)), np.interp(t, self.t, np.cos(r))
        return float(np.degrees(np.arctan2(s, c)) % 360), float(np.interp(t, self.t, self.tws))


@dataclass
class Fleet:
    boats: dict          # name -> classified 10 s track
    raw: dict            # name -> raw track (time_epoch, x, y)
    winners: set
    wind_gps: pd.DataFrame


def boat_name(stem: str) -> str:
    p = stem.split("_")
    return f"{' '.join(p[2:-2]) or p[1]} ({p[-2]})"


def load_fleet(session_id: int) -> Fleet:
    files = [(f, False) for f in sorted(TRACK_DIR.glob(f"{session_id}_*.csv"))] + \
            [(f, True) for f in sorted((TRACK_DIR / "winners").glob(f"{session_id}_*.csv"))]
    boats, raw, winners = {}, {}, set()
    for f, win in files:
        n = boat_name(f.stem)
        boats[n] = load_track(f)
        d = pd.read_csv(f).drop_duplicates("time_epoch").sort_values("time_epoch")
        d["x"], d["y"] = (d.lng - LON0) * KX, (d.lat - LAT0) * KY
        raw[n] = d
        if win:
            winners.add(n)
    w = gps_wind(boats)
    return Fleet({k: classify(v, w) for k, v in boats.items()}, raw, winners, w)


def truth_wind(fleet: Fleet) -> Wind:
    w = fleet.wind_gps
    t = (w.index.tz_convert("UTC").astype("int64") // 10**9).to_numpy(dtype=float)
    df = pd.read_parquet(CONDITIONS, columns=["time_utc", "site", "variable", "value"])
    s = df[(df.site == "port_la_course") & (df.variable == "wind_speed")].sort_values("time_utc")
    ts = (s.time_utc.astype("int64") // 10**9).to_numpy(dtype=float)
    return Wind(t, w.twd_gps.to_numpy(dtype=float), np.interp(t, ts, s.value.to_numpy(dtype=float)))


def course_race(date: str, race: int) -> dict:
    c = json.loads((COURSE_DIR / f"{date}.json").read_text(encoding="utf-8"))
    r = next(x for x in c["races"] if x["race"] == race)
    sl = r["start_line"]
    L, R = to_xy(sl["left_end"]["lat"], sl["left_end"]["lon"]), to_xy(sl["right_end"]["lat"], sl["right_end"]["lon"])
    m1 = r.get("mark1") or r["windward_mark_1"]
    M = to_xy(m1["lat"], m1["lon"])
    centre = (L + R) / 2
    d = M - centre
    return {"left": L, "right": R, "mark": M, "centre": centre, "rhumb_deg": math.degrees(math.atan2(d[0], d[1])) % 360,
            "mark_uncertainty_m": m1["spread_m"], "mark_method": m1.get("method")}


@dataclass
class BoatModel:
    vup_kn: float
    tack_angle: float
    tack_loss_s: float = TACK_LOSS_S


def boat_model(fleet: Fleet, gun: float) -> BoatModel:
    t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(TZ)
    sp, ta = [], []
    for b in fleet.boats.values():
        seg = b[(b.index >= t0) & (b.index <= t0 + pd.Timedelta(minutes=20)) & (b["mode"] == "upwind")]
        sp += list(seg.speed_kn)
    w = fleet.wind_gps[(fleet.wind_gps.index >= t0) & (fleet.wind_gps.index <= t0 + pd.Timedelta(minutes=30))]
    return BoatModel(float(np.median(sp)), float(w.tack_angle.median()) if len(w) else 90.0)


# ------------------------------------------------------------------ real first beats
def real_first_beat(fleet: Fleet, name: str, gun: float, course: dict) -> dict | None:
    """Gun position (0..1 along the line), tack times and time at mark 1 of one real boat."""
    raw = fleet.raw[name]
    t = raw.time_epoch.to_numpy(dtype=float)
    if not (t[0] <= gun <= t[-1]) or np.min(np.abs(t - gun)) > 10:
        return None
    p0 = np.array([np.interp(gun, t, raw.x), np.interp(gun, t, raw.y)])
    line = course["right"] - course["left"]
    pos = float(np.clip((p0 - course["left"]) @ line / (line @ line), -0.5, 1.5))
    b = fleet.boats[name]
    t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(TZ)
    seg = b[(b.index >= t0) & (b.index <= t0 + pd.Timedelta(minutes=30))]
    dist = np.hypot(seg.x - course["mark"][0], seg.y - course["mark"][1])
    near = seg.index[dist <= REAL_MARK_RADIUS_M]
    t_mark = float(near[0].timestamp()) if len(near) else float("nan")
    # end of the first beat: at the mark, else the first switch to downwind after the start (tracker gap at the mark)
    down = seg.index[(seg["mode"] == "downwind") & (seg.index >= t0 + pd.Timedelta(minutes=3))]
    end = near[0] if len(near) else (down[0] if len(down) else seg.index[-1])
    beat = seg[seg.index <= end]
    tk = beat[beat.tack != ""].tack
    first = tk.iloc[0] if len(tk) else "starboard"
    changes = tk[tk != tk.shift()].index[1:]
    right = unit(course["rhumb_deg"] + 90)
    lat = (beat[["x", "y"]].to_numpy() - course["centre"]) @ right
    return {"boat": name, "winner": name in fleet.winners, "line_position": round(pos, 3), "first_tack": first,
            "tack_times": [float(x.timestamp()) for x in changes], "gun_xy": p0,
            "real_time_to_mark_s": (t_mark - gun) if not math.isnan(t_mark) else None,
            "real_mean_lateral_m": round(float(lat.mean())) if len(lat) else None,
            "real_pct_time_right": round(float((lat > 0).mean() * 100)) if len(lat) else None}


# ------------------------------------------------------------------ simulation
@dataclass
class State:
    t: float
    xy: np.ndarray
    tack: str
    last_tack_t: float
    track: list = field(default_factory=list)
    tacks: int = 0
    history: list = field(default_factory=list)     # (t, twd) felt by the sailor
    phase: str = "start"
    final: bool = False


def heading(twd, tack, ta):
    return (twd - ta / 2) % 360 if tack == "starboard" else (twd + ta / 2) % 360


def other(tack):
    return "port" if tack == "starboard" else "starboard"


def fetch_excess(s: State, mark, twd, ta, tack) -> float:
    """Metres beyond the layline for `tack` (>= 0 means the mark can be fetched on that tack)."""
    d = mark - s.xy
    dist = float(np.hypot(*d))
    b = math.degrees(math.atan2(d[0], d[1])) % 360
    off = float(angdiff(b, twd))
    beyond = (-off if tack == "starboard" else off) - ta / 2
    return dist * math.sin(math.radians(beyond)) if beyond > -90 else -dist


class GhostPolicy:
    """Replays a real boat's tack times; after its last recorded tack it sails the laylines home."""

    def __init__(self, tack_times):
        self.times = list(tack_times)

    def decide(self, s: State, twd, tws, ta, course):
        if self.times and s.t >= self.times[0]:
            self.times.pop(0)
            return True
        if not self.times:
            return fetch_excess(s, course["mark"], twd, ta, other(s.tack)) >= 0 and \
                fetch_excess(s, course["mark"], twd, ta, s.tack) < 0
        return False


class PlanPolicy:
    """Executes the strategist's action_plan literally (see prompt.ACTION PLAN)."""

    def __init__(self, plan: dict, gun: float):
        self.p, self.gun = plan, gun
        self.side = plan["upwind"]["target_side"]
        self.hdr = plan["upwind"]["tack_on_header_deg"]
        self.fired = set()
        self.header_since = None

    def _triggers(self, twd, tws):
        for i, tr in enumerate(self.p.get("triggers", [])):
            if i in self.fired:
                continue
            c, v = tr["condition"], tr["value"]
            hit = ((c == "wind_speed_below_kn" and tws < v) or (c == "wind_speed_above_kn" and tws > v) or
                   (c == "wind_dir_right_of_deg" and angdiff(twd, v) > 0) or (c == "wind_dir_left_of_deg" and angdiff(twd, v) < 0))
            if hit:
                self.fired.add(i)
                if tr["then_target_side"] != "keep":
                    self.side = tr["then_target_side"]
                self.hdr = tr["then_tack_on_header_deg"]

    def decide(self, s: State, twd, tws, ta, course):
        u = self.p["upwind"]
        self._triggers(twd, tws)
        if s.t - self.gun < self.p["start"]["hold_first_tack_s"]:
            return False
        mark = course["mark"]
        # 1. laylines: tack for the mark once beyond the layline by the planned overstand
        if fetch_excess(s, mark, twd, ta, other(s.tack)) >= u["layline_overstand_m"] or \
                (s.final and fetch_excess(s, mark, twd, ta, s.tack) < 0 <= fetch_excess(s, mark, twd, ta, other(s.tack))):
            s.final = True
            return True
        if s.final:
            return False
        right = unit(course["rhumb_deg"] + 90)
        lat = float((s.xy - course["centre"]) @ right)
        going_right = float(unit(heading(twd, s.tack, ta)) @ right) > 0
        lim = u["max_lateral_m"]
        lo, hi = {"right": (-100, lim), "left": (-lim, 100)}.get(self.side, (-lim, lim))
        # 2. corridor
        if (lat >= hi and going_right) or (lat <= lo and not going_right):
            s.phase = "play"
            return True
        # 3. get to the target side first
        if s.phase != "play" and self.side in ("left", "right"):
            if (self.side == "right") != going_right:
                return True
            if (self.side == "right" and lat >= hi) or (self.side == "left" and lat <= lo):
                s.phase = "play"
            return False
        s.phase = "play"
        # 4. play the shifts: header = heading knocked vs the recent mean wind
        hist = [w for (tt, w) in s.history if tt >= s.t - HEADER_MEMORY_S]
        ref = circmean(hist) if hist else twd
        knock = float(angdiff(ref, twd)) if s.tack == "starboard" else float(angdiff(twd, ref))
        if knock >= self.hdr:
            self.header_since = self.header_since or s.t
            if s.t - self.header_since >= u["header_hold_s"]:
                self.header_since = None
                return True
        else:
            self.header_since = None
        return False


def sail_first_beat(start_xy, first_tack, gun, wind: Wind, boat: BoatModel, course, policy) -> dict:
    s = State(gun, np.array(start_xy, dtype=float), first_tack, gun - MIN_TACK_GAP_S)
    v = boat.vup_kn / KN                                     # m/s
    stall_until, t_near = -1.0, None
    while s.t - gun <= MAX_BEAT_S:
        twd, tws = wind.at(s.t)
        s.history.append((s.t, twd))
        s.track.append((s.t, *to_latlon(s.xy)))
        dist = float(np.hypot(*(course["mark"] - s.xy)))
        if t_near is None and dist <= REAL_MARK_RADIUS_M:
            t_near = s.t - gun          # timed at the same radius as the real tracks
        if dist <= MARK_RADIUS_M:
            return {"time_to_mark_s": t_near, "tacks": s.tacks, "track": s.track, "reached": True}
        if s.t - s.last_tack_t >= MIN_TACK_GAP_S and policy.decide(s, twd, tws, boat.tack_angle, course):
            s.tack, s.last_tack_t, s.tacks = other(s.tack), s.t, s.tacks + 1
            stall_until = s.t + boat.tack_loss_s
        if s.t >= stall_until:
            h = heading(twd, s.tack, boat.tack_angle)
            if s.final or fetch_excess(s, course["mark"], twd, boat.tack_angle, s.tack) >= 0:
                d = course["mark"] - s.xy                    # can lay the mark: sail straight at it
                h = math.degrees(math.atan2(d[0], d[1])) % 360 if fetch_excess(
                    s, course["mark"], twd, boat.tack_angle, s.tack) >= 0 else h
            step = min(v * DT_S, float(np.hypot(*(course["mark"] - s.xy))))
            s.xy = s.xy + unit(h) * step
        s.t += DT_S
    return {"time_to_mark_s": None, "tacks": s.tacks, "track": s.track, "reached": False}


def lateral_stats(track, course):
    xy = np.array([to_xy(la, lo) for _, la, lo in track])
    lat = (xy - course["centre"]) @ unit(course["rhumb_deg"] + 90)
    return round(float(lat.mean())), round(float((lat > 0).mean() * 100))


def write_track(path: Path, track):
    pd.DataFrame(track, columns=["time_epoch", "lat", "lng"]).round({"lat": 7, "lng": 7}).to_csv(path, index=False)
