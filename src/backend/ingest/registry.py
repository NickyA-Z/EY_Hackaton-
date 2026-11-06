"""Which parser handles which raw files, and which categories the inbox can sort into.

Adding a new format (e.g. a GPX track or a coach's Excel sheet):
  1. create ingest/<format>.py with `parse(path) -> DataFrame` that returns
     `schema.conform(df)`, and `sniff(name, head) -> float` (0-1 confidence);
  2. add one `Source(...)` line to SOURCES below (or move its Category entry there);
  3. add a test with a tiny fixture in tests/.
run.py, validation, the report and the inbox classifier pick it up automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from . import coops, gpx, metar, ndbc, open_meteo, sailsync
from .config import EXTERNAL_DIRS

Sniffer = Callable[[str, Optional[str]], float]


@dataclass(frozen=True)
class Category:
    """A kind of file the inbox can recognise and where it is stored under data/weather/raw."""
    key: str                       # stable id, also the classifier's label
    description: str               # shown to the user and to the LLM classifier
    subdir: str                    # folder under data/weather/raw
    sniff: Optional[Sniffer] = None
    # File name inside subdir, formatted with source_id / period / ext / product.
    # None = keep the (sanitised) original name.
    filename: Optional[str] = None
    needs: tuple[str, ...] = ()    # proposal fields required to build the file name


@dataclass(frozen=True)
class Source(Category):
    """A category that has a parser feeding the common data model."""
    name: str = ""                                  # value of the `source` column
    table: str = "observations"                     # "observations" or "tide_events"
    patterns: tuple[str, ...] = ()                  # globs relative to data/weather/raw
    parse: Optional[Callable[[Path], pd.DataFrame]] = None
    exclude: tuple[str, ...] = field(default=())    # globs to skip

    external_patterns: tuple[str, ...] = ()        # globs inside EXTERNAL_DIRS[key]

    def files(self, raw_dir: Path, include_external: bool = False) -> list[Path]:
        found = {p for pat in self.patterns for p in raw_dir.glob(pat)}
        skipped = {p for pat in self.exclude for p in raw_dir.glob(pat)}
        ext = EXTERNAL_DIRS.get(self.key)
        if include_external and ext is not None and ext.exists():
            found |= {p for pat in self.external_patterns for p in ext.glob(pat)}
        return sorted(found - skipped)


SOURCES: list[Source] = [
    Source(key="metar", name="metar", subdir="metar",
           description="Airport METAR reports as CSV with columns station,valid,metar (IEM export)",
           sniff=metar.sniff, filename="{source_id}_{period}.csv", needs=("source_id", "period"),
           patterns=("metar/*.csv",), parse=metar.parse),
    Source(key="coops", name="coops", subdir="noaa_coops",
           description="NOAA CO-OPS station CSV: 'Date Time' plus wind speed/direction/gust or air/water temperature",
           sniff=coops.sniff, filename="{source_id}_{product}_{period}.csv", needs=("source_id", "period"),
           patterns=("noaa_coops/*.csv",), parse=coops.parse,
           exclude=("noaa_coops/*_predictions_*.csv",)),
    Source(key="coops_tides", name="coops", table="tide_events", subdir="noaa_coops",
           description="NOAA CO-OPS tide predictions CSV: 'Date Time, Prediction, Type' (H/L)",
           sniff=coops.sniff_tides, filename="{source_id}_predictions_{period}.csv",
           needs=("source_id", "period"),
           patterns=("noaa_coops/*_predictions_*.csv",), parse=coops.parse_tide_events),
    Source(key="ndbc", name="ndbc", subdir="ndbc",
           description="NDBC buoy standard meteorological text (header '#YY MM DD hh mm WDIR WSPD ...'), often .gz",
           sniff=ndbc.sniff, filename="{source_id}_{period}{ext}", needs=("source_id", "period"),
           patterns=("ndbc/*.txt.gz", "ndbc/*.txt"), parse=ndbc.parse),
    Source(key="open_meteo", name="open_meteo", subdir="open_meteo",
           description="Open-Meteo API JSON with 'hourly' arrays (time, wind_speed_10m, ...) for one point",
           sniff=open_meteo.sniff, filename="{source_id}_{period}.json", needs=("source_id", "period"),
           patterns=("open_meteo/*.json",), parse=open_meteo.parse),
    Source(key="gps_track", name="sailsync", table="tracks", subdir="tracks",
           description="GPS track of a boat as CSV with time + lat + lon/lng columns (e.g. SailSync export)",
           sniff=sailsync.sniff, patterns=("tracks/**/*.csv",), parse=sailsync.parse,
           external_patterns=("*.csv", "winners/*.csv")),
    Source(key="gpx_track", name="gpx", table="tracks", subdir="tracks",
           description="GPS track in GPX format (XML with <trkpt lat lon><time>)",
           sniff=gpx.sniff, patterns=("tracks/**/*.gpx",), parse=gpx.parse),
]


# --- categories that are recognised and stored, but have no parser yet -------------

def _sniff_raster(name: str, head: Optional[str]) -> float:
    return 0.9 if name.lower().endswith((".tif", ".tiff")) else 0.0


STORAGE_ONLY: list[Category] = [
    Category(key="geo_raster", subdir="geo", sniff=_sniff_raster,
             description="Gridded geodata such as bathymetry or terrain (GeoTIFF)"),
    Category(key="coach_notes", subdir="notes",
             description="Free text written by people: coach debriefs, venue notes, reports (txt, md, pdf, docx)"),
    Category(key="other_tabular", subdir="other",
             description="Any other table (CSV, Excel) with measurements that no parser handles yet"),
]

UNKNOWN = Category(key="unknown", subdir="", description="Cannot tell what this file is")

CATEGORIES: dict[str, Category] = {c.key: c for c in [*SOURCES, *STORAGE_ONLY, UNKNOWN]}
