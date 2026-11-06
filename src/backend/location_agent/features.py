#!/usr/bin/env python3
"""
Step 2 - features: standard conditions table + geo rasters -> briefing pack JSON,
organised as the 9 strategic building blocks of "Boat brief and strategy.docx" (section 2).

    PYTHONPATH=src python -m backend.location_agent.features --date 2026-07-19 --area port_la_course
    PYTHONPATH=src python -m backend.location_agent.features --date 2026-07-19 --area port_la_course --no-backtest
    PYTHONPATH=src python -m backend.location_agent.features --date 2026-07-19 --area belmont_course

The pack contains NUMBERS ONLY (no labels, verdicts or thresholds). Each block:
    {"evidence": {...}, "venue_percentiles": {...}, "data_sources": [...], "data_quality": "..."}
A venue percentile = % of July days (climatology years) with a value <= the race-day value.
The brief's definitions / rules of thumb are given to the AI separately (system prompt).

Backtest mode (default) = only what a coach could know on the race-day morning:
  climatology excludes the race year; measured race-day data stops at --cutoff (11:00 local);
  reports published on/after the race day are excluded; race-day wind = the HRRR forecast
  issued ~24 h before (from 2024). Hindsight mode uses near-real-time HRRR for the race day.

Every feature is documented in docs/location_agent_features.md.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml
from scipy import ndimage

from backend import paths

ROOT = paths.ROOT
PKG = Path(__file__).resolve().parent      # holds settings.yaml
CONDITIONS = paths.LOCATION_AGENT_CONDITIONS_FILE
BATHY = paths.GEO_LA28_DIR / "bathymetry_ncei.tif"
TERRAIN = paths.GEO_LA28_DIR / "terrain.tif"
GPS_RESULTS = paths.LOCATION_AGENT_GPS_RESULTS_DIR     # hindsight lessons only
COURSE_DIR = paths.LOCATION_AGENT_COURSE_DIR                                      # <date>.json: buoy / line coordinates only


def fingerprint(race_day: date, area: str, window, cutoff_h: int, backtest: bool) -> str:
    """Short hash of everything the feature numbers depend on. Same hash = stored pack still valid.
    Covers: the standard table (size + modified time), terrain/depth rasters, settings.yaml, the course
    file, this file's code, the GPS summary (hindsight only) and the run parameters.
    The RAG insights text (inputs/<date>_rag_insights.txt) is NOT included - the strategist attaches it at call time."""
    import hashlib
    h = hashlib.sha256(f"{race_day}|{area}|{tuple(window)}|{cutoff_h}|{backtest}".encode())
    for f in (CONDITIONS, BATHY, TERRAIN):
        st = f.stat() if f.exists() else None
        h.update(f"{f.name}:{st.st_size}:{int(st.st_mtime)}".encode() if st else f"{f.name}:missing".encode())
    extra = [SETTINGS_FILE, Path(__file__), course_file(race_day)]
    if not backtest:
        extra.append(GPS_RESULTS / "summary.json")
    for f in extra:
        h.update(f.read_bytes() if f and f.exists() else b"missing")
    return h.hexdigest()[:12]


def pack_path(race_day: date, area: str, backtest: bool) -> Path:
    return paths.LOCATION_AGENT_OUTPUT_DIR / f"{race_day.isoformat()}_{area}{'' if backtest else '_hindsight'}" / "briefing_pack.json"


def load_or_build(race_day: date, area: str, window=None, cutoff_h=None, backtest=True, rebuild=False):
    """Stored features first. Returns (pack, path, status).
      no flag:    use the stored pack as is (built once if missing); warn if its inputs have changed
      rebuild:    recompute ONLY if the inputs differ from the stored pack's fingerprint"""
    window = tuple(window or S["race_window_local"])
    cutoff_h = S["morning_cutoff_hour"] if cutoff_h is None else cutoff_h
    f = pack_path(race_day, area, backtest)
    fp = fingerprint(race_day, area, window, cutoff_h, backtest)
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    old_fp = (old or {}).get("context", {}).get("fingerprint")
    if old is not None and (old_fp == fp or not rebuild):
        status = "stored (unchanged)" if old_fp == fp else \
            "stored - WARNING: inputs changed since it was built; run with --rebuild to refresh"
        return old, f, status
    pack = build_pack(race_day, area, window, cutoff_h, backtest)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(pack, indent=1, ensure_ascii=False), encoding="utf-8")
    return pack, f, "built (no stored pack)" if old is None else "rebuilt (inputs changed)"


def course_file(d: date) -> Path | None:
    """The course file for the race day, else the latest one before it (a layout known in advance)."""
    exact = COURSE_DIR / f"{d.isoformat()}.json"
    if exact.exists():
        return exact
    earlier = sorted(f for f in COURSE_DIR.glob("*.json") if f.stem < d.isoformat())
    return earlier[-1] if earlier else None
TZ = "America/Los_Angeles"

# Measurement settings (not decision thresholds) - edit src/backend/location_agent/settings.yaml, not this file.
SETTINGS_FILE = PKG / "settings.yaml"
DEFAULT_SETTINGS = {
    "race_window_local": [13, 17], "morning_cutoff_hour": 11, "veer_window_local": [12, 17],
    "climatology_hours_local": [10, 18],
    "sea_breeze_onset": {"min_speed_kn": 8, "sector_from_deg": [225, 295], "min_duration_h": 1},
    "land_sea_dT_inland_hour": 14,
    "lanes": {"offset_m": 300, "points": 9, "from_fraction": 0.1, "to_fraction": 0.9},
    "land_definition": {"bathymetry_land_m": 0, "terrain_land_m": 1, "terrain_obstacle_m": 2},
    "upwind_terrain_scan": {"length_m": 12000, "step_m": 30},
    "shelter_table_dirs_deg": {"from": 230, "to": 340, "step": 10},
    "shoreline_radius_m": 3000, "start_line_sensitivity_deg": 5,
    "boat_class_priors": {"class": "ILCA 7", "tack_angle_deg": 90, "upwind_vmg_kn": 3.4},
    "morning_cloud_hours_local": [9, 12], "cloud_clear_pct": 30,
}


