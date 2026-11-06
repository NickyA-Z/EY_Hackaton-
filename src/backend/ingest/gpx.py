"""GPX tracks (GPS Exchange Format 1.0/1.1): <trkpt lat lon><time>.

Times in GPX are ISO 8601, normally UTC ('Z'). Each <trk> becomes one track_id
(file stem, plus the track index when a file holds several tracks).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from . import schema, tracks

log = logging.getLogger(__name__)
SOURCE = "gpx"


def sniff(_name: str, head: str | None) -> float:
    return 0.95 if head and "<gpx" in head[:2000] else 0.0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]          # drop the XML namespace


def parse(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    try:
        root = ET.parse(path).getroot()    # stdlib parser: no external entities are fetched
    except ET.ParseError as e:
        log.error("%s: not valid XML: %s", path.name, e)
        return schema.empty("tracks")

    rows, skipped = [], 0
    trks = [el for el in root.iter() if _local(el.tag) == "trk"]
    for i, trk in enumerate(trks):
        name = next((el.text for el in trk if _local(el.tag) == "name" and el.text), None)
        track_id = path.stem if len(trks) == 1 else f"{path.stem}_{i + 1}"
        for pt in trk.iter():
            if _local(pt.tag) != "trkpt":
                continue
            time = next((el.text for el in pt if _local(el.tag) == "time"), None)
            try:
                rows.append({"time_utc": time, "lat": float(pt.get("lat")), "lon": float(pt.get("lon")),
                             "track_id": track_id, "sailor": name})
            except (TypeError, ValueError):
                skipped += 1
    if skipped:
        log.warning("%s: skipped %d track points without valid lat/lon", path.name, skipped)
    if not rows:
        log.error("%s: no <trkpt> elements found", path.name)
        return schema.empty("tracks")

    df = pd.DataFrame(rows)
    t = pd.to_datetime(df["time_utc"], errors="coerce", utc=False, format="mixed")
    df["time_utc"] = t.dt.tz_localize("UTC") if t.dt.tz is None else t.dt.tz_convert("UTC")
    df["source"], df["is_top_finisher"], df["is_sample"] = SOURCE, False, False
    return tracks.finish(df, path.name)
