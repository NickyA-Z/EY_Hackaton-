#!/usr/bin/env python3
"""
Derive the race COURSE (buoy / line positions only) from all SailSync GPS tracks of a race day.

SailSync track files have no mark positions, so until official course data (SailSync analysis API or
the race committee) is available, the marks are inferred from where the whole fleet rounded them:

  windward mark 1 = median of the furthest-upwind point of each boat's FIRST beat after the gun, where
                   the track visibly rounds (continues without a tracker gap); other upwind marks =
                   clusters of later beat tops at least MIN_UPWIND_M upwind of the start line
  course seen     = beat 1 (~13 min) -> run -> beat 2 (~5 min) -> run -> beat 3 (~4 min) to the finish,
                   found by following each boat's sequence of legs
  mark 2          = top of the second beat (clean roundings, else the leading quarter of the fleet)
  leeward gate    = bottom of every run, split into two marks when the roundings form two groups side by side
  finish area     = where boats start a sustained (>= 2 min) slow period after their last leg
  Tracker gaps hit almost every boat at the top of beat 1, so a reach / offset mark there cannot be seen.
  start line     = positions of all boats at the official gun (probe_report.json): the line is the
                   main axis of the fleet, at the front row, ends = outermost boats

Output: location_agent/course/<date>.json - COORDINATES ONLY (no routes, sides, times or rankings),
plus how many boats each position is based on and its spread in metres (uncertainty).
The strategist reads only this file. Replace it when official course data arrives.

Run from the repo root:  python strategy/gps_analysis/derive_course.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyse_tracks import (KX, KY, LAT0, LON0, ROOT, TZ, angdiff, circmean, classify, gps_wind,  # noqa: E402
                            leg_top, legs_of, load_track)

TRACK_DIR = ROOT / "sailsync_api_results"
PROBE = TRACK_DIR / "probe_report.json"
OUT_DIR = ROOT / "location_agent" / "course"

CLUSTER_M = 150        # roundings closer than this to a cluster centre belong to the same mark
MIN_BOATS = 3          # a mark needs at least this many clean roundings
GATE_SPLIT_M = 20      # two leeward marks if the roundings split into groups at least this far apart
FRONT_ROW_M = 40       # start: boats within this distance of the front row define the line
LINE_END_PCT = (3, 97)  # start: line ends = these percentiles of the fleet along the line
MIN_UPWIND_M = 400     # an upwind mark must be at least this far upwind of the start line
MARK1_MIN_CLEAN = 5    # mark 1 from clean roundings needs this many boats, else the leading-quarter fallback
MIN_CONFIDENT = 5      # a mark found from fewer boats is flagged "uncertain"


def to_latlon(x, y):
    return round(float(LAT0 + y / KY), 6), round(float(LON0 + x / KX), 6)


def unit(bearing):
    return np.array([np.sin(np.radians(bearing)), np.cos(np.radians(bearing))])


def cluster(points: np.ndarray) -> list[np.ndarray]:
    """Greedy clustering of (x, y) points; returns arrays of member points, biggest first."""
    groups: list[list] = []
    for p in points:
        for g in groups:
            if np.hypot(*(p - np.median(np.array(g), axis=0))) <= CLUSTER_M:
                g.append(p)
                break
        else:
            groups.append([p])
    return sorted((np.array(g) for g in groups if len(g) >= MIN_BOATS), key=len, reverse=True)


def mark_record(pts: np.ndarray, mark_id: str) -> dict:
    cx, cy = np.median(pts, axis=0)
    lat, lon = to_latlon(cx, cy)
    spread = float(np.median(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)))
    return {"id": mark_id, "lat": lat, "lon": lon, "n_boats": int(len(pts)), "spread_m": round(spread)}


def split_gate(pts: np.ndarray, twd: float) -> list[np.ndarray]:
    """Leeward roundings -> one or two marks, split across the wind at the biggest gap."""
    across = pts @ unit(twd + 90)
    order = np.argsort(across)
    gaps = np.diff(across[order])
    if len(gaps):
        k = int(np.argmax(gaps))
        left, right = order[:k + 1], order[k + 1:]
        if gaps[k] >= GATE_SPLIT_M and len(left) >= MIN_BOATS and len(right) >= MIN_BOATS:
            return [pts[left], pts[right]]
    return [pts]


def start_line(raw: dict[str, pd.DataFrame], gun: float, twd: float) -> dict | None:
    """Fleet positions at the gun -> start line ends (left / right looking upwind)."""
    pos = []
    for d in raw.values():
        t = d.time_epoch.values
        if t[0] <= gun <= t[-1] and np.min(np.abs(t - gun)) <= 10:          # tracked at the gun
            pos.append((np.interp(gun, t, d.x.values), np.interp(gun, t, d.y.values)))
    if len(pos) < 5:
        return None
    p = np.array(pos)
    p = p[np.hypot(*(p - np.median(p, axis=0)).T) < 600]                      # drop boats away from the line
    up = unit(twd)
    front = np.percentile(p @ up, 90)
    row = p[(p @ up) >= front - FRONT_ROW_M]                                  # front row only
    c = row - row.mean(axis=0)
    axis = np.linalg.svd(c, full_matrices=False)[2][0]                        # main direction of the front row
    bearing = float(np.degrees(np.arctan2(axis[0], axis[1])) % 180)
    # ends along the line, at the front-row position
    along = p @ unit(bearing)
    a0, a1 = np.percentile(along, LINE_END_PCT)
    normal = unit(bearing + 90)
    if normal @ up < 0:
        normal = -normal
    off = float(np.median(row @ normal))
    ends = [unit(bearing) * a + normal * off for a in (a0, a1)]
    # left / right looking upwind
    right_dir = unit(twd + 90)
    ends.sort(key=lambda e: e @ right_dir)
    (lx, ly), (rx, ry) = ends
    resid = float(np.median(np.abs(row @ normal - off)))
    return {"left_end": dict(zip(("lat", "lon"), to_latlon(lx, ly))), "right_end": dict(zip(("lat", "lon"), to_latlon(rx, ry))),
            "bearing_deg": round(bearing), "length_m": round(float(a1 - a0)), "n_boats": int(len(p)),
            "n_front_row": int(len(row)), "front_row_spread_m": round(resid)}


def main(date: str = "2026-07-19"):
    probe = json.loads(PROBE.read_text())
    sess = next(s["assignment"] for s in probe["events"][0]["matching_sessions"] if s["assignment"]["date"] == date)
    guns = [r["time_range"]["start"] for r in sess["races"]]
    files = sorted(TRACK_DIR.glob(f"{sess['session_id']}_*.csv")) + sorted((TRACK_DIR / "winners").glob(f"{sess['session_id']}_*.csv"))
    print(f"{len(files)} tracks, races at", [f"{pd.Timestamp(g, unit='s', tz='UTC').tz_convert(TZ):%H:%M:%S}" for g in guns])

    boats, raw = {}, {}
    for f in files:
        boats[f.stem] = load_track(f)
        d = pd.read_csv(f).drop_duplicates("time_epoch").sort_values("time_epoch")
        d["x"], d["y"] = (d.lng - LON0) * KX, (d.lat - LAT0) * KY
        raw[f.stem] = d
    wind = gps_wind(boats)
    boats = {k: classify(v, wind) for k, v in boats.items()}
    legs = [l for v in boats.values() for l in legs_of(v)]

    races = []
    for i, gun in enumerate(guns):
        t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(TZ)
        t1 = (pd.Timestamp(guns[i + 1], unit="s", tz="UTC").tz_convert(TZ) - pd.Timedelta(minutes=5)
              if i + 1 < len(guns) else t0 + pd.Timedelta(minutes=80))
        w = wind[(wind.index >= t0 - pd.Timedelta(minutes=5)) & (wind.index <= t0 + pd.Timedelta(minutes=5))]
        twd_gun = circmean(w.twd_gps) if len(w) else circmean(wind.twd_gps)
        sl = start_line(raw, gun, twd_gun)
        sx, sy = (np.mean([(e["lon"] - LON0) * KX for e in (sl["left_end"], sl["right_end"])]),
                  np.mean([(e["lat"] - LAT0) * KY for e in (sl["left_end"], sl["right_end"])])) if sl else (0.0, 0.0)
        upwind_of_line = lambda x, y: (np.array([x - sx, y - sy]) @ unit(twd_gun))  # noqa: E731
        in_race = [l for l in legs if t0 - pd.Timedelta(seconds=60) <= l["seg"].index[0] <= t1]
        first_tops, tops, bottoms, first_any = [], [], [], {}
        for l in in_race:
            seg = l["seg"]
            if l["type"] == "upwind":
                p = leg_top(seg, circmean(seg.twd))
                if abs((seg.index[0] - t0).total_seconds()) <= 180:
                    first_any.setdefault(id(l["boat_df"]), (p.x, p.y))       # first beat, gap or not
            else:
                p = leg_top(seg, (circmean(seg.twd) + 180) % 360)
            if not ((seg.index[-1] - p.name).total_seconds() <= 60 and l["gap_after"] <= 40):
                continue                                                      # top cut by a tracker gap
            if l["type"] == "downwind":
                bottoms.append((p.x, p.y))
            elif upwind_of_line(p.x, p.y) >= MIN_UPWIND_M:                    # turns near the line are not buoys
                first = (seg.index[0] - t0).total_seconds() <= 180
                (first_tops if first else tops).append((p.x, p.y))
        mark1 = cluster(np.array(first_tops)) if first_tops else []
        if mark1 and len(mark1[0]) >= MARK1_MIN_CLEAN:
            mark1 = {**mark_record(mark1[0], f"R{i + 1}_M1"), "method": "clean roundings"}
        elif first_any:
            # tracker gaps near the mark for most boats: use the leading quarter of the fleet's first-beat tops
            pts = np.array(list(first_any.values()))
            up = np.array([upwind_of_line(x, y) for x, y in pts])
            lead = pts[up >= np.percentile(up, 75)]
            mark1 = {**mark_record(lead, f"R{i + 1}_M1"), "method": "leading quarter of first-beat tops (tracker gaps at the mark)"}
        else:
            mark1 = None
        if mark1:
            mark1.update(id="mark1", role="windward mark 1 (end of the first beat)", uncertain=mark1["n_boats"] < MIN_CONFIDENT)
        # ---- follow each boat's sequence of legs: first beat -> (reach) -> run -> beat 2 -> finish
        cand = {"mark2": [], "gate3": [], "finish": []}
        by_boat: dict[int, list] = {}
        for l in in_race:
            by_boat.setdefault(id(l["boat_df"]), []).append(l)
        for seq in by_boat.values():
            seq.sort(key=lambda l: l["seg"].index[0])
            b = seq[0]["boat_df"]
            fb = next((k for k, l in enumerate(seq) if l["type"] == "upwind"
                       and abs((l["seg"].index[0] - t0).total_seconds()) <= 180), None)
            if fb is None:
                continue
            # course seen in the data: beat 1 (~13 min) -> run -> beat 2 (~5 min) -> run -> beat 3 (~4 min) to finish.
            # Tracker gaps hide almost every rounding at the top of beat 1, so a reach / offset mark there is invisible.
            runs = [k for k in range(fb + 1, len(seq)) if seq[k]["type"] == "downwind"]
            for k in runs:                                                    # gate = bottom of every run
                rs = seq[k]["seg"]
                bot = leg_top(rs, (circmean(rs.twd) + 180) % 360)
                if (rs.index[-1] - bot.name).total_seconds() <= 60 and seq[k]["gap_after"] <= 40:
                    cand["gate3"].append((bot.x, bot.y))
            if runs:
                b2 = next((k for k in range(runs[0] + 1, len(seq)) if seq[k]["type"] == "upwind"), None)
                if b2 is not None:                                            # mark 2 = top of the second beat
                    s2 = seq[b2]["seg"]
                    top2 = leg_top(s2, circmean(s2.twd))
                    clean = (s2.index[-1] - top2.name).total_seconds() <= 60 and seq[b2]["gap_after"] <= 40
                    cand["mark2"].append((top2.x, top2.y, clean))
            # finish = start of the first sustained slow period (>= 2 min) after the last racing leg
            after = b[(b.index > seq[-1]["seg"].index[-1]) & (b.index <= t1)]
            slow = (after.speed_kn < 2.5).astype(int)
            run_len = slow.groupby((slow != slow.shift()).cumsum()).transform("sum") * slow
            stop = after[run_len >= 12]                                       # 12 x 10 s = 2 min
            if len(stop) and (stop.index[0] - t0).total_seconds() >= 25 * 60:
                cand["finish"].append((stop.iloc[0].x, stop.iloc[0].y))

        def best(role, label):
            groups = cluster(np.array(cand[role])) if cand[role] else []
            if not groups:
                return None
            m = mark_record(groups[0], role)
            m.update(role=label, uncertain=m["n_boats"] < MIN_CONFIDENT)
            return m
        finish = best("finish", "finish area (where boats stop racing; approximate)")
        gate = []
        g3 = cluster(np.array(cand["gate3"])) if cand["gate3"] else []
        # mark 2: clean second-beat tops, else the leading quarter of all second-beat tops (as for mark 1),
        # counting only tops well upwind of the gate (a top near the gate = beat cut short by a gap)
        mark2 = None
        if g3 and cand["mark2"]:
            gx, gy = np.median(g3[0], axis=0)
            pts = np.array([(x, y) for x, y, _ in cand["mark2"]])
            okc = np.array([c for _, _, c in cand["mark2"]])
            upg = (pts - [gx, gy]) @ unit(twd_gun)
            far = upg >= MIN_UPWIND_M / 2
            clean_g = cluster(pts[far & okc]) if (far & okc).any() else []
            if clean_g and len(clean_g[0]) >= MARK1_MIN_CLEAN:
                mark2 = {**mark_record(clean_g[0], "mark2"), "method": "clean roundings"}
            elif far.sum() >= MIN_BOATS:
                lead = pts[far][upg[far] >= np.percentile(upg[far], 75)]
                mark2 = {**mark_record(lead, "mark2"), "method": "leading quarter of second-beat tops (tracker gaps at the mark)"}
            if mark2:
                mark2.update(role="windward mark 2 (top of the second, shorter beat from the gate)",
                             uncertain=mark2["n_boats"] < MIN_CONFIDENT or mark2["spread_m"] > 100)
        if g3:
            parts = split_gate(g3[0], twd_gun)
            names = ["gate3_left", "gate3_right"] if len(parts) == 2 else ["gate3"]
            if len(parts) == 2:   # order left / right looking upwind
                parts.sort(key=lambda pp: float(np.median(pp, axis=0) @ unit(twd_gun + 90)))
            for nm, pp in zip(names, parts):
                m = mark_record(pp, nm)
                m.update(role="leeward gate (bottom of the first run)" if len(parts) == 2 else "leeward mark (bottom of the first run)",
                         uncertain=m["n_boats"] < MIN_CONFIDENT)
                gate.append(m)
        buoys = (2 if sl else 0) + sum(1 for m in (mark1, mark2) if m) + len(gate) + (1 if finish else 0)
        races.append({"race": i + 1, "gun_local": f"{t0:%H:%M:%S}", "start_line": sl, "mark1": mark1, "mark2": mark2,
                      "gate3": gate, "finish": finish, "buoys_found": buoys,
                      "legs_seen": "beat 1 (~13 min) -> run (~9) -> beat 2 to mark 2 (~5) -> run (~6) -> beat 3 to finish (~4)",
                      "note": "start line = 2 buoys (committee boat + pin; which is which is unknown). "
                              "'uncertain' = fewer than %d boats rounded cleanly (tracker gaps)." % MIN_CONFIDENT})

    out = {
        "date": date, "venue": "Port of LA boat course (outside San Pedro breakwater)", "boat_class": sess["boat_class"],
        "source": f"derived from {len(files)} SailSync GPS tracks (session {sess['session_id']}): mark positions = median of "
                  "clean roundings, start line = fleet at the official gun. Replace with official course data when available.",
        "contains": "coordinates only - no routes, sides, times or results",
        "races": races,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    f = OUT_DIR / f"{date}.json"
    f.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(races, indent=1))
    print("->", f.relative_to(ROOT))


if __name__ == "__main__":
    main(*sys.argv[1:])
