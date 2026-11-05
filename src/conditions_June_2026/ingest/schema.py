"""Common data model: column lists, dtypes, conforming and validation."""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

UTC = pd.DatetimeTZDtype(unit="ns", tz="UTC")

OBSERVATION_COLUMNS: dict[str, object] = {
    "time_utc": UTC,
    "lat": "float64",
    "lon": "float64",
    "source": "string",
    "source_id": "string",
    "wind_dir_deg": "float64",   # direction the wind blows FROM; NaN if calm/variable
    "wind_speed_kn": "float64",
    "wind_gust_kn": "float64",
    "air_temp_c": "float64",
    "water_temp_c": "float64",
    "wave_height_m": "float64",
    "cloud_cover_pct": "float64",
    "is_sample": "bool",
}
OBSERVATION_KEY = ["source", "source_id", "time_utc"]
OBSERVATION_REQUIRED = ["time_utc", "source", "source_id", "is_sample"]

TIDE_EVENT_COLUMNS: dict[str, object] = {
    "time_utc": UTC,
    "station_id": "string",
    "height_m": "float64",
    "type": "string",   # 'H' or 'L'
}
TIDE_EVENT_KEY = ["station_id", "time_utc"]

TABLES = {
    "observations": (OBSERVATION_COLUMNS, OBSERVATION_KEY),
    "tide_events": (TIDE_EVENT_COLUMNS, TIDE_EVENT_KEY),
}

# Plausibility ranges used by validate(); values outside are reported, not silently fixed.
RANGES = {
    "lat": (-90, 90),
    "lon": (-180, 180),
    "wind_dir_deg": (0, 360),
    "wind_speed_kn": (0, 60),
    "wind_gust_kn": (0, 80),
    "air_temp_c": (-10, 50),
    "water_temp_c": (0, 35),
    "wave_height_m": (0, 15),
    "cloud_cover_pct": (0, 100),
    "height_m": (-3, 4),
}


def empty(table: str = "observations") -> pd.DataFrame:
    return conform(pd.DataFrame(), table)


def conform(df: pd.DataFrame, table: str = "observations") -> pd.DataFrame:
    """Add missing columns as nulls, drop unknown ones, cast dtypes, fix column order."""
    columns, _ = TABLES[table]
    out = pd.DataFrame(index=df.index)
    for col, dtype in columns.items():
        if col in df.columns:
            s = df[col]
        elif dtype == "bool":
            s = pd.Series(False, index=df.index)
        else:
            s = pd.Series(pd.NA, index=df.index, dtype="object")
        if dtype is UTC:
            s = pd.to_datetime(s, utc=True).astype(UTC)
        elif dtype == "float64":
            s = pd.to_numeric(s, errors="coerce").astype("float64")
        else:
            s = s.astype(dtype)
        out[col] = s
    if table == "observations":
        out = apply_calm_rule(out)
    return out.reset_index(drop=True)


def apply_calm_rule(df: pd.DataFrame) -> pd.DataFrame:
    """Direction is undefined in calm air: wind_dir_deg = NaN where wind_speed_kn == 0.

    Sources disagree here (METAR writes 00000KT, CO-OPS writes 0.0 deg), so the
    rule lives in one place for all sources.
    """
    calm = df["wind_speed_kn"] == 0
    if calm.any():
        df.loc[calm, "wind_dir_deg"] = float("nan")
    return df


def coalesce_duplicates(df: pd.DataFrame, table: str = "observations") -> pd.DataFrame:
    """Merge rows sharing the table key, taking the first non-null value per column.

    Needed because one station can deliver different variables in different files
    (e.g. CO-OPS wind and air_temperature for the same station and hour).
    """
    _, key = TABLES[table]
    if df.empty:
        return df
    n = len(df)
    merged = df.groupby(key, sort=False, dropna=False).first().reset_index()
    if len(merged) != n:
        log.info("%s: merged %d duplicate-key rows", table, n - len(merged))
    return conform(merged, table)


def validate(df: pd.DataFrame, table: str = "observations") -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    columns, key = TABLES[table]
    problems: list[str] = []
    missing = [c for c in columns if c not in df.columns]
    if missing:
        problems.append(f"missing columns: {missing}")
        return problems
    for col, dtype in columns.items():
        if str(df[col].dtype) != str(dtype):
            problems.append(f"{col}: dtype {df[col].dtype}, expected {dtype}")
    required = OBSERVATION_REQUIRED if table == "observations" else key
    for col in required:
        n = int(df[col].isna().sum())
        if n:
            problems.append(f"{col}: {n} null values in required column")
    for col, (lo, hi) in RANGES.items():
        if col in df.columns:
            bad = df[col].notna() & ~df[col].between(lo, hi)
            if bad.any():
                problems.append(f"{col}: {int(bad.sum())} values outside [{lo}, {hi}]")
    dups = int(df.duplicated(key).sum())
    if dups:
        problems.append(f"{dups} duplicate rows on key {key}")
    if table == "tide_events":
        bad = ~df["type"].isin(["H", "L"])
        if bad.any():
            problems.append(f"type: {int(bad.sum())} values not in ('H', 'L')")
    return problems
