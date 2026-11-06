"""METAR airport reports (Iowa Environmental Mesonet CSV: station,valid,metar).

`valid` is UTC. Wind, temperature and sky cover are parsed from the raw METAR string.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema, units
from .config import station_coords

log = logging.getLogger(__name__)
SOURCE = "metar"

# dddff(Gfff)KT / MPS; ddd may be VRB. Bounded by whitespace so "RMK" groups don't match.
WIND_RE = re.compile(r"(?<!\S)(?P<dir>\d{3}|VRB)(?P<spd>\d{2,3})(?:G(?P<gust>\d{2,3}))?(?P<unit>KT|MPS)(?!\S)")
TEMP_RE = re.compile(r"(?<!\S)(?P<t>M?\d{2})/(?P<d>M?\d{2})?(?!\S)")
# Remark T-group: T snnn snnn, tenths of a degree, s=1 means negative. More precise than TT/DD.
TGROUP_RE = re.compile(r"(?<!\S)T(?P<s>[01])(?P<t>\d{3})(?:[01]\d{3})?(?!\S)")
SKY_RE = re.compile(r"(?<!\S)(?P<cov>SKC|CLR|NSC|FEW|SCT|BKN|OVC|VV)(?:\d{3}|///)?(?:CB|TCU)?(?!\S)")
SPEED_UNIT = {"KT": "kn", "MPS": "m/s"}


def _metar_temp(text: str) -> float:
    return -float(text[1:]) if text.startswith("M") else float(text)


def parse_metar(report: str) -> dict:
    """Parse one raw METAR string into common-schema fields (no time / location)."""
    body, _, remarks = report.partition(" RMK ")
    out = {"wind_dir_deg": np.nan, "wind_speed_kn": np.nan, "wind_gust_kn": np.nan,
           "air_temp_c": np.nan, "cloud_cover_pct": np.nan}

    m = WIND_RE.search(body)
    if m:
        unit = SPEED_UNIT[m["unit"]]
        speed = float(units.speed_to_kn(float(m["spd"]), unit))
        out["wind_speed_kn"] = speed
        if m["gust"]:
            out["wind_gust_kn"] = float(units.speed_to_kn(float(m["gust"]), unit))
        # VRB -> NaN; calm (00000KT) -> NaN (direction undefined)
        if m["dir"] != "VRB" and speed > 0:
            out["wind_dir_deg"] = float(m["dir"])

    tg = TGROUP_RE.search(remarks)
    if tg:
        out["air_temp_c"] = (-1 if tg["s"] == "1" else 1) * int(tg["t"]) / 10.0
    else:
        mt = TEMP_RE.search(body)
        if mt:
            out["air_temp_c"] = _metar_temp(mt["t"])

    covers = [units.SKY_COVER_PCT[s["cov"]] for s in SKY_RE.finditer(body)]
    if covers:
        out["cloud_cover_pct"] = max(covers)
    return out


def sniff(name: str, head: str | None) -> float:
    """Confidence 0-1 that a file is an IEM METAR CSV (used by the inbox classifier)."""
    if not head:
        return 0.0
    first = head.splitlines()[0].strip().lower() if head.strip() else ""
    if first.replace(" ", "") == "station,valid,metar":
        return 0.95
    return 0.6 if re.search(r"\b\d{6}Z\b.*\b(\d{5}|VRB\d{2})(G\d{2})?KT\b", head) else 0.0


def parse(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    bad_lines: list[list[str]] = []
    raw = pd.read_csv(path, dtype=str, engine="python", skipinitialspace=True,
                      on_bad_lines=lambda line: bad_lines.append(line))
    if bad_lines:
        log.warning("%s: skipped %d malformed lines", path.name, len(bad_lines))
    raw.columns = [c.strip().lower() for c in raw.columns]
    if not {"station", "valid", "metar"} <= set(raw.columns):
        log.error("%s: expected columns station,valid,metar, got %s", path.name, list(raw.columns))
        return schema.empty()

    raw["time_utc"] = pd.to_datetime(raw["valid"], format="%Y-%m-%d %H:%M", errors="coerce", utc=True)
    bad = raw["time_utc"].isna() | raw["metar"].isna() | raw["station"].isna()
    if bad.any():
        log.warning("%s: skipped %d rows with unparseable time or empty report", path.name, int(bad.sum()))
    raw = raw[~bad]

    # IEM sometimes delivers the same minute twice: a regular report and a MADIS
    # high-frequency copy ("MADISHF"). Prefer the regular one.
    raw = raw.assign(_madis=raw["metar"].str.contains("MADISHF", regex=False))
    raw = raw.sort_values(["station", "time_utc", "_madis"]).drop_duplicates(["station", "time_utc"])

    fields = pd.DataFrame([parse_metar(r) for r in raw["metar"]], index=raw.index)
    no_wind = fields["wind_speed_kn"].isna().sum()
    if no_wind:
        log.info("%s: %d reports without a wind group", path.name, int(no_wind))

    df = pd.concat([raw[["time_utc", "station"]], fields], axis=1).rename(columns={"station": "source_id"})
    coords = df["source_id"].map(lambda s: station_coords(SOURCE, s))
    df["lat"] = [c[0] for c in coords]
    df["lon"] = [c[1] for c in coords]
    df["source"] = SOURCE
    df["is_sample"] = False
    return schema.conform(df)
