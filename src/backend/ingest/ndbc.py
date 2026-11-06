"""NDBC standard meteorological data (stdmet), whitespace-separated, usually gzipped.

Line 1: header starting with '#YY'; line 2: units starting with '#yr' (skipped).
Times are UTC. Missing values are written as 'MM' or as all-9 sentinels whose
width depends on the column (999, 99.0, 99.00, 9999.0, ...).
"""
from __future__ import annotations

import gzip
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema, units
from .config import REQUESTED_MONTHS, station_coords

log = logging.getLogger(__name__)
SOURCE = "ndbc"

BUOY_RE = re.compile(r"(?<![0-9A-Za-z])(\d{5})(?!\d)")   # 5-digit WMO buoy id
SPEED_UNIT = "m/s"

# Column -> sentinel values that mean "missing" (in addition to 'MM').
MISSING = {
    "WDIR": {999}, "MWD": {999},
    "WSPD": {99.0}, "GST": {99.0},
    "WVHT": {99.0}, "DPD": {99.0}, "APD": {99.0},
    "PRES": {9999.0}, "ATMP": {999.0}, "WTMP": {999.0}, "DEWP": {999.0},
    "VIS": {99.0}, "TIDE": {99.0},
}


def _open(path: Path):
    return gzip.open(path, "rt") if path.suffix == ".gz" else open(path)


def _header(path: Path) -> list[str]:
    with _open(path) as f:
        first = f.readline()
    if not first.startswith("#"):
        raise ValueError(f"{path.name}: first line is not a '#YY' header: {first[:40]!r}")
    return first.lstrip("#").split()


def sniff(name: str, head: str | None) -> float:
    """Confidence that a file is NDBC stdmet text (header line starts with '#YY')."""
    if not head:
        return 0.0
    first = head.lstrip().split("\n", 1)[0]
    if re.match(r"#\s*YY(YY)?\s+MM\s+DD\s+hh", first):
        return 0.95
    return 0.0


def parse(path: str | Path, months=REQUESTED_MONTHS) -> pd.DataFrame:
    """Parse one NDBC file. `months` keeps only those months (None = keep all)."""
    path = Path(path)
    m = BUOY_RE.search(path.name)
    buoy = m[1] if m else path.name.split("_")[0]
    names = _header(path)

    bad_lines: list[list[str]] = []
    raw = pd.read_csv(path, sep=r"\s+", comment="#", header=None, names=names, dtype=str,
                      na_values=["MM"], keep_default_na=False, engine="python",
                      on_bad_lines=lambda line: bad_lines.append(line))
    if bad_lines:
        log.warning("%s: skipped %d malformed lines", path.name, len(bad_lines))

    num = raw.apply(pd.to_numeric, errors="coerce")
    for col, sentinels in MISSING.items():
        if col in num.columns:
            num[col] = num[col].mask(num[col].isin(sentinels))

    # Old files use 'YY' (2-digit) or 'YYYY' and may lack minutes.
    year_col = next((c for c in ("YY", "YYYY") if c in num.columns), None)
    if year_col is None or not {"MM", "DD", "hh"} <= set(num.columns):
        log.error("%s: cannot find date columns in header %s", path.name, names)
        return schema.empty()
    year = num[year_col].where(num[year_col] >= 100, num[year_col] + 1900)
    parts = pd.DataFrame({"year": year, "month": num["MM"], "day": num["DD"],
                          "hour": num["hh"], "minute": num["mm"] if "mm" in num else 0})
    time = pd.to_datetime(parts, errors="coerce", utc=True)
    bad = time.isna()
    if bad.any():
        log.warning("%s: skipped %d rows with invalid date", path.name, int(bad.sum()))
    keep = ~bad
    if months is not None:
        keep &= num["MM"].isin(months)

    def col(name):
        return num[name][keep] if name in num.columns else pd.Series(np.nan, index=num.index[keep])

    lat, lon = station_coords(SOURCE, buoy)
    if pd.isna(lat):
        log.warning("%s: no coordinates configured for buoy %s", path.name, buoy)
    out = pd.DataFrame({
        "time_utc": time[keep],
        "wind_dir_deg": col("WDIR"),
        "wind_speed_kn": units.speed_to_kn(col("WSPD"), SPEED_UNIT),
        "wind_gust_kn": units.speed_to_kn(col("GST"), SPEED_UNIT),
        "air_temp_c": units.temp_to_c(col("ATMP"), "C"),
        "water_temp_c": units.temp_to_c(col("WTMP"), "C"),
        "wave_height_m": col("WVHT"),
        "lat": lat, "lon": lon,
        "source": SOURCE, "source_id": buoy, "is_sample": False,
    })
    return schema.conform(out)
