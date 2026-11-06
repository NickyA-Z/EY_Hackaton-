"""Previous strategy: data for a 3D replay of the 19 July 2026 San Pedro OCR ILCA 7 races.

Every function here is plain pandas/numpy (no Streamlit) so it can be tested on its own:

  load_fleet_tracks()   44 SailSync GPS tracks, with GPS outliers removed
  build_race()          per race: every boat's track resampled to a fixed step, on the race clock
  segments_frame()      the same, as one row per line segment (what the 3D map draws)
  race_marks()          start and first mark (median boat position at the rounding)
  conditions_at()       wind (Open-Meteo + NOAA piers), tide and waves at one instant
  strategy_documents()  which (synthetic) team-strategy documents those conditions trigger

The third dimension of the map is TIME, so the vertical axis is seconds since the start gun.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from backend import paths, race_analysis, strategy
from backend.race_model import model as race_model
from backend.venue_time import VENUE_TZ

RAW = paths.CONDITIONS_RAW_DIR
BATHYMETRY = paths.GEO_JSON_DIR / "bathymetry.json"
CORPUS = paths.STRATEGY_CORPUS_DIR

SESSION = "2796"
STEP_S = 5            # resampling step of every track, seconds
GAP_S = 20            # a grid point further than this from any GPS fix is treated as missing
JUMP_MS = 20.0        # a fix that implies > 20 m/s (39 kn) from the previous one is a GPS glitch
KN = 1.94384          # m/s -> knots
MAX_SPEED_KN = 14.0   # plausible ceiling for an ILCA 7; anything above is clipped for colouring
CAP_FACTOR = 1.5      # a boat's leg is cut at this multiple of the race's median leg time

# Venue box. One SailSync track contains fixes at lat -85, lng -37 (Antarctica); without this
# box the scene would be scaled to the planet.
LAT_RANGE = (33.55, 33.85)
LNG_RANGE = (-118.45, -118.05)

# Weather sources, all 8-11 km from the course (see distance_km() at run time).
OPEN_METEO_POINT = "palos_verdes"   # the only July Open-Meteo cell west of the course
NOAA_WIND_STATIONS = {
    "9410670": ("Pier F", 33.7463, -118.2156),
    "9410665": ("Pier J", 33.7330, -118.1857),
    "9410692": ("Pier S", 33.7683, -118.2257),
}
NOAA_DEFAULT_STATION = "9410670"   # nearest of the three to the course
NDBC_STATION = ("46222", "San Pedro buoy", 33.614, -118.314)
TIDE_STATION = ("9410660", "Los Angeles", 33.7200, -118.2720)


# ---------- geometry ----------

def to_metres(lat, lng, lat0, lng0):
    """Local east/north metres of lat/lng relative to (lat0, lng0). Works on arrays."""
    return ((np.asarray(lng) - lng0) * 111_320 * math.cos(math.radians(lat0)),
            (np.asarray(lat) - lat0) * 110_540)


def to_lnglat(x, y, lat0, lng0):
    """Inverse of to_metres: east/north metres -> (lng, lat)."""
    return (lng0 + np.asarray(x) / (111_320 * math.cos(math.radians(lat0))),
            lat0 + np.asarray(y) / 110_540)


def distance_km(lat1, lng1, lat2, lng2):
    x, y = to_metres(lat2, lng2, lat1, lng1)
    return float(math.hypot(x, y) / 1000)


def bearing_deg(x, y):
    """Compass bearing of an east/north vector."""
    return math.degrees(math.atan2(x, y)) % 360


# ---------- tracks and races ----------

def _drop_glitches(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove fixes that jump further than JUMP_MS from the last kept fix."""
    if len(frame) < 3:
        return frame
    lat, lng, t = frame["lat"].to_numpy(), frame["lng"].to_numpy(), frame["time_epoch"].to_numpy()
    keep = [0]
    for i in range(1, len(frame)):
        j = keep[-1]
        dx, dy = to_metres(lat[i], lng[i], lat[j], lng[j])
        dt = max(t[i] - t[j], 0.1)
        if math.hypot(float(dx), float(dy)) / dt <= JUMP_MS:
            keep.append(i)
    return frame.iloc[keep]


