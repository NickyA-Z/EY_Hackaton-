#!/usr/bin/env python3
"""
Step 4 - race simulator: sails the strategy's action_plan over the FULL course of a race, in the
reconstructed race-day wind, and outputs our boat's positions at the timestamps of the race winner's
real track (SailSync format: time_epoch, lat, lng) so both can be plotted and compared directly.

Inputs (after the race - this is the evaluation side, never fed to the strategist):
  - course        location_agent/course/<date>.json: start line, marks and the leg order per race
                  (race 1: beat -> mark1, run -> gate, beat -> mark2, run -> gate, reach -> finish)
  - truth wind    direction every 2 min from ALL boats' tacking angles (strategy/gps_analysis method),
                  speed from near-real-time HRRR at the course; uniform over the course
  - boat model    measured from the fleet in that race: upwind / downwind / reach speed, tack angle,
                  downwind angle to the wind; tack and gybe losses of TACK_LOSS_S / GYBE_LOSS_S
  - real tracks   sailsync_api_results/ (44 boats): which boat won, its timestamps, real leg times

Runs use the beat rules mirrored: wind turned by 180 deg and the gybe angle in place of the tack angle,
so "layline", "corridor", "target side" and "shift" mean the same thing downwind.
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
GYBE_LOSS_S = 4          # seconds of no progress per gybe
MIN_TACK_GAP_S = 20      # a boat cannot tack again within this
MARK_RADIUS_M = 15       # rounding = within this of the mark
REAL_MARK_RADIUS_M = 80  # a real track "reaches" the mark within this (marks are uncertain by tens of m)
MAX_BEAT_S = 3600
MAX_RACE_S = 5400
FINISH_EARLIEST_S = 1500  # a real boat cannot finish within 25 min of the gun (race 1 leaders: ~38 min)
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
    marks = {"mark1": m1, "mark2": r.get("mark2"), "finish": r.get("finish")}
    marks.update({g["id"]: g for g in r.get("gate3", [])})
    legs, origin = [], centre
    for lg in r.get("legs", [{"type": "beat", "to": "mark1"}]):
        m = marks.get(lg["to"])
        if not m:
            break
        to = to_xy(m["lat"], m["lon"])
        dd = to - origin
        legs.append({"type": lg["type"], "to": lg["to"], "mark": to, "origin": origin,
                     "rhumb_deg": math.degrees(math.atan2(dd[0], dd[1])) % 360,
                     "uncertain": bool(m.get("uncertain")), "spread_m": m.get("spread_m")})
        origin = to
    return {"left": L, "right": R, "mark": M, "centre": centre, "rhumb_deg": math.degrees(math.atan2(d[0], d[1])) % 360,
            "mark_uncertainty_m": m1["spread_m"], "mark_method": m1.get("method"), "legs": legs}


@dataclass
class BoatModel:
    vup_kn: float
    tack_angle: float
    vdn_kn: float = 6.0
    downwind_twa: float = 150.0      # angle between the wind and the course sailed on a run
    vreach_kn: float = 6.0
    tack_loss_s: float = TACK_LOSS_S
    gybe_loss_s: float = GYBE_LOSS_S


def boat_model(fleet: Fleet, gun: float, minutes: int = 45) -> BoatModel:
    """Measured from all boats in this race: median speed over ground by mode, tack angle, run angle."""
    t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(TZ)
    up, dn, dn_twa, reach = [], [], [], []
    for b in fleet.boats.values():
        r = b[(b.index >= t0) & (b.index <= t0 + pd.Timedelta(minutes=minutes))]
        up += list(r[(r["mode"] == "upwind") & (r.index <= t0 + pd.Timedelta(minutes=20))].speed_kn)
        d = r[(r["mode"] == "downwind") & (r.speed_kn > 2.5)]
        dn += list(d.speed_kn)
        dn_twa += list(np.abs(d.twa))
        rr = r[(np.abs(r.twa) > 70) & (np.abs(r.twa) < 110) & (r.speed_kn > 2.5)]
        reach += list(rr.speed_kn)
    w = fleet.wind_gps[(fleet.wind_gps.index >= t0) & (fleet.wind_gps.index <= t0 + pd.Timedelta(minutes=30))]
    return BoatModel(float(np.median(up)), float(w.tack_angle.median()) if len(w) else 90.0,
                     float(np.median(dn)) if dn else 6.0, float(np.median(dn_twa)) if dn_twa else 150.0,
                     float(np.median(reach)) if reach else 6.0)


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


class PlanPolicy:
    """Executes the strategist's action_plan literally (see prompt.ACTION PLAN), leg by leg.
    Beats use plan["upwind"]; runs use plan["downwind"] in a mirrored frame (wind + 180 deg)."""

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

    def rules(self, leg_type):
        """(target side, max lateral m, shift threshold deg, hold s, overstand m) for this kind of leg."""
        u = self.p["upwind"]
        if leg_type == "run":
            d = self.p.get("downwind", {})
            return (d.get("target_side", "middle"), d.get("max_lateral_m", u["max_lateral_m"]),
                    d.get("gybe_on_lift_deg", u["tack_on_header_deg"]), u["header_hold_s"], 0.0)
        return self.side, u["max_lateral_m"], self.hdr, u["header_hold_s"], u["layline_overstand_m"]

    def start_tack(self, leg, s, twd_eff, ang):
        """First tack / gybe of a leg: the one heading to the target side (middle: the one closer to the mark)."""
        side = self.rules(leg["type"])[0]
        right = unit(leg["rhumb_deg"] + 90)
        if side in ("left", "right"):
            st_right = float(unit(heading(twd_eff, "starboard", ang)) @ right) > 0
            return "starboard" if st_right == (side == "right") else "port"
        d = leg["mark"] - s.xy
        b = math.degrees(math.atan2(d[0], d[1])) % 360
        return min(("starboard", "port"), key=lambda k: abs(float(angdiff(heading(twd_eff, k, ang), b))))

    def decide(self, s, twd_eff, tws, ang, leg, first_leg: bool):
        if leg["type"] == "beat":
            self._triggers(twd_eff % 360, tws)
        side, lim, shift, hold, over = self.rules(leg["type"])
        if first_leg and s.t - self.gun < self.p["start"]["hold_first_tack_s"]:
            return False
        mark = leg["mark"]
        # 1. laylines: tack / gybe for the mark once beyond the layline by the planned overstand
        if fetch_excess(s, mark, twd_eff, ang, other(s.tack)) >= over or \
                (s.final and fetch_excess(s, mark, twd_eff, ang, s.tack) < 0 <= fetch_excess(s, mark, twd_eff, ang, other(s.tack))):
            s.final = True
            return True
        if s.final:
            return False
        right = unit(leg["rhumb_deg"] + 90)
        lat = float((s.xy - leg["origin"]) @ right)
        going_right = float(unit(heading(twd_eff, s.tack, ang)) @ right) > 0
        lo, hi = {"right": (-100, lim), "left": (-lim, 100)}.get(side, (-lim, lim))
        # 2. corridor
        if (lat >= hi and going_right) or (lat <= lo and not going_right):
            s.phase = "play"
            return True
        # 3. get to the target side first
        if s.phase != "play" and side in ("left", "right"):
            if (side == "right") != going_right:
                return True
            if (side == "right" and lat >= hi) or (side == "left" and lat <= lo):
                s.phase = "play"
            return False
        s.phase = "play"
        # 4. play the shifts (upwind: header; downwind: a lift = a header in the mirrored frame)
        hist = [w for (tt, w) in s.history if tt >= s.t - HEADER_MEMORY_S]
        ref = circmean(hist) if hist else twd_eff
        knock = float(angdiff(ref, twd_eff)) if s.tack == "starboard" else float(angdiff(twd_eff, ref))
        if knock >= shift:
            self.header_since = self.header_since or s.t
            if s.t - self.header_since >= hold:
                self.header_since = None
                return True
        else:
            self.header_since = None
        return False


def leg_frame(kind, twd, boat):
    """(wind used by the rules, angle between the two tacks/gybes, speed m/s, turn loss s) for a leg type."""
    if kind == "beat":
        return twd, boat.tack_angle, boat.vup_kn / KN, boat.tack_loss_s
    if kind == "run":
        return (twd + 180) % 360, 2 * (180 - boat.downwind_twa), boat.vdn_kn / KN, boat.gybe_loss_s
    return twd, 0.0, boat.vreach_kn / KN, 0.0


def sail_race(start_xy, first_tack, gun, wind: Wind, boat: BoatModel, course, policy: PlanPolicy) -> dict:
    """Sail every leg of course["legs"] in order. Returns the 2 s track and per-leg results."""
    s = State(gun, np.array(start_xy, dtype=float), first_tack, gun - MIN_TACK_GAP_S)
    stall_until, legs_out = -1.0, []
    for li, leg in enumerate(course["legs"]):
        kind = leg["type"]
        s.final, s.phase, policy.header_since, s.history = False, "start", None, []
        t_start, n_turns, t_near, done = s.t, 0, None, False
        if li > 0 and kind != "reach":
            eff, ang, _, _ = leg_frame(kind, wind.at(s.t)[0], boat)
            s.tack = policy.start_tack(leg, s, eff, ang)
        while s.t - gun <= MAX_RACE_S:
            twd, tws = wind.at(s.t)
            eff, ang, v, loss = leg_frame(kind, twd, boat)
            s.history.append((s.t, eff))
            s.track.append((s.t, *to_latlon(s.xy)))
            dist = float(np.hypot(*(leg["mark"] - s.xy)))
            if t_near is None and dist <= REAL_MARK_RADIUS_M:
                t_near = s.t
            if dist <= MARK_RADIUS_M:
                done = True
                break
            if kind != "reach" and s.t - s.last_tack_t >= MIN_TACK_GAP_S and \
                    policy.decide(s, eff, tws, ang, leg, first_leg=(li == 0)):
                s.tack, s.last_tack_t, s.tacks, n_turns = other(s.tack), s.t, s.tacks + 1, n_turns + 1
                stall_until = s.t + loss
            if s.t >= stall_until:
                d = leg["mark"] - s.xy
                if kind == "reach" or fetch_excess(s, leg["mark"], eff, ang, s.tack) >= 0:
                    h = math.degrees(math.atan2(d[0], d[1])) % 360      # can lay the mark: sail straight at it
                else:
                    h = heading(eff, s.tack, ang)
                s.xy = s.xy + unit(h) * min(v * DT_S, dist)
            s.t += DT_S
        turn_key = "tacks" if kind == "beat" else "gybes" if kind == "run" else "turns"
        legs_out.append({"leg": li + 1, "type": kind, "to": leg["to"], "start_s": round(t_start - gun),
                         "at_mark_s": round(s.t - gun) if done else None,
                         "within_80m_s": round(t_near - gun) if t_near else None,
                         "time_s": round(s.t - t_start) if done else None, turn_key: n_turns})
        if not done:
            break
    s.track.append((s.t, *to_latlon(s.xy)))
    finished = len(legs_out) == len(course["legs"]) and legs_out[-1]["at_mark_s"] is not None
    return {"track": s.track, "legs": legs_out, "finished": finished,
            "finish_s": legs_out[-1]["within_80m_s"] if finished else None, "turns": s.tacks}


def sail_first_beat(start_xy, first_tack, gun, wind: Wind, boat: BoatModel, course, policy) -> dict:
    """First beat only: the full-race sailor stopped at mark 1."""
    r = sail_race(start_xy, first_tack, gun, wind, boat, {**course, "legs": course["legs"][:1]}, policy)
    leg = r["legs"][0] if r["legs"] else {}
    return {"time_to_mark_s": leg.get("within_80m_s"), "tacks": leg.get("tacks", 0), "track": r["track"],
            "reached": leg.get("at_mark_s") is not None}


# ------------------------------------------------------------------ real tracks: whole race
def real_race(fleet: Fleet, name: str, gun: float, course: dict) -> dict:
    """When a real boat came within REAL_MARK_RADIUS_M of each mark, in course order (None while its tracker
    had no data there), its tacks / gybes per leg, the share of each leg with data, and its finish time."""
    b = fleet.boats[name]
    t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(TZ)
    r = b[(b.index >= t0) & (b.index <= t0 + pd.Timedelta(seconds=MAX_RACE_S))]
    out, t_prev = [], t0
    for li, leg in enumerate(course["legs"]):
        # the leg ends at the mark, or - if the tracker had a gap there - where the boat's own mode changes
        # (beat -> downwind, run -> upwind); marks are only searched up to that boundary (+60 s), so a hidden
        # rounding is never matched with the next lap's pass of the same mark
        nxt = {"beat": "downwind", "run": "upwind"}.get(leg["type"])
        later = r[r.index > t_prev + pd.Timedelta(seconds=120)]
        flips = later.index[later["mode"] == nxt] if nxt else later.index[:0]
        cap = t_prev + pd.Timedelta(minutes=15)             # no visible switch (long gap): legs last < 15 min
        boundary = min(flips[0], cap) if len(flips) else cap
        after = r[(r.index > t_prev) & (r.index <= boundary + pd.Timedelta(seconds=60))]
        if li == len(course["legs"]) - 1:
            # the finish is passed once, at the end: first approach after FINISH_EARLIEST_S, whatever was hidden before
            after = r[r.index > t0 + pd.Timedelta(seconds=FINISH_EARLIEST_S)]
        dist = np.hypot(after.x - leg["mark"][0], after.y - leg["mark"][1])
        near = after.index[dist <= REAL_MARK_RADIUS_M]
        t_hit = near[0] if len(near) else None
        end = t_hit if t_hit is not None else boundary
        seg = r[(r.index > t_prev) & (r.index <= end)]
        if leg["type"] == "beat":
            k = seg[seg.tack != ""].tack
            turns = int((k != k.shift()).sum() - 1) if len(k) else None
        elif leg["type"] == "run":
            sgn = np.sign(seg[seg["mode"] == "downwind"].twa)
            turns = int((sgn != sgn.shift()).sum() - 1) if len(sgn) else None
        else:
            turns = 0
        span = (end - t_prev).total_seconds()
        turn_key = "tacks" if leg["type"] == "beat" else "gybes" if leg["type"] == "run" else "turns"
        out.append({"leg": li + 1, "type": leg["type"], "to": leg["to"],
                    "within_80m_s": round((t_hit - t0).total_seconds()) if t_hit is not None else None,
                    turn_key: turns, "data_coverage_pct": round(min(len(seg) * 10 / max(span, 10), 1) * 100)})
        # mark hidden by a gap: after a beat continue from the switch to downwind; after a run keep searching
        # from the run's start (its "upwind" switch may already be the sail back after the finish)
        t_prev = t_hit if t_hit is not None else (boundary if leg["type"] == "beat" else t_prev)
    return {"boat": name, "winner": name in fleet.winners, "legs": out, "finish_s": out[-1]["within_80m_s"] if out else None}


def at_timestamps(track, times):
    """Our 2 s track resampled to the given epoch timestamps (linear in time; holds the finish position after
    the finish)."""
    tr = np.array(track, dtype=float)
    t = np.asarray(times, dtype=float)
    return pd.DataFrame({"time_epoch": t, "lat": np.interp(t, tr[:, 0], tr[:, 1]),
                         "lng": np.interp(t, tr[:, 0], tr[:, 2])})


def lateral_stats(track, course):
    xy = np.array([to_xy(la, lo) for _, la, lo in track])
    lat = (xy - course["centre"]) @ unit(course["rhumb_deg"] + 90)
    return round(float(lat.mean())), round(float((lat > 0).mean() * 100))


def write_track(path: Path, track):
    pd.DataFrame(track, columns=["time_epoch", "lat", "lng"]).round({"lat": 7, "lng": 7}).to_csv(path, index=False)
