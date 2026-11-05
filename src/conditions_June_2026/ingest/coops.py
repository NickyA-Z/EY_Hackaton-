"""NOAA CO-OPS data-getter CSV (requested with units=metric, time_zone=gmt).

File names: {station}_{product}_{YYYYMM}.csv. Column names carry leading spaces,
and the wind product has two "Direction" columns (degrees, then compass text).
The files do NOT state their units; they are metric because the downloader asks
for units=metric (wind m/s, temperature degC, tide height m above MLLW).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from . import schema, units
from .config import station_coords

log = logging.getLogger(__name__)
SOURCE = "coops"

STATION_RE = re.compile(r"(?<!\d)(\d{7})(?!\d)")   # CO-OPS station ids are 7 digits
SPEED_UNIT = "m/s"   # units=metric


def _station_from_name(path: Path) -> str:
    m = STATION_RE.search(path.stem)
    return m[1] if m else path.stem.split("_")[0]


def _header(head: str | None) -> list[str]:
    if not head or not head.strip():
        return []
    return [c.strip() for c in head.splitlines()[0].split(",")]


def sniff(name: str, head: str | None) -> float:
    """Confidence that a file is a CO-OPS met product (wind / air or water temperature)."""
    cols = _header(head)
    if cols[:1] == ["Date Time"] and {"Speed", "Air Temperature", "Water Temperature"} & set(cols):
        return 0.95
    return 0.0


def sniff_tides(name: str, head: str | None) -> float:
    """Confidence that a file is a CO-OPS tide high/low prediction CSV."""
    cols = _header(head)
    return 0.95 if cols[:1] == ["Date Time"] and {"Prediction", "Type"} <= set(cols) else 0.0


def _read(path: Path) -> pd.DataFrame:
    bad_lines: list[list[str]] = []
    df = pd.read_csv(path, dtype=str, engine="python", skipinitialspace=True,
                     on_bad_lines=lambda line: bad_lines.append(line))
    if bad_lines:
        log.warning("%s: skipped %d malformed lines", path.name, len(bad_lines))
    # " Direction" twice -> pandas names them "Direction" and "Direction.1"
    df.columns = [c.strip() for c in df.columns]
    if "Date Time" not in df.columns:
        raise ValueError(f"{path.name}: no 'Date Time' column (got {list(df.columns)})")
    df["time_utc"] = pd.to_datetime(df["Date Time"], format="%Y-%m-%d %H:%M", errors="coerce", utc=True)
    bad = df["time_utc"].isna()
    if bad.any():
        log.warning("%s: skipped %d rows with unparseable time", path.name, int(bad.sum()))
    return df[~bad]


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def _direction_degrees(df: pd.DataFrame) -> pd.Series:
    """Pick the numeric one of the (possibly duplicated) Direction columns."""
    for col in [c for c in df.columns if c.split(".")[0] == "Direction"]:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().any() or df[col].isna().all():
            return values
    return pd.Series(float("nan"), index=df.index)


def parse(path: str | Path) -> pd.DataFrame:
    """Met products (wind / air_temperature / water_temperature) -> observations."""
    path = Path(path)
    station = _station_from_name(path)
    df = _read(path)
    if "Prediction" in df.columns:
        log.warning("%s: tide predictions are events; use parse_tide_events()", path.name)
        return schema.empty()

    out = pd.DataFrame({"time_utc": df["time_utc"]})
    if "Speed" in df.columns:
        out["wind_speed_kn"] = units.speed_to_kn(_num(df, "Speed"), SPEED_UNIT)
        out["wind_gust_kn"] = units.speed_to_kn(_num(df, "Gust"), SPEED_UNIT)
        out["wind_dir_deg"] = _direction_degrees(df)
    if "Air Temperature" in df.columns:
        out["air_temp_c"] = units.temp_to_c(_num(df, "Air Temperature"), "C")
    if "Water Temperature" in df.columns:
        out["water_temp_c"] = units.temp_to_c(_num(df, "Water Temperature"), "C")
    if out.shape[1] == 1:
        log.warning("%s: no known measurement columns in %s", path.name, list(df.columns))

    lat, lon = station_coords(SOURCE, station)
    if pd.isna(lat):
        log.warning("%s: no coordinates configured for station %s", path.name, station)
    out["lat"], out["lon"] = lat, lon
    out["source"], out["source_id"], out["is_sample"] = SOURCE, station, False
    return schema.conform(out)


def parse_tide_events(path: str | Path) -> pd.DataFrame:
    """Tide high/low predictions (interval=hilo, datum MLLW) -> tide_events."""
    path = Path(path)
    df = _read(path)
    if not {"Prediction", "Type"} <= set(df.columns):
        log.error("%s: expected Prediction and Type columns, got %s", path.name, list(df.columns))
        return schema.empty("tide_events")
    out = pd.DataFrame({
        "time_utc": df["time_utc"],
        "station_id": _station_from_name(path),
        "height_m": _num(df, "Prediction"),
        "type": df["Type"].str.strip().str.upper(),
    })
    bad = out["height_m"].isna() | ~out["type"].isin(["H", "L"])
    if bad.any():
        log.warning("%s: skipped %d invalid tide rows", path.name, int(bad.sum()))
    return schema.conform(out[~bad], "tide_events")