def load_fleet_tracks(results_dir: Path | None = None) -> dict[str, dict]:
    """{boat_id: {"name", "winner", "df"}} from the SailSync CSVs of session 2796."""
    results_dir = Path(results_dir or race_analysis.RESULTS)
    tracks: dict[str, dict] = {}
    for path in sorted(results_dir.rglob(f"{SESSION}_*.csv")):
        parts = path.stem.split("_")
        if len(parts) < 4:  # <session>_<boat_id>_<country>_<sail>; the sailor's name is optional
            continue
        boat_id = parts[1]
        frame = pd.read_csv(path).dropna(subset=["time_epoch", "lat", "lng"])
        frame = frame[frame["lat"].between(*LAT_RANGE) & frame["lng"].between(*LNG_RANGE)]
        frame = frame.drop_duplicates("time_epoch").sort_values("time_epoch").reset_index(drop=True)
        frame = _drop_glitches(frame).reset_index(drop=True)
        if frame.empty:
            continue
        tracks[boat_id] = {
            "name": f"{' '.join(parts[2:-2])} ({parts[-2]} {parts[-1]})" if len(parts) > 4
                    else f"{parts[-2]} {parts[-1]}",
            "winner": path.parent.name == "winners",
            "df": frame,
        }
    return tracks


def race_ids(legs_df: pd.DataFrame) -> list[str]:
    return sorted(legs_df["race"].unique())


def local_clock(epoch: float) -> str:
    """'14:15 PDT' for a UTC epoch."""
    stamp = pd.Timestamp(epoch, unit="s", tz="UTC").tz_convert(VENUE_TZ)
    return stamp.strftime("%H:%M ") + stamp.tzname()


def race_label(legs_df: pd.DataFrame, race_id: str) -> str:
    start = legs_df.loc[legs_df["race"] == race_id, "t_start"].min()
    number = race_ids(legs_df).index(race_id) + 1
    return f"Race {number} · {local_clock(start)}"


def build_race(race_id: str, legs_df: pd.DataFrame, tracks: dict[str, dict], step: int = STEP_S) -> dict:
    """Every tracked boat on the leg-1 window of one race, resampled every `step` seconds.

    Time is the race clock: seconds since the first boat's start. Grid points that lie more
    than GAP_S from any real GPS fix are marked invalid, so holes in a track stay holes.
    """
    race = legs_df[legs_df["race"] == race_id]
    if race.empty:
        raise KeyError(f"unknown race {race_id!r}")
    t0 = float(race["t_start"].min())
    # One straggler (race 2: 1,786 s against a 440 s median) would stretch the vertical axis 4x.
    # Every boat is cut at CAP_FACTOR x the median leg time; the cut is reported, not hidden.
    cap_s = CAP_FACTOR * float((race["t_end"] - race["t_start"]).median())
    raw, skipped, truncated = [], 0, []
    for row in race.itertuples():
        track = tracks.get(str(row.boat_id))
        if track is None:
            skipped += 1
            continue
        times = track["df"]["time_epoch"].to_numpy()
        if row.t_end - row.t_start > cap_s:
            truncated.append(str(row.boat_id))
        grid = np.arange(row.t_start, min(row.t_end, row.t_start + cap_s), step, dtype=float)
        if len(grid) < 2 or len(times) < 2:
            skipped += 1
            continue
        nearest = np.minimum(
            np.abs(times[np.clip(np.searchsorted(times, grid), 0, len(times) - 1)] - grid),
            np.abs(times[np.clip(np.searchsorted(times, grid) - 1, 0, len(times) - 1)] - grid),
        )
        valid = nearest <= GAP_S
        if valid.sum() < 3:
            skipped += 1
            continue
        raw.append((row, track, grid, valid,
                    np.interp(grid, times, track["df"]["lat"].to_numpy()),
                    np.interp(grid, times, track["df"]["lng"].to_numpy())))
    if not raw:
        raise ValueError(f"no GPS track covers race {race_id}")

    # local frame: origin = median first valid position of the fleet
    first = np.array([[lat[valid][0], lng[valid][0]] for _, _, _, valid, lat, lng in raw])
    lat0, lng0 = float(np.median(first[:, 0])), float(np.median(first[:, 1]))

    boats = []
    for row, track, grid, valid, lat, lng in raw:
        x, y = to_metres(lat, lng, lat0, lng0)
        window = max(1, int(round(15 / step)))  # speed over +/- 15 s
        speed = np.full(len(grid), np.nan)
        for i in range(len(grid)):
            a, b = max(0, i - window), min(len(grid) - 1, i + window)
            if valid[a] and valid[b] and b > a:
                speed[i] = math.hypot(x[b] - x[a], y[b] - y[a]) / (grid[b] - grid[a]) * KN
        boats.append({
            "boat_id": str(row.boat_id), "name": track["name"], "winner": track["winner"],
            "position": None if pd.isna(row.position) else int(row.position),
            "elapsed_s": float(row.t_end - row.t_start),
            "t": grid - t0, "lat": lat, "lng": lng, "x": x, "y": y,
            "speed_kn": np.clip(speed, 0, MAX_SPEED_KN), "valid": valid,
        })
    boats.sort(key=lambda b: (b["position"] is None, b["position"] or 0))
    return {
        "race_id": race_id, "t0": t0, "origin": (lat0, lng0), "boats": boats,
        "duration_s": float(max(b["t"][-1] for b in boats)),
        "tracked": len(boats), "in_race": len(race), "skipped": skipped,
        "truncated": truncated, "cap_s": cap_s,
    }


