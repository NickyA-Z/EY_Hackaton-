#!/usr/bin/env python3
"""
GPS-track analysis of the 19 July 2026 San Pedro test regatta (ILCA 7, four winners).

Input : sailsync_api_results/winners/*.csv   (time_epoch, lat, lng; ~1.7 s)
Output: strategy/gps_analysis/results/
          wind_from_gps.csv   GPS-derived wind direction every 2 min (from the two tack headings)
          legs.csv            one row per boat x leg: type, times, speed, VMG, tacks, side of course
          marks.json          windward / leeward mark positions per race (cluster of roundings)
          summary.json        races, wind trend per race, side-choice stats, model/station comparison

Method (no AI, plain geometry):
  1. Resample each track to 10 s, compute speed and course over ground (COG).
  2. Wind direction from tacking: upwind, boats sail ~45 deg either side of the wind, so the
     wind direction is the bisector of the starboard-tack and port-tack COG. Pooled over the
     four boats in sliding 10-min windows.
  3. True wind angle TWA = COG - wind. |TWA| < 70 upwind (TWA < 0 starboard, > 0 port),
     |TWA| > 110 downwind. Contiguous runs give legs; leg ends give mark roundings.
  4. Side of course on each beat: lateral offset from the wind axis through the windward mark,
     positive = RIGHT side looking upwind.

Run from the repo root:  python strategy/gps_analysis/analyse_tracks.py
Needs: numpy, pandas.
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TRACKS = ROOT / "sailsync_api_results" / "winners"
OUT = Path(__file__).resolve().parent / "results"
TZ = "America/Los_Angeles"
LAT0, LON0 = 33.687, -118.271                      # course centre (local metric frame)
KX, KY = 111320 * np.cos(np.radians(LAT0)), 110540
KN = 1.94384
RES = "10s"
MIN_SPEED = 2.5                                    # kn; slower = drifting / between races
UPWIND_MAX, DOWNWIND_MIN = 70, 110                 # |TWA| thresholds (deg)
MIN_LEG_S = 180                                    # legs shorter than this are ignored
TWD_SEARCH = (200, 330)                            # sea-breeze sector searched for the wind direction
UPWIND_MAX_KN = 6.5                                # ILCA upwind speeds stay below this
MARK_CLUSTER_M = 350                               # leg tops closer than this belong to one mark
STATIONS = ROOT / "src" / "conditions_July" / "data" / "raw"


def angdiff(a, b):
    """Signed smallest difference a - b in degrees (-180, 180]."""
    return (np.asarray(a) - np.asarray(b) + 180) % 360 - 180


def circmean(deg):
    r = np.radians(np.asarray(deg, dtype=float))
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


# 1. load ---------------------------------------------------------------------------
def load_track(f: Path) -> pd.DataFrame:
    """One SailSync CSV (time_epoch, lat, lng) -> 10 s series with x/y (m), speed_kn, cog."""
    d = pd.read_csv(f).drop_duplicates("time_epoch").sort_values("time_epoch")
    d.index = pd.to_datetime(d.time_epoch, unit="s", utc=True).dt.tz_convert(TZ)
    d["x"], d["y"] = (d.lng - LON0) * KX, (d.lat - LAT0) * KY
    s = d[["x", "y", "lat", "lng"]].resample(RES).mean().interpolate(limit=2, limit_area="inside")
    dx, dy = s.x.diff(), s.y.diff()
    s["speed_kn"] = np.hypot(dx, dy) / pd.Timedelta(RES).total_seconds() * KN
    s["cog"] = np.degrees(np.arctan2(dx, dy)) % 360
    return s.dropna()


def load_tracks() -> dict[str, pd.DataFrame]:
    boats = {}
    for f in sorted(TRACKS.glob("*.csv")):
        parts = f.stem.split("_")
        boats[f"{parts[-3]} ({parts[-2]})"] = load_track(f)       # e.g. "Wearn (AUS)"
    return boats


# 2. wind from tacking ---------------------------------------------------------------
def gps_wind(boats, window="10min", step="2min") -> pd.DataFrame:
    a = pd.concat(boats.values())
    a = a[a.speed_kn > MIN_SPEED].sort_index()
    rows = []
    t = a.index.min().floor(step)
    while t <= a.index.max():
        w = a[(a.index >= t - pd.Timedelta(window) / 2) & (a.index < t + pd.Timedelta(window) / 2)]
        best = None
        if len(w) > 30:
            cog, spd = w.cog.values, w.speed_kn.values
            # coarse search: wind direction that best explains two tack clusters at +-45 deg.
            # Search the sea-breeze sector only, and require upwind-like speeds so that
            # downwind gybes (also ~90 deg apart) are not mistaken for tacks.
            for twd in range(TWD_SEARCH[0], TWD_SEARCH[1] + 1, 2):
                stb = (np.abs(angdiff(cog, twd - 45)) < 15) & (spd < UPWIND_MAX_KN)
                prt = (np.abs(angdiff(cog, twd + 45)) < 15) & (spd < UPWIND_MAX_KN)
                score = min(stb.sum(), prt.sum())
                if best is None or score > best[0]:
                    best = (score, twd, stb, prt)
        if best and best[0] >= 6:
            _, _, stb, prt = best
            h_stb, h_prt = circmean(w.cog[stb]), circmean(w.cog[prt])
            twd = (h_stb + angdiff(h_prt, h_stb) / 2) % 360
            rows.append({"time": t, "twd_gps": round(twd, 1), "stbd_cog": round(h_stb, 1), "port_cog": round(h_prt, 1),
                         "tack_angle": round(angdiff(h_prt, h_stb), 1), "n_stbd": int(stb.sum()), "n_port": int(prt.sum())})
        t += pd.Timedelta(step)
    return pd.DataFrame(rows).set_index("time")


# 3. legs ----------------------------------------------------------------------------
def classify(boat: pd.DataFrame, wind: pd.DataFrame) -> pd.DataFrame:
    twd = wind.twd_gps.reindex(boat.index.union(wind.index))
    # interpolate direction safely via unit vectors
    r = np.radians(twd)
    s, c = pd.Series(np.sin(r), index=twd.index).interpolate(limit_direction="both"), \
        pd.Series(np.cos(r), index=twd.index).interpolate(limit_direction="both")
    boat = boat.copy()
    boat["twd"] = (np.degrees(np.arctan2(s, c)) % 360).reindex(boat.index)
    boat["twa"] = angdiff(boat.cog, boat.twd)
    state = np.where(boat.speed_kn < MIN_SPEED, "slow",
                     np.where(np.abs(boat.twa) < UPWIND_MAX, "upwind",
                              np.where(np.abs(boat.twa) > DOWNWIND_MIN, "downwind", "reach")))
    # smooth: majority state over 90 s, ignoring "slow"/"reach" blips
    st = pd.Series(state, index=boat.index)
    num = st.map({"upwind": 1.0, "downwind": -1.0}).rolling("90s", center=True).mean()
    boat["mode"] = np.where(num > 0.2, "upwind", np.where(num < -0.2, "downwind", "other"))
    boat["tack"] = np.where(boat["mode"] == "upwind", np.where(boat.twa < 0, "starboard", "port"), "")
    return boat


def legs_of(boat: pd.DataFrame) -> list[dict]:
    legs, cur, start = [], None, None
    modes = boat["mode"].values
    idx = boat.index
    for i, m in enumerate(list(modes) + ["end"]):
        if m != cur:
            if cur in ("upwind", "downwind") and start is not None:
                seg = boat.iloc[start:i]
                if (seg.index[-1] - seg.index[0]).total_seconds() >= MIN_LEG_S:
                    # seconds of missing data right before / after the leg (tracker gaps)
                    gap_after = (idx[i] - idx[i - 1]).total_seconds() if i < len(idx) else 1e9
                    gap_before = (idx[start] - idx[start - 1]).total_seconds() if start > 0 else 1e9
                    prev_mode = modes[max(start - 1, 0)]
                    legs.append({"type": cur, "seg": seg, "gap_after": gap_after, "gap_before": gap_before,
                                 "boat_df": boat, "prev_mode": prev_mode})
            cur, start = m, i
    return legs


def find_races(all_legs, min_boats=3, sync_s=120, finish_margin_min=10):
    """Race start = >= min_boats boats beginning an upwind leg within sync_s of each other,
    after pre-start manoeuvring: in the 4 min before, the boat is tracked continuously and spends
    some time slow (< 2.5 kn). A leeward-mark rounding instead follows a fast run (and often a
    tracker gap). Race end = end of the last downwind leg that starts before (next start - finish_margin)."""
    def start_like(l):
        b, t0 = l["boat_df"], l["seg"].index[0]
        pre = b[(b.index >= t0 - pd.Timedelta(minutes=4)) & (b.index < t0)]
        return len(pre) >= 20 and (pre.speed_kn < MIN_SPEED).mean() >= 0.10

    ups = sorted((l["seg"].index[0], boat) for boat, legs in all_legs.items() for l in legs
                 if l["type"] == "upwind" and start_like(l))
    starts, i = [], 0
    while i < len(ups):
        grp = [u for u in ups[i:] if (u[0] - ups[i][0]).total_seconds() <= sync_s]
        if len({b for _, b in grp}) >= min_boats and (not starts or ups[i][0] - starts[-1] > pd.Timedelta(minutes=25)):
            starts.append(ups[i][0])
            i += len(grp)
        else:
            i += 1
    races = []
    for k, s in enumerate(starts):
        nxt = starts[k + 1] - pd.Timedelta(minutes=finish_margin_min) if k + 1 < len(starts) else s + pd.Timedelta(hours=3)
        dn_ends = [l["seg"].index[-1] for legs in all_legs.values() for l in legs
                   if l["type"] == "downwind" and s <= l["seg"].index[0] < nxt]
        races.append((s - pd.Timedelta(seconds=30), max(dn_ends) if dn_ends else s + pd.Timedelta(minutes=60)))
    return races


def leg_top(seg: pd.DataFrame, twd: float):
    """Furthest-upwind point of a beat (approximates where it reached the windward mark)."""
    u = np.array([np.sin(np.radians(twd)), np.cos(np.radians(twd))])
    i = int(np.argmax(seg.x * u[0] + seg.y * u[1]))
    return seg.iloc[i]


def cluster_marks(points, radius=MARK_CLUSTER_M, min_members=2):
    """Greedy clustering of (x, y, lat, lng) points; returns clusters with >= min_members."""
    clusters = []
    for p in points:
        for c in clusters:
            if np.hypot(p[0] - c["cx"], p[1] - c["cy"]) <= radius:
                c["pts"].append(p)
                arr = np.array(c["pts"])
                c["cx"], c["cy"] = np.median(arr[:, 0]), np.median(arr[:, 1])
                break
        else:
            clusters.append({"pts": [p], "cx": p[0], "cy": p[1]})
    out = []
    for c in clusters:
        if len(c["pts"]) >= min_members:
            arr = np.array(c["pts"])
            out.append({"x_m": round(float(np.median(arr[:, 0]))), "y_m": round(float(np.median(arr[:, 1]))),
                        "lat": round(float(np.median(arr[:, 2])), 6), "lon": round(float(np.median(arr[:, 3])), 6),
                        "legs": len(c["pts"])})
    return out


# 4. side of course -------------------------------------------------------------------
def side_metrics(seg: pd.DataFrame, from_xy, mark_xy, twd) -> dict:
    """Side of course relative to the rhumb line from the leg's start (start-line centre or gate)
    to the windward mark. Positive = RIGHT side looking toward the mark."""
    dx, dy = mark_xy[0] - from_xy[0], mark_xy[1] - from_xy[1]
    rhumb = float(np.degrees(np.arctan2(dx, dy)) % 360)
    right = np.array([np.sin(np.radians(rhumb + 90)), np.cos(np.radians(rhumb + 90))])
    lat = (seg.x - from_xy[0]) * right[0] + (seg.y - from_xy[1]) * right[1]
    return {"rhumb_bearing": round(rhumb), "course_skew_deg": round(float(angdiff(rhumb, twd))),
            "lateral_mean_m": round(float(lat.mean())), "lateral_max_right_m": round(float(lat.max())),
            "lateral_max_left_m": round(float(-lat.min())), "pct_time_right": round(float((lat > 0).mean() * 100))}


def load_station_wind(sid: str) -> pd.Series | None:
    f = STATIONS / "noaa_coops" / f"{sid}_wind_202607.csv"
    if not f.exists():
        return None
    rows = list(csv.reader(open(f)))[1:]
    t = pd.to_datetime([r[0] for r in rows]).tz_localize("UTC").tz_convert(TZ)
    return pd.DataFrame({"dir": pd.to_numeric([r[2] for r in rows], errors="coerce"),
                         "kn": pd.to_numeric([r[1] for r in rows], errors="coerce") * KN}, index=t)


def load_hrrr() -> pd.DataFrame | None:
    f = STATIONS / "hrrr" / "port_la_course_202607.json"
    if not f.exists():
        return None
    m = json.load(open(f))["minutely_15"]
    t = pd.to_datetime(m["time"]).tz_localize(TZ)
    return pd.DataFrame({"dir": m["wind_direction_10m"], "kn": m["wind_speed_10m"]}, index=t)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    boats = load_tracks()
    wind = gps_wind(boats)
    boats = {k: classify(v, wind) for k, v in boats.items()}
    all_legs = {k: legs_of(v) for k, v in boats.items()}
    races = find_races(all_legs)

    def race_of(t):
        return next((i for i, (rs, re) in enumerate(races, 1) if rs <= t <= re), None)

    # racing legs only (pre-start practice and sailing back after the finish are dropped)
    racing = [(boat, l) for boat, legs in all_legs.items() for l in legs if race_of(l["seg"].index[0])]

    # start line: boat positions when each race's first beat begins
    start_lines = []
    for ri, (rs, re) in enumerate(races, 1):
        pts = [l["seg"].iloc[0] for b, l in racing if l["type"] == "upwind" and race_of(l["seg"].index[0]) == ri
               and (l["seg"].index[0] - rs).total_seconds() < 180]
        if pts:
            ys = [p.y for p in pts]
            start_lines.append({"race": ri, "time": f"{rs + pd.Timedelta(seconds=30):%H:%M}",
                                "x_m": round(float(np.median([p.x for p in pts]))), "y_min_m": round(min(ys)),
                                "y_max_m": round(max(ys)), "boats": len(pts)})

    # windward marks: cluster the furthest-upwind point of every beat that visibly rounds a mark,
    # i.e. the top is at the end of the beat AND the track continues without a data gap.
    tops, clean = {}, []
    for b, l in racing:
        if l["type"] == "upwind":
            p = leg_top(l["seg"], circmean(l["seg"].twd))
            tops[id(l)] = p
            if (l["seg"].index[-1] - p.name).total_seconds() <= 60 and l["gap_after"] <= 40:
                clean.append((p.x, p.y, p.lat, p.lng))
    marks = cluster_marks(clean, min_members=1)
    for k, m in enumerate(marks, 1):
        m["id"] = f"W{k}"

    # legs table
    rows = []
    for boat, l in racing:
        seg = l["seg"]
        ri = race_of(seg.index[0])
        twd = circmean(seg.twd)
        vmg = seg.speed_kn * np.cos(np.radians(seg.twa))
        r = {"boat": boat, "race": ri, "type": l["type"], "start": seg.index[0].strftime("%H:%M:%S"),
             "end": seg.index[-1].strftime("%H:%M:%S"), "minutes": round((seg.index[-1] - seg.index[0]).total_seconds() / 60, 1),
             "twd_gps": round(twd), "speed_kn": round(float(seg.speed_kn.median()), 2),
             "vmg_kn": round(float(np.abs(vmg).median()), 2)}
        if l["type"] == "upwind":
            tk = seg.tack[seg.tack != ""]
            r["tacks"] = int((tk != tk.shift()).sum() - 1)
            r["pct_port"] = round(float((tk == "port").mean() * 100))
            top = tops[id(l)]
            if marks:
                d = [np.hypot(top.x - m["x_m"], top.y - m["y_m"]) for m in marks]
                m = marks[int(np.argmin(d))]
                r["mark"] = m["id"]
                r["reached_mark"] = bool(min(d) <= 150)       # False = leg cut short by a tracker gap
                sl = next((s for s in start_lines if s["race"] == ri), None)
                first_beat = sl is not None and (seg.index[0] - races[ri - 1][0]).total_seconds() < 180
                origin = (sl["x_m"], (sl["y_min_m"] + sl["y_max_m"]) / 2) if first_beat else (seg.x.iloc[0], seg.y.iloc[0])
                r["beat"] = "first (from start)" if first_beat else "later (from gate)"
                r.update(side_metrics(seg, origin, (m["x_m"], m["y_m"]), twd))
        rows.append(r)
    legs_df = pd.DataFrame(rows).sort_values(["race", "start"])
    legs_df.to_csv(OUT / "legs.csv", index=False)
    wind.to_csv(OUT / "wind_from_gps.csv")
    (OUT / "marks.json").write_text(json.dumps({"start_lines": start_lines, "windward_marks": marks,
                                                 "frame": f"x/y metres east/north of {LAT0}, {LON0}"}, indent=2))

    # wind trend per race and comparison with station / model
    trend = []
    for ri, (rs, re) in enumerate(races, 1):
        w = wind[(wind.index >= rs) & (wind.index <= re)]
        if len(w) >= 4:
            hrs = (w.index - w.index[0]).total_seconds() / 3600
            unwrapped = w.twd_gps.values[0] + np.cumsum(np.r_[0, angdiff(w.twd_gps.values[1:], w.twd_gps.values[:-1])])
            slope = np.polyfit(hrs, unwrapped, 1)
            resid = unwrapped - np.polyval(slope, hrs)
            trend.append({"race": ri, "window": f"{rs:%H:%M}-{re:%H:%M}", "twd_start": round(float(w.twd_gps.iloc[0])),
                          "twd_end": round(float(w.twd_gps.iloc[-1])), "twd_mean": round(circmean(w.twd_gps)),
                          "trend_deg_per_h": round(float(slope[0]), 1), "oscillation_sd_deg": round(float(resid.std()), 1),
                          "tack_angle_median": round(float(w.tack_angle.median()))})
    comp = []
    ag, hr = load_station_wind("9410647"), load_hrrr()
    for h in range(14, 18):
        t = pd.Timestamp(f"2026-07-19 {h:02d}:00", tz=TZ)
        g = wind[(wind.index >= t - pd.Timedelta("10min")) & (wind.index <= t + pd.Timedelta("10min"))]
        rec = {"hour": f"{h:02d}:00", "gps_twd": round(circmean(g.twd_gps)) if len(g) else None}
        if ag is not None and t in ag.index:
            rec.update(angels_gate_dir=float(ag.loc[t, "dir"]), angels_gate_kn=round(float(ag.loc[t, "kn"]), 1))
        if hr is not None and t in hr.index:
            rec.update(hrrr_dir=float(hr.loc[t, "dir"]), hrrr_kn=float(hr.loc[t, "kn"]))
        comp.append(rec)

    up = legs_df[legs_df.type == "upwind"]
    dn = legs_df[legs_df.type == "downwind"]
    full = up[up.get("reached_mark", False) == True]  # noqa: E712  beats with no tracker gap at the top
    beats = []
    for (ri, mk), g in full.groupby(["race", "mark"]):
        beats.append({"race": int(ri), "mark": mk, "boats": int(len(g)),
                      "pct_time_right_mean": round(float(g.pct_time_right.mean())),
                      "boats_mostly_right": int((g.pct_time_right > 50).sum()),
                      "pct_port_tack_mean": round(float(g.pct_port.mean())), "course_skew_deg": int(g.course_skew_deg.median()),
                      "first_to_mark": g.sort_values("end").iloc[0].boat,
                      "first_to_mark_pct_right": int(g.sort_values("end").iloc[0].pct_time_right)})
    summary = {
        "event": "San Pedro test regatta, 19 July 2026, ILCA 7 (SailSync event 2796)",
        "boats": list(boats),
        "races": [{"race": i, "start": f"{s + pd.Timedelta(seconds=30):%H:%M}", "end": f"{e:%H:%M}"}
                  for i, (s, e) in enumerate(races, 1)],
        "start_lines": start_lines,
        "windward_marks": marks,
        "wind_from_gps": trend,
        "wind_comparison_gps_vs_station_vs_model": comp,
        "upwind": {"legs": int(len(up)), "legs_reaching_mark": int(len(full)),
                   "speed_kn_median": float(up.speed_kn.median()), "vmg_kn_median": float(up.vmg_kn.median()),
                   "tacks_per_leg_median": float(up.tacks.median()), "pct_time_on_port_tack": round(float(up.pct_port.mean())),
                   "side_by_beat": beats},
        "downwind": {"legs": int(len(dn)), "speed_kn_median": float(dn.speed_kn.median()),
                     "vmg_kn_median": float(dn.vmg_kn.median())},
        "data_quality": "Tracker gaps of 5-13 min at the same times for all boats (mostly around mark roundings); "
                        "beats cut by a gap are kept for speed but excluded from side-of-course stats.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: summary[k] for k in ("races", "start_lines", "windward_marks", "wind_from_gps",
                                              "wind_comparison_gps_vs_station_vs_model", "upwind", "downwind")},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
