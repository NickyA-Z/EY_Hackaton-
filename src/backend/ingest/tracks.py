"""Shared helpers for GPS-track parsers (sailsync.py, gpx.py): motion and finishing.

Track parsers only need to produce time_utc / lat / lon (+ identity columns);
finish() sorts, de-duplicates, derives speed and course, and conforms to the
`tracks` table in schema.py.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import schema, units

log = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0
MAX_GAP_S = 30.0          # no speed across a logging gap longer than this
MAX_SPEED_KN = 30.0       # faster than any Olympic dinghy/board: a GPS jump


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (vectorised)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat, dlon = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees 0-360 (vectorised)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2) - np.radians(lon1)
    y = np.sin(dlon) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dlon)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def add_motion(df: pd.DataFrame, name: str = "") -> pd.DataFrame:
    """speed_kn / course_deg from each fix to the previous one of the same track."""
    df = df.sort_values(["track_id", "time_utc"]).copy()
    prev = df.groupby("track_id")[["lat", "lon", "time_utc"]].shift(1)
    dt_s = (df["time_utc"] - prev["time_utc"]).dt.total_seconds()
    dist = haversine_m(prev["lat"], prev["lon"], df["lat"], df["lon"])
    speed = units.ms_to_kn(dist / dt_s.where(dt_s > 0))
    course = bearing_deg(prev["lat"], prev["lon"], df["lat"], df["lon"])

    gap = dt_s > MAX_GAP_S
    jump = speed > MAX_SPEED_KN
    if jump.any():
        log.info("%s: %d GPS jumps (> %.0f kn) set to NaN", name, int(jump.sum()), MAX_SPEED_KN)
    bad = gap | jump | dt_s.isna()
    df["speed_kn"] = speed.mask(bad)
    df["course_deg"] = course.where(~bad & (dist > 0))   # no course while not moving
    return df


def finish(df: pd.DataFrame, name: str = "") -> pd.DataFrame:
    """Drop invalid fixes, de-duplicate, add motion, conform to the tracks table."""
    bad = (df["time_utc"].isna() | df["lat"].isna() | df["lon"].isna()
           | ~df["lat"].between(-90, 90) | ~df["lon"].between(-180, 180))
    if bad.any():
        log.warning("%s: skipped %d fixes with missing/invalid time or position", name, int(bad.sum()))
    df = df[~bad]
    n = len(df)
    df = df.drop_duplicates(["track_id", "time_utc"])
    if len(df) != n:
        log.info("%s: dropped %d duplicate timestamps", name, n - len(df))
    if df.empty:
        return schema.empty("tracks")
    return schema.conform(add_motion(df, name), "tracks")
