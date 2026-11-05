"""Which parser handles which raw files.

Adding a new format (e.g. a GPX track or a coach's Excel sheet):
  1. create ingest/<format>.py with `parse(path) -> DataFrame` that returns
     `schema.conform(df)` (set is_sample=True for hand-made sample files);
  2. add one `Source(...)` line below;
  3. add a test with a tiny fixture in tests/.
run.py, validation and the report pick it up automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from . import coops, metar, ndbc, open_meteo


@dataclass(frozen=True)
class Source:
    name: str                               # value of the `source` column
    table: str                              # "observations" or "tide_events"
    patterns: tuple[str, ...]               # globs relative to data/raw
    parse: Callable[[Path], pd.DataFrame]
    exclude: tuple[str, ...] = field(default=())   # globs to skip

    def files(self, raw_dir: Path) -> list[Path]:
        found = {p for pat in self.patterns for p in raw_dir.glob(pat)}
        skipped = {p for pat in self.exclude for p in raw_dir.glob(pat)}
        return sorted(found - skipped)


SOURCES: list[Source] = [
    Source("metar", "observations", ("metar/*.csv",), metar.parse),
    Source("coops", "observations", ("noaa_coops/*.csv",), coops.parse,
           exclude=("noaa_coops/*_predictions_*.csv",)),
    Source("coops", "tide_events", ("noaa_coops/*_predictions_*.csv",), coops.parse_tide_events),
    Source("ndbc", "observations", ("ndbc/*.txt.gz", "ndbc/*.txt"), ndbc.parse),
    Source("open_meteo", "observations", ("open_meteo/*.json",), open_meteo.parse),
]