def load_settings(path: Path = SETTINGS_FILE) -> dict:
    """Values from settings.yaml (each entry's 'value'), falling back to DEFAULT_SETTINGS per key."""
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    if path.exists():
        for k, entry in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).items():
            v = entry.get("value") if isinstance(entry, dict) and "value" in entry else entry
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            else:
                s[k] = v
    return s


S = load_settings()
SEA_BREEZE_SECTOR = tuple(S["sea_breeze_onset"]["sector_from_deg"])
SEA_BREEZE_MIN_KN = float(S["sea_breeze_onset"]["min_speed_kn"])
LANE_OFFSET_M = S["lanes"]["offset_m"]
RAY_MAX_M = S["upwind_terrain_scan"]["length_m"]
RAY_STEP_M = S["upwind_terrain_scan"]["step_m"]
ILCA_TACK_ANGLE_DEG = S["boat_class_priors"]["tack_angle_deg"]
ILCA_UPWIND_VMG_KN = S["boat_class_priors"]["upwind_vmg_kn"]
VEER_H0, VEER_H1 = S["veer_window_local"]
CLIM_H0, CLIM_H1 = S["climatology_hours_local"]
ONSET_MIN_H = S["sea_breeze_onset"]["min_duration_h"]

AREA_CENTRES = {"port_la_course": (33.687, -118.271), "belmont_course": (33.748, -118.140)}
AREA_NAMES = {"port_la_course": "Port of LA boat course (outside San Pedro breakwater)",
              "belmont_course": "Belmont Shore board course (inside Long Beach breakwater)"}

# Venue knowledge from the brief, with the date it became available (filtered in backtest).
PRIOR_KNOWLEDGE = [
    ("1932-08-01", "1932 Olympic report: westerly, eight to fifteen knots, from midday (Port of LA outer harbour)."),
    ("2026-06-15", "Long Beach Race Week briefing (June 2026): 10-14 kt WSW-W in the afternoon, peaking 14:00-17:00; "
                   "inside the harbour 2-5 kt lighter than outside the breakwater."),
    ("2026-07-19", "World Sailing day-1 report (19 Jul 2026, San Pedro): about 12-18 kt and ~3 ft ocean swell; "
                   "ILCA: 'getting all the way to the right side'."),
    ("2026-08-08", "World Sailing week-2 report (8 Aug 2026): much of the fleet launching off the line on port "
                   "to reach the favoured right side; pressure differences across the course."),
]


# ============================================================ helpers
def circmean(deg) -> float:
    r = np.radians(np.asarray(deg, dtype=float))
    r = r[~np.isnan(r)]
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360) if r.size else float("nan")


def angdiff(a, b):
    return (np.asarray(a, dtype=float) - np.asarray(b, dtype=float) + 180) % 360 - 180


def unwrap_deg(deg):
    d = np.asarray(deg, dtype=float)
    return d[0] + np.concatenate([[0], np.cumsum(angdiff(d[1:], d[:-1]))]) if d.size else d


def r(x, nd=1):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, nd)


def hhmm(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else f"{int(x):02d}:{int(round((x % 1) * 60)) % 60:02d}"


def pct_rank(value, dist) -> float | None:
    d = np.asarray([v for v in dist if v is not None and not (isinstance(v, float) and math.isnan(v))], dtype=float)
    if value is None or d.size == 0 or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float((d <= value).mean() * 100))


def series(df, site, variable) -> pd.Series:
    s = df[(df.site == site) & (df.variable == variable)].set_index("t_local")["value"].sort_index()
    return s[~s.index.duplicated()]


def on_day(s: pd.Series, d: date) -> pd.Series:
    return s[s.index.date == d]


def in_hours(s: pd.Series, h0: float, h1: float) -> pd.Series:
    h = s.index.hour + s.index.minute / 60
    return s[(h >= h0) & (h < h1)]


def dhours(s: pd.Series) -> np.ndarray:
    return (s.index.hour + s.index.minute / 60).to_numpy(dtype=float)


def slope_resid(s: pd.Series):
    """Linear trend (deg/h) of an unwrapped direction series and the SD of the residuals."""
    if len(s) < 4:
        return float("nan"), float("nan"), None
    x, y = dhours(s), unwrap_deg(s.to_numpy())
    p = np.polyfit(x, y, 1)
    res = y - np.polyval(p, x)
    return float(p[0]), float(np.std(res)), res


def swing_period_min(res: np.ndarray, step_min: float) -> float | None:
    """Period of the swings: 2 x the first lag where the residual autocorrelation drops below zero."""
    if res is None or len(res) < 8 or np.std(res) == 0:
        return None
    x = res - res.mean()
    ac = np.correlate(x, x, "full")[len(x) - 1:] / (x.var() * len(x))
    neg = np.where(ac[1:] < 0)[0]
    return float(2 * (neg[0] + 1) * step_min) if neg.size else None


def onset_time(speed: pd.Series, direction: pd.Series, need: int = 4):
    j = pd.concat([speed.rename("s"), direction.rename("d")], axis=1).dropna()
    j = j[(j.index.hour >= 9) & (j.index.hour < 17)]
    ok = (j.s >= SEA_BREEZE_MIN_KN) & (j.d >= SEA_BREEZE_SECTOR[0]) & (j.d <= SEA_BREEZE_SECTOR[1])
    run = 0
    for i, flag in enumerate(ok.to_numpy()):
        run = run + 1 if flag else 0
        if run >= need:
            t = ok.index[i - need + 1]
            return t.hour + t.minute / 60
    return None


def hourly(s: pd.Series, how="mean", directional=False) -> pd.Series:
    g = s.groupby(s.index.floor("h"))
    return g.agg(circmean) if directional else g.agg(how)


def lonlat_to_xy(lat, lon, lat0, lon0):
    return (lon - lon0) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 110540


def xy_to_lonlat(x, y, lat0, lon0):
    return lat0 + y / 110540, lon0 + x / (111320 * math.cos(math.radians(lat0)))


def block(evidence, percentiles, sources, quality):
    return {"evidence": evidence, "venue_percentiles": percentiles, "data_sources": sources, "data_quality": quality}