def race_marks(race_id: str, legs_df: pd.DataFrame, tracks: dict[str, dict]) -> pd.DataFrame:
    """Start (mark 0) and mark 1 = median position of the boats at the gun / at the rounding."""
    by_boat = {SESSION: {boat_id: t["df"] for boat_id, t in tracks.items()}}
    return race_model.mark_positions(legs_df[legs_df["race"] == race_id], by_boat)


def race_approaches(race_id: str, legs_df: pd.DataFrame, tracks: dict[str, dict],
                    marks: pd.DataFrame) -> pd.DataFrame:
    """Per boat: Left/Right of the straight start-mark line and Aggressive/Conservative."""
    by_boat = {SESSION: {boat_id: t["df"] for boat_id, t in tracks.items()}}
    legs_race = legs_df[legs_df["race"] == race_id]
    if marks.empty:
        return pd.DataFrame(columns=["boat_id", "side", "style", "offset"])
    return race_model.approaches(legs_race, by_boat, marks)[["boat_id", "side", "style", "offset"]]


def segments_frame(race: dict, approaches: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per line segment between consecutive valid grid points of a boat.

    Columns: boat_id, name, position, winner, side, style, t0, t1 (race clock s),
    lng0/lat0/lng1/lat1, speed_kn. Segments across a gap are not created.
    """
    side = style = {}
    if approaches is not None and not approaches.empty:
        side = dict(zip(approaches["boat_id"].astype(str), approaches["side"]))
        style = dict(zip(approaches["boat_id"].astype(str), approaches["style"]))
    rows = []
    for boat in race["boats"]:
        ok = boat["valid"][:-1] & boat["valid"][1:]
        for i in np.flatnonzero(ok):
            rows.append((
                boat["boat_id"], boat["name"], boat["position"], boat["winner"],
                side.get(boat["boat_id"], "n/a"), style.get(boat["boat_id"], "n/a"),
                boat["t"][i], boat["t"][i + 1],
                boat["lng"][i], boat["lat"][i], boat["lng"][i + 1], boat["lat"][i + 1],
                float(np.nanmean(boat["speed_kn"][i:i + 2])) if not np.isnan(boat["speed_kn"][i:i + 2]).all() else 0.0,
            ))
    return pd.DataFrame(rows, columns=[
        "boat_id", "name", "position", "winner", "side", "style", "t0", "t1",
        "lng0", "lat0", "lng1", "lat1", "speed_kn"])


def positions_at(race: dict, t: float) -> pd.DataFrame:
    """Each boat's position at race-clock t (clamped to its own valid span)."""
    rows = []
    for boat in race["boats"]:
        good = np.flatnonzero(boat["valid"])
        if len(good) == 0:
            continue
        tt = float(np.clip(t, boat["t"][good[0]], boat["t"][good[-1]]))
        rows.append({
            "boat_id": boat["boat_id"], "name": boat["name"], "position": boat["position"],
            "lng": float(np.interp(tt, boat["t"][good], boat["lng"][good])),
            "lat": float(np.interp(tt, boat["t"][good], boat["lat"][good])),
            "speed_kn": float(np.interp(tt, boat["t"][good], np.nan_to_num(boat["speed_kn"][good]))),
            "t": tt, "finished": bool(t >= boat["t"][good[-1]]),
        })
    return pd.DataFrame(rows)


# ---------- weather ----------

def _epoch_from_local(times: pd.Series) -> np.ndarray:
    """Naive LA-local timestamps -> UTC epoch seconds."""
    stamped = pd.to_datetime(times).dt.tz_localize(VENUE_TZ, ambiguous="NaT", nonexistent="NaT")
    return (stamped - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy()


@lru_cache(maxsize=4)
def _open_meteo(point: str) -> tuple[pd.DataFrame, float, float]:
    """(frame with epoch/speed_kn/gust_kn/dir/cloud/temp, cell lat, cell lng) for June+July 2026."""
    frame = strategy.load_wind([strategy.LIVE_YEAR], point)
    frame = frame.assign(epoch=_epoch_from_local(frame["time"])).dropna(subset=["epoch"])
    frame = frame.rename(columns={"speed": "speed_kn", "gust": "gust_kn"})
    sample = next(iter(sorted((RAW / "open_meteo").glob(f"{point}_{strategy.LIVE_YEAR}07.json"))))
    meta = json.loads(sample.read_text())
    return frame.sort_values("epoch").reset_index(drop=True), meta["latitude"], meta["longitude"]


@lru_cache(maxsize=8)
def _noaa_wind(station: str) -> pd.DataFrame:
    """NOAA CO-OPS hourly wind (GMT, m/s) for 2026 as epoch/speed_kn/gust_kn/dir."""
    frames = []
    for path in sorted((RAW / "noaa_coops").glob(f"{station}_wind_{strategy.LIVE_YEAR}[01][0-9].csv")):
        frame = pd.read_csv(path, skipinitialspace=True)
        frame.columns = [column.strip() for column in frame.columns]
        frames.append(pd.DataFrame({
            "epoch": (pd.to_datetime(frame["Date Time"]) - pd.Timestamp("1970-01-01")).dt.total_seconds(),
            "speed_kn": pd.to_numeric(frame["Speed"], errors="coerce") * KN,
            "gust_kn": pd.to_numeric(frame["Gust"], errors="coerce") * KN,
            "dir": pd.to_numeric(frame["Direction"], errors="coerce"),
        }))
    if not frames:
        return pd.DataFrame(columns=["epoch", "speed_kn", "gust_kn", "dir"])
    return pd.concat(frames).dropna(subset=["speed_kn", "dir"]).sort_values("epoch").reset_index(drop=True)


@lru_cache(maxsize=2)
def _ndbc_waves(station: str) -> pd.DataFrame:
    """NDBC standard meteorological file(s) for 2026: epoch (UTC), wave height m, period s."""
    frames = []
    for path in sorted((RAW / "ndbc").glob(f"{station}_{strategy.LIVE_YEAR}[01][0-9].txt.gz")):
        with gzip.open(path, "rt") as handle:
            header = handle.readline().lstrip("#").split()
        frame = pd.read_csv(path, sep=r"\s+", comment="#", header=None, names=header, compression="gzip")
        stamp = pd.to_datetime({"year": frame["YY"], "month": frame["MM"], "day": frame["DD"],
                                "hour": frame["hh"], "minute": frame["mm"]})
        wave = frame["WVHT"].where(frame["WVHT"] < 90)
        period = frame["DPD"].where(frame["DPD"] < 90)
        frames.append(pd.DataFrame({
            "epoch": (stamp - pd.Timestamp("1970-01-01")).dt.total_seconds(),
            "wave_m": wave, "period_s": period}))
    if not frames:
        return pd.DataFrame(columns=["epoch", "wave_m", "period_s"])
    return pd.concat(frames).dropna(subset=["wave_m"]).sort_values("epoch").reset_index(drop=True)


def _interp(frame: pd.DataFrame, column: str, epoch: float, max_gap_s: float = 7200):
    """Linear interpolation at `epoch`; None when the surrounding samples are too far apart."""
    t = frame["epoch"].to_numpy()
    if len(t) < 2 or epoch < t[0] or epoch > t[-1]:
        return None
    i = int(np.searchsorted(t, epoch))
    lo, hi = max(i - 1, 0), min(i, len(t) - 1)
    if t[hi] - t[lo] > max_gap_s:
        return None
    value = np.interp(epoch, t, frame[column].to_numpy(dtype=float))
    return None if np.isnan(value) else float(value)


def _interp_dir(frame: pd.DataFrame, epoch: float, max_gap_s: float = 7200):
    """Circular interpolation of a 'from' direction (deg true)."""
    t = frame["epoch"].to_numpy()
    if len(t) < 2 or epoch < t[0] or epoch > t[-1]:
        return None
    i = int(np.searchsorted(t, epoch))
    lo, hi = max(i - 1, 0), min(i, len(t) - 1)
    if t[hi] - t[lo] > max_gap_s:
        return None
    rad = np.radians(frame["dir"].to_numpy(dtype=float))
    east = np.interp(epoch, t, np.sin(rad))
    north = np.interp(epoch, t, np.cos(rad))
    return float(np.degrees(np.arctan2(east, north)) % 360)


def wind_at(frame: pd.DataFrame, epoch: float) -> dict | None:
    speed = _interp(frame, "speed_kn", epoch)
    direction = _interp_dir(frame, epoch)
    if speed is None or direction is None:
        return None
    out = {"speed_kn": speed, "dir": direction, "gust_kn": _interp(frame, "gust_kn", epoch),
           "rise_2h_kn": None}
    earlier = _interp(frame, "speed_kn", epoch - 7200)
    if earlier is not None:
        out["rise_2h_kn"] = speed - earlier
    if "cloud" in frame:
        out["cloud_pct"] = _interp(frame, "cloud", epoch)
    return out


def winds_at(epoch: float, noaa_station: str = NOAA_DEFAULT_STATION) -> dict:
    """Just the two wind readings at one instant (cheap; the 3D scene calls this on every slider move)."""
    return {"open_meteo": wind_at(_open_meteo(OPEN_METEO_POINT)[0], epoch),
            "noaa": wind_at(_noaa_wind(noaa_station), epoch)}


def compass(degrees: float) -> str:
    return strategy.COMPASS[round(degrees / 22.5) % 16]


@lru_cache(maxsize=1)
def _tides() -> pd.DataFrame:
    return strategy.load_tides()


def conditions_at(epoch: float, course_origin: tuple[float, float],
                  noaa_station: str = NOAA_DEFAULT_STATION, window: tuple[float, float] | None = None) -> dict:
    """Wind, tide and waves at one UTC instant. Missing sources come back as None, never as 0.

    `window` = (start, end) epochs of the race, used to tell whether the tide turns during it.
    """
    lat0, lng0 = course_origin
    om_frame, om_lat, om_lng = _open_meteo(OPEN_METEO_POINT)
    open_meteo = wind_at(om_frame, epoch)
    if open_meteo:
        open_meteo["source"] = (f"Open-Meteo model cell ({om_lat:.2f}, {om_lng:.2f}), "
                                f"{distance_km(lat0, lng0, om_lat, om_lng):.0f} km from the course")

    name, st_lat, st_lng = NOAA_WIND_STATIONS[noaa_station][0:3]
    noaa = wind_at(_noaa_wind(noaa_station), epoch)
    if noaa:
        noaa["source"] = (f"NOAA {name} ({noaa_station}), "
                          f"{distance_km(lat0, lng0, st_lat, st_lng):.0f} km from the course")

    waves = None
    ndbc = _ndbc_waves(NDBC_STATION[0])
    height = _interp(ndbc, "wave_m", epoch, max_gap_s=3600) if not ndbc.empty else None
    if height is not None:
        waves = {"height_m": height, "period_s": _interp(ndbc, "period_s", epoch, max_gap_s=3600),
                 "source": f"NDBC {NDBC_STATION[0]} {NDBC_STATION[1]}, "
                           f"{distance_km(lat0, lng0, NDBC_STATION[2], NDBC_STATION[3]):.0f} km from the course"}

    local = pd.Timestamp(epoch, unit="s", tz="UTC").tz_convert(VENUE_TZ).tz_localize(None)
    tides = _tides()
    tide = strategy.tide_state(tides, local)
    tide_turns_in_race = None
    if window is not None:
        a = pd.Timestamp(window[0], unit="s", tz="UTC").tz_convert(VENUE_TZ).tz_localize(None)
        b = pd.Timestamp(window[1], unit="s", tz="UTC").tz_convert(VENUE_TZ).tz_localize(None)
        tide_turns_in_race = bool(((tides["time"] >= a) & (tides["time"] <= b)).any())
    return {
        "epoch": epoch, "local": local_clock(epoch), "open_meteo": open_meteo, "noaa": noaa,
        "waves": waves, "tide": {"state": tide["state"], "turns": tide["turns"],
                                 "turns_in_race": tide_turns_in_race,
                                 "source": f"NOAA {TIDE_STATION[0]} {TIDE_STATION[1]} (predictions)"},
    }


# ---------- strategy documents (synthetic corpus) ----------

def _doc_sections(path: Path) -> dict:
    text = path.read_text()
    front = dict(re.findall(r"^([a-z_]+):\s*(.+)$", text.split("---")[1], re.M)) if text.startswith("---") else {}
    sections = {m.group(1).strip(): m.group(2) for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S)}
    return {"title": front.get("title", path.stem), "sections": sections}


def strategy_documents(conditions: dict, source: str = "noaa") -> dict:
    """Run the deterministic trigger rules of the RAG on the measured conditions.

    Returns {"selected": [{id, title, reason, tier, core, upwind}], "missing": [...], "inputs": {...}}.
    Inputs the data cannot provide stay None and are reported as missing, never guessed.
    """
    from backend.rag.triggers import Conditions, select_documents  # noqa: PLC0415

    wind = conditions.get(source) or conditions.get("open_meteo") or conditions.get("noaa") or {}
    inputs = {
        "wind_mean_kt": wind.get("speed_kn"), "gust_kt": wind.get("gust_kn"),
        "wind_rise_kt_2h": wind.get("rise_2h_kn"),
        "cloud_cover_pct": (conditions.get("open_meteo") or {}).get("cloud_pct"),
        "wave_height_m": (conditions.get("waves") or {}).get("height_m"),
        "tide_change_during_race": conditions["tide"].get("turns_in_race"),
    }
    inputs = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in inputs.items()}
    selection = select_documents(Conditions(**inputs))
    documents = []
    for doc_id in selection.doc_ids:
        path = next(iter(sorted(CORPUS.glob(f"{doc_id}_*.md"))), None)
        info = _doc_sections(path) if path else {"title": doc_id, "sections": {}}
        documents.append({
            "id": doc_id, "title": info["title"], "reason": selection.reasons[doc_id],
            "tier": selection.tiers[doc_id],
            "core": info["sections"].get("Core idea", "").strip(),
            "upwind": info["sections"].get("Upwind", "").strip(),
        })
    return {"selected": documents, "missing": list(selection.missing), "inputs": inputs}


