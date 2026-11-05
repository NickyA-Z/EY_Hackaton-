"""Open-Meteo archive API JSON (hourly parallel arrays).

`hourly.time` is local wall-clock time without an offset. The file's
`utc_offset_seconds` is the authoritative offset: in our June files it is -28800
(GMT-8), not PDT (-25200). This was verified by re-requesting the same day with
timezone=GMT. Only if the field is missing do we fall back to the IANA `timezone`.
lat/lon are the model grid cell Open-Meteo snapped to, not the requested point.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema, units

log = logging.getLogger(__name__)
SOURCE = "open_meteo"

SUFFIX_RE = re.compile(r"_\d{6}$")   # trailing _YYYYMM in file names

# common-schema column -> (Open-Meteo variable, kind for unit conversion)
VARIABLES = {
    "wind_speed_kn": ("wind_speed_10m", "speed"),
    "wind_gust_kn": ("wind_gusts_10m", "speed"),
    "wind_dir_deg": ("wind_direction_10m", None),
    "air_temp_c": ("temperature_2m", "temp"),
    "cloud_cover_pct": ("cloud_cover", None),
}


def _to_utc(times: pd.Series, meta: dict) -> pd.Series:
    if meta.get("utc_offset_seconds") is not None:
        return units.local_to_utc(times, int(meta["utc_offset_seconds"]))
    tz = meta.get("timezone") or "UTC"
    log.warning("no utc_offset_seconds; localizing with IANA zone %s", tz)
    local = pd.to_datetime(times).dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    return local.dt.tz_convert("UTC")


def parse(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    meta = json.loads(path.read_text(encoding="utf-8"))
    hourly = meta.get("hourly") or {}
    hourly_units = meta.get("hourly_units") or {}
    if "time" not in hourly:
        log.error("%s: no hourly.time array", path.name)
        return schema.empty()

    lengths = {k: len(v) for k, v in hourly.items()}
    n = min(lengths.values())
    if len(set(lengths.values())) > 1:
        log.warning("%s: hourly arrays have different lengths %s; truncating to %d", path.name, lengths, n)

    times = pd.Series(hourly["time"][:n])
    out = pd.DataFrame({"time_utc": _to_utc(times, meta)})
    for col, (var, kind) in VARIABLES.items():
        if var not in hourly:
            log.info("%s: variable %s not present", path.name, var)
            continue
        values = pd.Series(hourly[var][:n], dtype="float64")   # JSON null -> NaN
        unit = hourly_units.get(var, "")
        if kind == "speed":
            values = units.speed_to_kn(values, unit or "km/h")   # API default is km/h
        elif kind == "temp":
            values = units.temp_to_c(values, unit or "C")
        out[col] = values

    bad = out["time_utc"].isna()
    if bad.any():
        log.warning("%s: skipped %d rows with invalid time", path.name, int(bad.sum()))
        out = out[~bad]

    out["lat"] = meta.get("latitude", np.nan)
    out["lon"] = meta.get("longitude", np.nan)
    out["source"] = SOURCE
    out["source_id"] = SUFFIX_RE.sub("", path.stem).removeprefix("open_meteo_")
    out["is_sample"] = False
    return schema.conform(out)