# ============================================================ shared computations
class Ctx:
    """Everything the blocks share: data, race day, climatology days, course, rasters."""

    def __init__(self, race_day: date, area: str, window, cutoff_h: int, backtest: bool):
        df = pd.read_parquet(CONDITIONS)
        df["t_local"] = df["time_utc"].dt.tz_convert(TZ)
        self.df, self.D, self.area, self.window, self.cutoff_h, self.backtest = df, race_day, area, window, cutoff_h, backtest
        years = sorted(df.loc[df.source == "hrrr", "t_local"].dt.year.unique())
        self.years = [int(y) for y in years if not (backtest and y == race_day.year)]
        sp, dr, gu = (series(df, area, v) for v in ("wind_speed", "wind_dir_from", "wind_gust"))
        clim = lambda s: s[s.index.year.isin(self.years)]
        self.sp, self.dr, self.gu = clim(sp), clim(dr), clim(gu)            # climatology (near-real-time HRRR, 15 min)

        # Race-day wind: backtest -> HRRR forecast issued ~24 h before (what a coach really had);
        # hindsight (or no day-ahead data) -> near-real-time HRRR for the day.
        da = f"{area}_dayahead"
        use_da = backtest and not on_day(series(df, da, "wind_speed"), race_day).empty
        self.day_site = da if use_da else area
        self.inland_site = "inland_lakewood_dayahead" if use_da else "inland_lakewood"
        self.belmont_site = "belmont_course_dayahead" if use_da else "belmont_course"
        self.day_source = ("HRRR forecast issued ~24 h before the race day (Open-Meteo previous runs, hourly)" if use_da else
                           "HRRR near-real-time model output for the race day (15 min)" +
                           (" - day-ahead forecast not available for this date" if backtest else " - hindsight"))
        self.f_sp, self.f_dr, self.f_gu = (on_day(series(df, self.day_site, v), race_day)
                                           for v in ("wind_speed", "wind_dir_from", "wind_gust"))
        step = 60 if use_da else 15                                        # minutes between race-day samples
        self.step = step
        w0, w1 = window
        # per-climatology-day statistics (for percentiles), at the same time step as the race-day series
        if step == 60:
            hs, hd, hg = hourly(self.sp), hourly(self.dr, directional=True), hourly(self.gu)
        else:
            hs, hd, hg = self.sp, self.dr, self.gu
        self.days = sorted(set(self.sp.index.date))
        rows = []
        for d in self.days:
            s, dd, g = on_day(hs, d), on_day(hd, d), on_day(hg, d)
            v12, _, _ = slope_resid(in_hours(dd, VEER_H0, VEER_H1))
            _, sd, res = slope_resid(in_hours(dd, w0, w1))
            ws, wg = in_hours(s, w0, w1), in_hours(g, w0, w1)
            rows.append({"day": d, "veer_12_17": v12, "resid_sd": sd, "period": swing_period_min(res, step),
                         "onset": onset_time(s, dd, max(1, int(ONSET_MIN_H * 60 // step))), "win_speed": ws.mean(), "win_dir": circmean(in_hours(dd, w0, w1)),
                         "gust_excess": (wg - ws).mean(), "peak_speed": in_hours(s, 10, 19).max(),
                         "peak_time": (lambda x: x.idxmax().hour + x.idxmax().minute / 60 if len(x) else None)(in_hours(s, 10, 19))})
        self.daily = pd.DataFrame(rows)
        # race-day equivalents
        v12, _, _ = slope_resid(in_hours(self.f_dr, VEER_H0, VEER_H1))
        vw, sdw, resw = slope_resid(in_hours(self.f_dr, w0, w1))
        fs = in_hours(self.f_sp, w0, w1)
        self.f = {"veer_12_17": v12, "veer_window": vw, "resid_sd": sdw, "period": swing_period_min(resw, step),
                  "onset": onset_time(self.f_sp, self.f_dr, max(1, int(ONSET_MIN_H * 60 // step))), "win_speed": fs.mean(), "win_min": fs.min(), "win_max": fs.max(),
                  "win_dir": circmean(in_hours(self.f_dr, w0, w1)),
                  "gust_excess": (in_hours(self.f_gu, w0, w1) - fs).mean(),
                  "dir_start": circmean(in_hours(self.f_dr, w0, w0 + 1)), "dir_end": circmean(in_hours(self.f_dr, w1 - 1, w1))}
        self.course = self._course()
        self._rasters()

    # ---------------- course
    def _course(self):
        cf = course_file(self.D) if self.area == "port_la_course" else None
        if cf:
            # buoy / line coordinates only (location_agent/course/<date>.json); never boat routes
            cdat = json.loads(cf.read_text(encoding="utf-8"))
            r = cdat["races"][0]
            sl, m1 = r["start_line"], r.get("mark1") or r["windward_mark_1"]
            ends = [(sl["left_end"]["lat"], sl["left_end"]["lon"]), (sl["right_end"]["lat"], sl["right_end"]["lon"])]
            mark = (m1["lat"], m1["lon"])
            src = (f"course file {cf.name}, race {r['race']} (start line + windward mark 1): {cdat['source']}"
                   + ("" if cf.stem == self.D.isoformat() else f" - no course file for {self.D}, using the {cf.stem} layout"))
        else:
            c = AREA_CENTRES[self.area]
            ends = [(c[0] - 0.00135, c[1] + 0.0067), (c[0] + 0.00135, c[1] + 0.0067)]   # ~300 m N-S line, east end
            mark = (c[0], c[1] - 0.0067)
            src = "placeholder: E-W beat (~1.25 km) through the venues.yaml area centre"
        start = ((ends[0][0] + ends[1][0]) / 2, (ends[0][1] + ends[1][1]) / 2)
        mx, my = lonlat_to_xy(mark[0], mark[1], start[0], start[1])
        ex, ey = lonlat_to_xy(ends[1][0], ends[1][1], ends[0][0], ends[0][1])
        return {"source": src, "start_line_ends": [[round(a, 5), round(b, 5)] for a, b in ends],
                "start_line_centre": [round(start[0], 5), round(start[1], 5)],
                "start_line_length_m": round(math.hypot(ex, ey)), "start_line_bearing_deg": round(math.degrees(math.atan2(ex, ey)) % 180),
                "windward_mark": [round(mark[0], 5), round(mark[1], 5)],
                "rhumb_bearing_deg": round(math.degrees(math.atan2(mx, my)) % 360), "beat_length_m": round(math.hypot(mx, my))}

    # ---------------- rasters and lanes
    def _rasters(self):
        self.bsrc = rasterio.open(BATHY)
        self.bath = self.bsrc.read(1).astype("float64")
        self.tsrc = rasterio.open(TERRAIN)
        self.terr = self.tsrc.read(1).astype("float64")
        self.land = np.nan_to_num(self.bath, nan=1.0) >= S['land_definition']['bathymetry_land_m']
        lat_mid = (self.bsrc.bounds.top + self.bsrc.bounds.bottom) / 2
        self.px = (self.bsrc.res[1] * 110540, self.bsrc.res[0] * 111320 * math.cos(math.radians(lat_mid)))
        self.dist_land = ndimage.distance_transform_edt(~self.land, sampling=self.px)
        c = self.course
        s_lat, s_lon = c["start_line_centre"]
        mx, my = lonlat_to_xy(*c["windward_mark"], s_lat, s_lon)
        rb = math.radians(c["rhumb_bearing_deg"])
        right = (math.sin(rb + math.pi / 2), math.cos(rb + math.pi / 2))
        self.lanes = {}
        for name, sign in (("left", -1), ("right", 1), ("centre", 0)):
            self.lanes[name] = [xy_to_lonlat(f * mx + sign * LANE_OFFSET_M * right[0], f * my + sign * LANE_OFFSET_M * right[1],
                                             s_lat, s_lon) for f in np.linspace(S['lanes']['from_fraction'], S['lanes']['to_fraction'], S['lanes']['points'])]

    def sample(self, which, lat, lon):
        src, arr = (self.bsrc, self.bath) if which == "bath" else (self.tsrc, self.terr) if which == "terr" else (self.bsrc, self.dist_land)
        try:
            i, j = src.index(lon, lat)
        except Exception:
            return float("nan")
        return float(arr[i, j]) if 0 <= i < arr.shape[0] and 0 <= j < arr.shape[1] else float("nan")

    def upwind_scan(self, lat, lon, wdir):
        best, first_land = None, None
        for d in range(RAY_STEP_M, RAY_MAX_M, RAY_STEP_M):
            la, lo = xy_to_lonlat(d * math.sin(math.radians(wdir)), d * math.cos(math.radians(wdir)), lat, lon)
            h = self.sample("terr", la, lo)
            if math.isnan(h):
                break
            if h > S['land_definition']['terrain_land_m'] and first_land is None:
                first_land = d
            if h > S['land_definition']['terrain_obstacle_m'] and (best is None or h / d > best[0]):
                best = (h / d, h, d)
        return {"over_water_fetch_m": first_land if first_land else f">{RAY_MAX_M}",
                "max_obstacle_height_m": r(best[1], 0) if best else 0, "max_obstacle_distance_m": best[2] if best else None,
                "shelter_index_height_over_distance": r(best[0], 4) if best else 0.0}


# ============================================================ the 9 blocks
def b1_oscillating(c: Ctx):
    d = c.daily
    st = series(c.df, "angels_gate", "wind_dir_from")
    st = st[st.index.year.isin(c.years)]
    st_sd = [slope_resid(in_hours(on_day(st, day), *c.window))[1] for day in sorted(set(st.index.date))]
    return block(
        {"race_day": {"swing_sd_deg_around_trend": r(c.f["resid_sd"]), "swing_period_min": r(c.f["period"], 0)},
         "july_climatology": {"swing_sd_deg_median": r(d.resid_sd.median()), "swing_sd_deg_p25_p75": [r(d.resid_sd.quantile(.25)), r(d.resid_sd.quantile(.75))],
                              "swing_period_min_median": r(d.period.median(), 0)},
         "station_angels_gate_hourly_swing_sd_deg_median": r(np.nanmedian(st_sd)),
         "window_local": f"{c.window[0]:02d}:00-{c.window[1]:02d}:00"},
        {"race_day_swing_sd": pct_rank(c.f["resid_sd"], d.resid_sd)},
        ["HRRR 15-min direction at the course", "CO-OPS Angels Gate hourly direction (measured)"],
        "HRRR (3 km, 15 min) smooths short swings: SD and period describe slow swings only (periods >= ~30 min).")


def b2_persistent(c: Ctx):
    d = c.daily
    st = series(c.df, "angels_gate", "wind_dir_from")
    st = st[st.index.year.isin(c.years)]
    st_v = [slope_resid(in_hours(on_day(st, day), VEER_H0, VEER_H1))[0] for day in sorted(set(st.index.date))]
    st_v = [v for v in st_v if not math.isnan(v)]
    w0, w1 = c.window
    return block(
        {"race_day": {"veer_deg_per_h_12_17": r(c.f["veer_12_17"]), "veer_deg_per_h_race_window": r(c.f["veer_window"]),
                               "dir_deg_window_start": r(c.f["dir_start"], 0), "dir_deg_window_end": r(c.f["dir_end"], 0),
                               "total_turn_deg_over_window": r(angdiff(c.f["dir_end"], c.f["dir_start"]), 0)},
         "july_climatology_hrrr": {"veer_deg_per_h_12_17_median": r(d.veer_12_17.median()),
                                   "veer_p25_p75": [r(d.veer_12_17.quantile(.25)), r(d.veer_12_17.quantile(.75))],
                                   "pct_days_veering": r(100 * (d.veer_12_17 > 0).mean(), 0),
                                   "mean_dir_deg_by_hour": {f"{h:02d}": r(circmean(c.dr[c.dr.index.hour == h]), 0) for h in range(CLIM_H0, CLIM_H1 + 1)}},
         "july_climatology_angels_gate_measured": {"veer_deg_per_h_12_17_median": r(np.median(st_v)) if st_v else None,
                                                   "pct_days_veering": r(100 * np.mean(np.array(st_v) > 0), 0) if st_v else None,
                                                   "n_days": len(st_v)},
         "sign_convention": "positive = clockwise = veer = right shift"},
        {"race_day_veer_12_17": pct_rank(c.f["veer_12_17"], d.veer_12_17)},
        ["HRRR course (15 min)", "CO-OPS Angels Gate (hourly, measured)"],
        "Model and station agree on the sign of the trend; station direction itself is biased ~25-40 deg left.")


def b3_geographic(c: Ctx):
    w0, w1 = c.window
    course_h = hourly(in_hours(c.dr, w0, w1), directional=True)
    diffs = {}
    for site, label in (("angels_gate", "angels_gate_measured"), ("belmont_course", "belmont_inshore_model"),
                        ("buoy_46025", "offshore_buoy_46025_measured")):
        s = series(c.df, site, "wind_dir_from")
        s = in_hours(s[s.index.year.isin(c.years)], w0, w1)
        sh = hourly(s, directional=True)
        j = pd.concat([course_h.rename("a"), sh.rename("b")], axis=1).dropna()
        diffs[label] = {"median_deg": r(np.median(angdiff(j.a, j.b)), 0), "n_hours": int(len(j))}
    bel = in_hours(on_day(series(c.df, c.belmont_site, "wind_dir_from"), c.D), w0, w1)
    # shoreline geometry near the beat midpoint (from the bathymetry land mask)
    mid = c.lanes["centre"][4]
    i0, j0 = c.bsrc.index(mid[1], mid[0])
    rad = int(S['shoreline_radius_m'] / c.px[0])
    win = c.land[max(i0 - rad, 0):i0 + rad, max(j0 - rad, 0):j0 + rad]
    ii, jj = np.nonzero(win)
    shore = {}
    if ii.size:
        ys = -(ii + max(i0 - rad, 0) - i0) * c.px[0]
        xs = (jj + max(j0 - rad, 0) - j0) * c.px[1]
        k = int(np.argmin(np.hypot(xs, ys)))
        cov = np.cov(np.vstack([xs, ys]))
        ev, evec = np.linalg.eigh(cov)
        ax = evec[:, int(np.argmax(ev))]
        shore = {"nearest_land_bearing_deg": round(math.degrees(math.atan2(xs[k], ys[k])) % 360),
                 "nearest_land_distance_m": round(float(math.hypot(xs[k], ys[k]))),
                 "land_within_3km_main_axis_bearing_deg": round(math.degrees(math.atan2(ax[0], ax[1])) % 180)}
    dl = {n: r(np.nanmedian([c.sample("dist", la, lo) for la, lo in c.lanes[n]]), 0) for n in ("left", "right")}
    return block(
        {"dir_difference_course_minus_site_race_hours_july": diffs,
         "race_day_dir_difference_course_minus_belmont_deg": r(angdiff(c.f["win_dir"], circmean(bel)), 0),
         "shoreline_near_course": shore,
         "distance_to_land_by_side_m": dl,
         "sign_convention": "difference > 0 = wind at the course is veered (more from the right) relative to that site"},
        {},
        ["HRRR course + Belmont", "CO-OPS Angels Gate (measured)", "NDBC 46025 offshore (measured)", "NCEI bathymetry land mask"],
        "Differences mix model and measured sites; Angels Gate sits in the breakwater entrance (local channelling).")


def b4_pressure(c: Ctx):
    w0, w1 = c.window
    by_site = {}
    for site, label in (("port_la_course", "port_la_course_model"), ("belmont_course", "belmont_inshore_model"),
                        ("angels_gate", "angels_gate_breakwater_measured"), ("pier_400", "pier_400_inside_harbour_measured"),
                        ("buoy_46025", "offshore_buoy_46025_measured")):
        s = series(c.df, site, "wind_speed")
        s = in_hours(s[s.index.year.isin(c.years)], w0, w1)
        by_site[label] = r(s.median())
    d = c.daily
    hourly_fc = {f"{h:02d}": {"speed_kn": r(in_hours(c.f_sp, h, h + 1).mean()),
                              "anomaly_vs_july_median_kn": r(in_hours(c.f_sp, h, h + 1).mean() - c.sp[c.sp.index.hour == h].median())}
                 for h in range(CLIM_H0, CLIM_H1 + 1)}
    return block(
        {"race_day": {"race_window_speed_kn_mean": r(c.f["win_speed"]), "race_window_speed_kn_min_max": [r(c.f["win_min"]), r(c.f["win_max"])],
                               "gust_minus_mean_kn": r(c.f["gust_excess"]), "by_local_hour": hourly_fc},
         "july_median_speed_kn_race_window_by_site": by_site,
         "july_climatology_race_window_speed_kn": {"median": r(d.win_speed.median()), "p10_p90": [r(d.win_speed.quantile(.1)), r(d.win_speed.quantile(.9))]},
         "july_gust_minus_mean_kn_median": r(d.gust_excess.median())},
        {"race_day_window_speed": pct_rank(c.f["win_speed"], d.win_speed), "race_day_gustiness": pct_rank(c.f["gust_excess"], d.gust_excess)},
        ["HRRR course + Belmont", "CO-OPS Angels Gate, Pier 400 (measured)", "NDBC 46025 (measured)"],
        "HRRR (3 km) cannot resolve left-vs-right pressure within a 1.2 km beat; site comparisons are inside/outside the breakwater scale.")


def cloud_metrics(cloud: pd.Series, day: date):
    """(mean total cloud % in the morning hours, first local hour from 07:00 with cloud < cloud_clear_pct)."""
    s = on_day(cloud, day)
    m = in_hours(s, *S["morning_cloud_hours_local"]).mean()
    after = in_hours(s, 7, 19)
    clear = after[after < S["cloud_clear_pct"]]
    return m, (clear.index[0].hour + clear.index[0].minute / 60 if len(clear) else float("nan"))


def b5_cloud(c: Ctx) -> dict:
    """Morning cloud (marine layer) - total cloud cover, because the day-ahead forecast has no low-cloud values."""
    inland_now, course_now = series(c.df, "inland_lakewood", "cloud_cover"), series(c.df, c.area, "cloud_cover")
    if inland_now.empty:
        return {}
    inland_day, course_day = series(c.df, c.inland_site, "cloud_cover"), series(c.df, c.day_site, "cloud_cover")
    clim = inland_now[inland_now.index.year.isin(c.years)]
    rows = []
    for day in c.days:
        m, clr = cloud_metrics(clim, day)
        rows.append((m, clr))
    cl = pd.DataFrame(rows, columns=["morning", "clear"], index=c.days)
    dd = c.daily.set_index("day")
    j = cl.join(dd[["onset", "win_speed"]])

    def rel(x, y):
        ok = j[[x, y]].dropna()
        if len(ok) < 10 or ok[x].std() == 0:
            return None, None
        return r(np.corrcoef(ok[x], ok[y])[0, 1], 2), r(np.polyfit(ok[x], ok[y], 1)[0] * 10, 2)
    co_on, sl_on = rel("morning", "onset")
    co_ws, sl_ws = rel("morning", "win_speed")
    m_in, clr_in = cloud_metrics(inland_day, c.D)
    m_co, clr_co = cloud_metrics(course_day, c.D)
    h0, h1 = S["morning_cloud_hours_local"]
    return {
        "evidence": {
            "race_day": {"morning_cloud_pct_inland": r(m_in, 0), "morning_cloud_pct_course": r(m_co, 0),
                         "cloud_clears_local_inland": hhmm(clr_in), "cloud_clears_local_course": hhmm(clr_co)},
            "july_climatology_inland": {"morning_cloud_pct_median": r(cl.morning.median(), 0),
                                        "morning_cloud_pct_p25_p75": [r(cl.morning.quantile(.25), 0), r(cl.morning.quantile(.75), 0)],
                                        "cloud_clears_local_median": hhmm(cl.clear.median()),
                                        "cloud_clears_p25_p75": [hhmm(cl.clear.quantile(.25)), hhmm(cl.clear.quantile(.75))],
                                        "pct_days_cloud_never_clears_07_19": r(100 * cl.clear.isna().mean(), 0),
                                        "corr_morning_cloud_vs_onset_hour": co_on, "onset_hours_per_10pct_cloud": sl_on,
                                        "corr_morning_cloud_vs_race_window_speed": co_ws, "race_window_kn_per_10pct_cloud": sl_ws},
            "definition": f"total cloud cover %, mean {h0:02d}:00-{h1:02d}:00; 'clears' = first hour from 07:00 with cloud < "
                          f"{S['cloud_clear_pct']} %",
        },
        "venue_percentiles": {"race_day_morning_cloud_inland": pct_rank(m_in, cl.morning),
                              "race_day_cloud_clears_inland": pct_rank(clr_in, cl.clear)},
    }


def b5_sea_breeze(c: Ctx):
    d = c.daily
    inland = series(c.df, "inland_lakewood", "air_temp")
    sea = series(c.df, "buoy_46222", "water_temp")
    pairs = []
    for day in c.days:
        ti = inland[(inland.index.date == day) & (inland.index.hour == S['land_sea_dT_inland_hour'])]
        ts = sea[sea.index.date == day]
        ws = in_hours(on_day(c.sp, day), *c.window)
        if len(ti) and len(ts) and len(ws):
            pairs.append((ti.mean() - ts.mean(), ws.mean()))
    a = np.array(pairs)
    slope = np.polyfit(a[:, 0], a[:, 1], 1)[0] if len(a) > 5 else float("nan")
    sea_clim = sea[sea.index.year.isin(c.years)].median()
    inland_day = series(c.df, c.inland_site, "air_temp")
    ti_d = inland_day[(inland_day.index.date == c.D) & (inland_day.index.hour == S['land_sea_dT_inland_hour'])].mean()
    dT_day = ti_d - sea_clim
    st = series(c.df, "angels_gate", "wind_speed")
    morning = {}
    for h in range(8, c.cutoff_h + 1):
        s = st[(st.index.date == c.D) & (st.index.hour == h)]
        if len(s):
            morning[f"{h:02d}"] = {"speed_kn": r(s.mean()),
                                   "vs_station_july_median_kn": r(s.mean() - st[(st.index.year.isin(c.years)) & (st.index.hour == h)].median())}
    on = d.onset.dropna()
    cloud = b5_cloud(c)
    out = block(
        {"race_day": {"onset_local": hhmm(c.f["onset"]),
                      "peak_kn": r(in_hours(c.f_sp, 10, 19).max()),
                      "inland_temp_14_degC": r(ti_d), "sea_temp_used_degC": r(sea_clim),
                      "land_sea_dT_degC": r(dT_day),
                      "measured_morning_angels_gate": morning},
         "july_climatology": {"onset_local_median": hhmm(on.median()), "onset_p25_p75": [hhmm(on.quantile(.25)), hhmm(on.quantile(.75))],
                              "pct_days_without_sea_breeze": r(100 * (1 - len(on) / len(d)), 0),
                              "peak_speed_kn_median": r(d.peak_speed.median()), "peak_time_local_median": hhmm(d.peak_time.median()),
                              "land_sea_dT_degC_median": r(np.median(a[:, 0])) if len(a) else None,
                              "corr_dT_vs_race_window_speed": r(np.corrcoef(a[:, 0], a[:, 1])[0, 1], 2) if len(a) > 5 else None,
                              "race_window_kn_per_degC_dT": r(slope, 2)},
         "onset_definition": f">= {SEA_BREEZE_MIN_KN:.0f} kn from {SEA_BREEZE_SECTOR[0]}-{SEA_BREEZE_SECTOR[1]} deg for 1 h"},
        {"race_day_dT": pct_rank(dT_day, a[:, 0] if len(a) else []), "race_day_onset_time": pct_rank(c.f["onset"], on),
         "race_day_peak_speed": pct_rank(in_hours(c.f_sp, 10, 19).max(), d.peak_speed)},
        ["HRRR inland Lakewood temperature + course wind", "NDBC 46222 sea temperature", "CO-OPS Angels Gate morning wind (measured, to cutoff)"],
        "Race-day sea temperature not in repo: July buoy median used. Morning station data cut at "
        f"{c.cutoff_h:02d}:00 (backtest).")
    if cloud:
        out["evidence"]["morning_cloud"] = cloud["evidence"]
        out["venue_percentiles"].update(cloud["venue_percentiles"])
        out["data_sources"].append("HRRR total cloud cover (race day: same source as the race-day wind)")
    return out


def b6_current_tide(c: Ctx):
    w0, w1 = c.window
    tide = series(c.df, "tide_los_angeles", "tide_height")
    events = []
    for var, kind in (("tide_high", "high"), ("tide_low", "low")):
        s = on_day(series(c.df, "tide_los_angeles", var), c.D)
        events += [(t, kind, v) for t, v in s.items()]
    events.sort()
    th = on_day(tide, c.D)
    at = lambda h: th[th.index.hour == h].mean() if len(th[th.index.hour == h]) else float("nan")
    turns_in_window = [f"{k} {t:%H:%M}" for t, k, _ in events if w0 <= t.hour + t.minute / 60 < w1]
    cur_site = f"current_{c.area}"
    cs, cd = series(c.df, cur_site, "current_speed"), series(c.df, cur_site, "current_dir_to")
    cs_d, cd_d = in_hours(on_day(cs, c.D), w0, w1), in_hours(on_day(cd, c.D), w0, w1)
    cs_c = cs[cs.index.year.isin(c.years)]
    clim_days = [in_hours(on_day(cs_c, day), w0, w1).mean() for day in sorted(set(cs_c.index.date))]
    depth = {n: r(np.nanmedian([c.sample("bath", la, lo) for la, lo in c.lanes[n]])) for n in ("left", "right")}
    lat, lon = (c.df.loc[c.df.site == cur_site, ["lat", "lon"]].iloc[0].tolist() if (c.df.site == cur_site).any() else (None, None))
    return block(
        {"tide_race_day_local": [f"{k} {t:%H:%M} {v:.2f} m" for t, k, v in events],
         "tide_height_m_at_window_start_end": [r(at(w0), 2), r(at(w1), 2)],
         "tide_turns_inside_race_window": turns_in_window,
         "tide_range_m_race_day": r(max(v for *_, v in events) - min(v for *_, v in events), 2) if events else None,
         "current_model_race_window": {"speed_kn_mean": r(cs_d.mean(), 2), "speed_kn_max": r(cs_d.max(), 2),
                                       "flowing_towards_deg": r(circmean(cd_d), 0), "model_cell": [lat, lon]},
         "current_july_race_window_speed_kn_median": r(np.nanmedian(clim_days), 2) if clim_days else None,
         "depth_m_navd88_median_by_side": depth},
        {"race_day_current_speed": pct_rank(cs_d.mean(), clim_days)},
        ["CO-OPS 9410660 Los Angeles tide predictions (MLLW)", "Open-Meteo marine surface current (model)", "NCEI bathymetry"],
        "Current is a coarse model (several km), nearest cell ~2.5 km from the course: background drift only, "
        "cannot resolve left vs right. Tide heights are exact predictions.")


def b7_terrain(c: Ctx):
    wd = c.f["win_dir"] if not math.isnan(c.f["win_dir"]) else circmean(in_hours(c.dr, *c.window))
    mids = {n: c.lanes[n][4] for n in ("left", "right")}
    per_side = {n: c.upwind_scan(m[0], m[1], wd) for n, m in mids.items()}
    sens = {}
    for w in range(S['shelter_table_dirs_deg']['from'], S['shelter_table_dirs_deg']['to'] + 1, S['shelter_table_dirs_deg']['step']):
        row = {}
        for n, m in mids.items():
            s = c.upwind_scan(m[0], m[1], w)
            row[n] = s["shelter_index_height_over_distance"]
        sens[str(w)] = row
    tr, tc = np.unravel_index(np.nanargmax(c.terr), c.terr.shape)
    hx, hy = c.tsrc.xy(tr, tc)
    s_lat, s_lon = c.course["start_line_centre"]
    px_, py_ = lonlat_to_xy(hy, hx, s_lat, s_lon)
    return block(
        {"wind_dir_used_deg": r(wd, 0), "upwind_scan_by_side_for_race_day_wind": per_side,
         "shelter_index_by_wind_dir_deg": sens,
         "highest_terrain": {"name": "Palos Verdes Hills", "height_m": r(np.nanmax(c.terr), 0),
                             "bearing_from_start_deg": round(math.degrees(math.atan2(px_, py_)) % 360), "distance_km": r(math.hypot(px_, py_) / 1000)},
         "shelter_index_definition": "max over the upwind path of terrain height / distance (scan 12 km, 30 m steps)"},
        {},
        ["Copernicus GLO-30 terrain (30 m, includes buildings)", "NCEI bathymetry"],
        "Terrain raster extends ~10 km west of the course; obstacles further away (e.g. Santa Catalina, ~35 km) are not scanned.")


def b8_start_line(c: Ctx):
    co = c.course
    (la1, lo1), (la2, lo2) = co["start_line_ends"]
    names = ["south_end", "north_end"] if la1 < la2 else ["north_end", "south_end"]
    # the line perpendicular that points up the course (towards the windward mark)
    perp = min(((co["start_line_bearing_deg"] + 90) % 360, (co["start_line_bearing_deg"] + 270) % 360),
               key=lambda b: abs(angdiff(b, co["rhumb_bearing_deg"])))

    def bias(wdir):
        u = (math.sin(math.radians(wdir)), math.cos(math.radians(wdir)))      # unit vector pointing upwind
        x2, y2 = lonlat_to_xy(la2, lo2, la1, lo1)
        adv = x2 * u[0] + y2 * u[1]                                             # >0: end 2 is further upwind
        return {"more_upwind_end": names[1] if adv > 0 else names[0], "upwind_advantage_m": r(abs(adv), 0),
                "wind_minus_line_perpendicular_deg": r(angdiff(wdir, perp), 0)}
    w0 = c.window[0]
    SL = S["start_line_sensitivity_deg"]
    start_dir = c.f["dir_start"]
    return block(
        {"start_line_bearing_deg": co["start_line_bearing_deg"], "start_line_length_m": co["start_line_length_m"],
         "line_perpendicular_up_course_deg": perp,
         "race_day_dir_deg_first_hour": r(start_dir, 0), "at_race_day_wind": bias(start_dir),
         f"if_wind_{SL}deg_left": bias(start_dir - SL), f"if_wind_{SL}deg_right": bias(start_dir + SL),
         "race_day_veer_deg_per_h_race_window": r(c.f["veer_window"]),
         "left_right_of_ends_looking_upwind": "south end = left, north end = right (course heads west)",
         "note": "which end is the committee boat vs the pin is not known from the data"},
        {},
        ["Start line from the course file (location_agent/course/)", "HRRR race-day wind direction"],
        "Line position and bearing come from one 2026 race; the real LA28 line will be set on the day.")


def b9_laylines(c: Ctx):
    L = c.course["beat_length_m"]
    t_beat_h = L / (ILCA_UPWIND_VMG_KN * 1852)
    veer = c.f["veer_window"]
    cur_site = f"current_{c.area}"
    cs = in_hours(on_day(series(c.df, cur_site, "current_speed"), c.D), *c.window).mean()
    cd = circmean(in_hours(on_day(series(c.df, cur_site, "current_dir_to"), c.D), *c.window))
    set_m = cs * 1852 * t_beat_h if not math.isnan(cs) else float("nan")
    rb = math.radians(c.course["rhumb_bearing_deg"])
    along = set_m * math.cos(math.radians(cd) - rb) if not math.isnan(set_m) else float("nan")
    across = set_m * math.sin(math.radians(cd) - rb) if not math.isnan(set_m) else float("nan")
    return block(
        {"beat_length_m": L, "rhumb_bearing_deg": c.course["rhumb_bearing_deg"],
         "class_priors": {"class": S["boat_class_priors"]["class"], "tack_angle_deg": ILCA_TACK_ANGLE_DEG, "upwind_vmg_kn": ILCA_UPWIND_VMG_KN},
         "estimated_beat_time_min": r(t_beat_h * 60), "expected_wind_turn_over_beat_deg": r(veer * t_beat_h),
         "current_set_over_beat_m": {"total": r(set_m, 0), "along_course_towards_mark": r(along, 0),
                                     "across_course_towards_right": r(across, 0)},
         "layline_angle_to_wind_deg": ILCA_TACK_ANGLE_DEG / 2},
        {},
        ["Course geometry", "HRRR race-day veer", "Open-Meteo current (model)", "ILCA class priors"],
        "Class priors are approximate; current set is from a coarse model.")


# ============================================================ pack
def build_pack(race_day: date, area: str, window=None, cutoff_h=None, backtest=True) -> dict:
    window = tuple(window or S["race_window_local"])
    cutoff_h = S["morning_cutoff_hour"] if cutoff_h is None else cutoff_h
    c = Ctx(race_day, area, window, cutoff_h, backtest)
    pack = {
        "pack_version": 2,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "context": {
            "venue": f"LA28 sailing - {AREA_NAMES[area]}", "race_day": race_day.isoformat(),
            "race_window_local": f"{window[0]:02d}:00-{window[1]:02d}:00", "boat_class": "ILCA 7",
            "mode": "backtest: only information available on the race-day morning" if backtest else "hindsight: all data",
            "fingerprint": fingerprint(race_day, area, window, cutoff_h, backtest),
            "climatology_years": c.years,
            "race_day_wind_source": c.day_source,
            "settings": {**S, "race_window_local": list(window), "morning_cutoff_hour": cutoff_h},
            "conventions": "speeds kn; wind/wave directions = degrees FROM; current direction = degrees TOWARDS; local time PDT; "
                           "left/right = as seen by a sailor looking toward the windward mark; depth m (negative = below NAVD88); "
                           "venue_percentiles = % of July climatology days with a value <= the race-day value",
            "course": c.course,
        },
        "building_blocks": {
            "1_oscillating_shifts": b1_oscillating(c),
            "2_persistent_shift": b2_persistent(c),
            "3_geographic_shift_wind_bend": b3_geographic(c),
            "4_pressure": b4_pressure(c),
            "5_sea_breeze": b5_sea_breeze(c),
            "6_current_tide": b6_current_tide(c),
            "7_terrain_effects": b7_terrain(c),
            "8_start_line_bias": b8_start_line(c),
            "9_laylines": b9_laylines(c),
        },
        "coach_questions_to_blocks": {
            "Q1 which side pays and why": ["2", "3", "4", "6", "7"],
            "Q2 oscillating or persistent, and on what cycle": ["1", "2", "5"],
            "Q3 which end of the start line": ["8"],
            "Q4 what changes if the forecast is wrong": ["5", "4", "2"],
        },
        "prior_knowledge": [txt for d, txt in PRIOR_KNOWLEDGE if not backtest or d < race_day.isoformat()],
        "data_caveats": [
            "Race-day wind: see context.race_day_wind_source (backtest uses the forecast issued ~24 h ahead; climatology uses near-real-time HRRR).",
            "Climatology: July of the listed years only (wind 6 years max; currents from 2022).",
            "Course: start line and windward mark positions from the course file (see context.course.source); "
            "positions are uncertain by tens of metres.",
        ],
    }
    if not backtest:   # learned from the race-day GPS tracks -> hindsight only
        pack["data_caveats"].insert(1, "HRRR direction matched the GPS-derived course wind on 19 Jul 2026; "
                                       "Angels Gate station direction reads 25-40 deg left.")
    if not backtest and (GPS_RESULTS / "summary.json").exists():
        s = json.loads((GPS_RESULTS / "summary.json").read_text())
        pack["gps_lessons_same_day"] = {"wind_from_gps": s["wind_from_gps"], "side_by_beat": s["upwind"]["side_by_beat"],
                                        "upwind_speed_kn": s["upwind"]["speed_kn_median"], "upwind_vmg_kn": s["upwind"]["vmg_kn_median"]}
    c.bsrc.close(); c.tsrc.close()
    return pack


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="2026-07-19")
    p.add_argument("--area", default="port_la_course", choices=list(AREA_CENTRES))
    p.add_argument("--window", default="-".join(str(x) for x in S["race_window_local"]), help="race window, local hours, e.g. 13-17 (default: settings.yaml)")
    p.add_argument("--cutoff", type=int, default=S["morning_cutoff_hour"], help="last local hour of measured race-day data (backtest; default: settings.yaml)")
    p.add_argument("--no-backtest", action="store_true", help="use all data including the race day (hindsight)")
    p.add_argument("--all", action="store_true", help="prepare the demo packs: both areas, backtest + hindsight, for --date")
    p.add_argument("--quiet", action="store_true", help="do not print the pack")
    a = p.parse_args()
    w = tuple(int(x) for x in a.window.split("-"))
    jobs = ([(ar, bt) for ar in AREA_CENTRES for bt in (True, False)] if a.all else [(a.area, not a.no_backtest)])
    for area, bt in jobs:
        # the features command refreshes the stored pack, but only if its inputs changed
        pack, f, status = load_or_build(date.fromisoformat(a.date), area, w, a.cutoff, backtest=bt, rebuild=True)
        compact = json.dumps(pack, separators=(",", ":"), ensure_ascii=False)
        if not (a.all or a.quiet):
            print(json.dumps(pack, indent=1, ensure_ascii=False))
        print(f"{status}: {f.relative_to(ROOT)}  ({len(compact) / 1000:.1f} KB, ~{len(compact) // 4} tokens, "
              f"fingerprint {pack['context']['fingerprint']})")


if __name__ == "__main__":
    main()