# ---------- depth (bathymetry) ----------

@lru_cache(maxsize=1)
def _bathymetry():
    payload = json.loads(BATHYMETRY.read_text())
    grid = payload["grid"]
    values = np.asarray(payload["values"], dtype=np.float32)
    if values.ndim == 1:
        values = values.reshape(grid["rows"], grid["cols"])
    return values, grid


def bathymetry_image(bounds: tuple[float, float, float, float], max_px: int = 700):
    """PNG data-URI of seabed depth inside bounds=(west, south, east, north), plus exact bounds.

    Water is shaded light -> dark blue over 0-30 m; land (elevation >= 0) is sand.
    """
    from PIL import Image  # noqa: PLC0415

    values, grid = _bathymetry()
    west, south, east, north = bounds
    step = grid["step_deg"]
    c0 = max(int((west - grid["west"]) / step), 0)
    c1 = min(int(math.ceil((east - grid["west"]) / step)), grid["cols"])
    r0 = max(int((grid["north"] - north) / step), 0)
    r1 = min(int(math.ceil((grid["north"] - south) / step)), grid["rows"])
    if c1 - c0 < 2 or r1 - r0 < 2:
        return None
    patch = values[r0:r1, c0:c1]
    stride = max(1, int(math.ceil(max(patch.shape) / max_px)))
    patch = patch[::stride, ::stride]
    depth = np.clip(-patch, 0, 30) / 30.0
    shallow, deep = np.array([190, 224, 235]), np.array([14, 58, 112])
    rgb = shallow + (deep - shallow) * depth[..., None]
    rgb = np.where((patch >= 0)[..., None], np.array([221, 211, 183]), rgb)
    alpha = np.full(patch.shape, 215, dtype=np.uint8)
    image = Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), "RGBA")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    exact = (grid["west"] + c0 * step, grid["north"] - r1 * step,
             grid["west"] + c1 * step, grid["north"] - r0 * step)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(), exact
