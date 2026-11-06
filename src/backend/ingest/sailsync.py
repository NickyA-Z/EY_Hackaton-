"""GPS tracks as CSV: SailSync exports and similar time + lat + lon tables.

SailSync file: <session>_<track>_<First>_<Last>_<NAT>_<sailno>.csv with columns
time_epoch,lat,lng (epoch seconds = UTC). The name part can be missing.
Files inside a folder called 'winners' are flagged is_top_finisher.

Other CSV tracks are accepted when they have a time column (time_epoch, or an
ISO time/timestamp/datetime column) and lat + lon/lng/long columns.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from . import schema, tracks

log = logging.getLogger(__name__)
SOURCE = "sailsync"

NAME_RE = re.compile(r"^(?P<session>\d+)_(?P<track>\d+)_(?:(?P<name>.+?)_)?(?P<nat>[A-Z]{3})_(?P<sailno>\d+)$")
TIME_COLUMNS = ("time_epoch", "epoch", "time", "timestamp", "datetime", "time_utc")
LON_COLUMNS = ("lon", "lng", "long", "longitude")
LAT_COLUMNS = ("lat", "latitude")
TOP_FOLDERS = {"winners", "top", "podium"}


def _header(head: str | None) -> set[str]:
    if not head or not head.strip():
        return set()
    return {c.strip().lower() for c in head.splitlines()[0].split(",")}


def sniff(_name: str, head: str | None) -> float:
    """Confidence that a file is a CSV GPS track (time + lat + lon columns)."""
    cols = _header(head)
    has_time = any(c in cols for c in TIME_COLUMNS)
    if has_time and cols & set(LAT_COLUMNS) and cols & set(LON_COLUMNS):
        return 0.95 if {"time_epoch", "lat", "lng"} <= cols else 0.9
    return 0.0


def identity(path: Path) -> dict:
    """track_id / sailor / nation / sail_no from a SailSync-style file name."""
    m = NAME_RE.match(path.stem)
    if not m:
        return {"track_id": path.stem, "sailor": None, "nation": None, "sail_no": None}
    name = m["name"].replace("_", " ") if m["name"] else None
    return {"track_id": f"{m['session']}_{m['track']}", "sailor": name,
            "nation": m["nat"], "sail_no": f"{m['nat']} {m['sailno']}"}


def _pick(columns, candidates) -> str | None:
    lower = {c.lower(): c for c in columns}
    return next((lower[c] for c in candidates if c in lower), None)


def _times(raw: pd.DataFrame, col: str, name: str) -> pd.Series:
    values = raw[col]
    numeric = pd.to_numeric(values, errors="coerce")
    if col.lower() in ("time_epoch", "epoch") or numeric.notna().mean() > 0.9:
        # epoch seconds; round away float noise such as .099999905
        return pd.to_datetime(numeric, unit="s", utc=True, errors="coerce").dt.round("ms")
    t = pd.to_datetime(values, errors="coerce", utc=False, format="mixed")
    if t.dt.tz is None:
        log.warning("%s: time column has no time zone; assuming UTC", name)
        return t.dt.tz_localize("UTC")
    return t.dt.tz_convert("UTC")


def parse(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    bad_lines: list[list[str]] = []
    raw = pd.read_csv(path, dtype=str, engine="python", skipinitialspace=True,
                      on_bad_lines=bad_lines.append)
    if bad_lines:
        log.warning("%s: skipped %d malformed lines", path.name, len(bad_lines))
    tcol, latcol, loncol = (_pick(raw.columns, c) for c in (TIME_COLUMNS, LAT_COLUMNS, LON_COLUMNS))
    if not (tcol and latcol and loncol):
        log.error("%s: need time + lat + lon columns, got %s", path.name, list(raw.columns))
        return schema.empty("tracks")

    df = pd.DataFrame({
        "time_utc": _times(raw, tcol, path.name),
        "lat": pd.to_numeric(raw[latcol], errors="coerce"),
        "lon": pd.to_numeric(raw[loncol], errors="coerce"),
    })
    for key, value in identity(path).items():
        df[key] = value
    df["source"] = SOURCE
    df["is_top_finisher"] = path.parent.name.lower() in TOP_FOLDERS
    df["is_sample"] = False
    return tracks.finish(df, path.name)
