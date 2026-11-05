"""Parse every file in data/raw into the common model and write parquet tables.

Usage (from src/conditions_June_2026):
  python -m ingest.run              # or: python ingest/run.py
  python -m ingest.run --quiet      # skip the verification report
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):          # allow `python ingest/run.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "ingest"

import pandas as pd

from ingest import schema
from ingest.config import PROCESSED_DIR, RAW_DIR, REQUESTED_MONTHS
from ingest.registry import SOURCES

log = logging.getLogger("ingest.run")
MEASUREMENTS = ["wind_dir_deg", "wind_speed_kn", "wind_gust_kn", "air_temp_c",
                "water_temp_c", "wave_height_m", "cloud_cover_pct"]


# Raw files that are metadata, not data (no parser expected).
METADATA_FILES = {"noaa_coops/stations_nearby.json"}


def unclaimed_files(raw_dir: Path) -> list[Path]:
    """Raw files no registered parser picks up - usually a new format to add."""
    claimed = {p for src in SOURCES for p in src.files(raw_dir)}
    return sorted(p for p in raw_dir.rglob("*")
                  if p.is_file() and not p.name.startswith(".") and p not in claimed
                  and p.relative_to(raw_dir).as_posix() not in METADATA_FILES)


def ingest(raw_dir: Path = RAW_DIR, months=REQUESTED_MONTHS) -> dict[str, pd.DataFrame]:
    for p in unclaimed_files(raw_dir):
        log.warning("no parser for %s (add a module + registry entry)", p.relative_to(raw_dir))
    frames: dict[str, list[pd.DataFrame]] = {t: [] for t in schema.TABLES}
    for src in SOURCES:
        files = src.files(raw_dir)
        if not files:
            log.warning("%s/%s: no files found for %s", src.name, src.table, src.patterns)
        for path in files:
            try:
                df = src.parse(path)
            except Exception:
                log.exception("%s: parser failed, file skipped", path)
                continue
            log.info("%-45s %6d rows", path.relative_to(raw_dir), len(df))
            frames[src.table].append(df)

    tables = {}
    for table, parts in frames.items():
        df = pd.concat(parts, ignore_index=True) if parts else schema.empty(table)
        df = schema.conform(df, table)

        outside = ~df["time_utc"].dt.month.isin(months)
        if outside.any():
            by = df.loc[outside, "source" if table == "observations" else "station_id"].value_counts()
            log.info("%s: dropped %d rows outside months %s: %s", table, int(outside.sum()),
                     months, by.to_dict())
            df = df[~outside]

        if table == "observations":
            empty_rows = df[MEASUREMENTS].isna().all(axis=1)
            if empty_rows.any():
                log.info("observations: dropped %d rows without any measurement", int(empty_rows.sum()))
                df = df[~empty_rows]

        df = schema.coalesce_duplicates(df, table)
        _, key = schema.TABLES[table]
        tables[table] = df.sort_values(key).reset_index(drop=True)
    return tables


def report(tables: dict[str, pd.DataFrame], months) -> bool:
    """Print verification output; return True if all hard checks pass."""
    ok = True
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    obs, tides = tables["observations"], tables["tide_events"]

    print("\n=== observations: per source ===")
    summary = obs.groupby("source").agg(
        rows=("time_utc", "size"), ids=("source_id", "nunique"),
        first=("time_utc", "min"), last=("time_utc", "max"))
    print(summary.to_string())

    print("\n=== observations: % missing per column ===")
    print(obs.drop(columns=["source"]).isna().groupby(obs["source"]).mean().mul(100).round(1)
          [["lat", "lon"] + MEASUREMENTS].to_string())

    print("\n=== observations: rows per source_id ===")
    print(obs.groupby(["source", "source_id"]).size().to_string())

    print("\n=== tide_events ===")
    print(f"rows={len(tides)}  stations={sorted(tides['station_id'].unique())}  "
          f"range={tides['time_utc'].min()} .. {tides['time_utc'].max()}  "
          f"types={tides['type'].value_counts().to_dict()}")

    print("\n=== sanity checks ===")
    checks = {
        "observations schema/range/duplicate validation": schema.validate(obs),
        "tide_events schema/range/duplicate validation": schema.validate(tides, "tide_events"),
    }
    for name, problems in checks.items():
        print(f"[{'OK' if not problems else 'FAIL'}] {name}")
        for p in problems:
            print("       -", p)
        ok &= not problems
    for name, df in (("observations", obs), ("tide_events", tides)):
        bad = int((~df["time_utc"].dt.month.isin(months)).sum())
        print(f"[{'OK' if not bad else 'FAIL'}] {name}: all times in months {months} (bad={bad})")
        ok &= not bad
    for col, (lo, hi) in (("wind_dir_deg", (0, 360)), ("wind_speed_kn", (0, 60))):
        s = obs[col].dropna()
        print(f"     {col}: min={s.min():.1f} max={s.max():.1f} (allowed {lo}..{hi})")

    print("\n=== 5 sample rows per source ===")
    for src, g in obs.groupby("source"):
        print(f"\n-- {src}")
        print(g.sample(min(5, len(g)), random_state=0).sort_values("time_utc").to_string(index=False))
    print("\n-- tide_events")
    print(tides.head(5).to_string(index=False))
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=RAW_DIR)
    ap.add_argument("--out", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--months", default=",".join(map(str, REQUESTED_MONTHS)), help="e.g. 6 or 5,6,7")
    ap.add_argument("--quiet", action="store_true", help="no verification report")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every file")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(levelname)-7s %(name)s: %(message)s")
    months = tuple(int(m) for m in a.months.split(","))

    tables = ingest(a.raw, months)
    a.out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        path = a.out / f"{name}.parquet"
        df.to_parquet(path, index=False)
        print(f"wrote {path}  ({len(df)} rows)")
    if a.quiet:
        return 0
    return 0 if report(tables, months) else 1


if __name__ == "__main__":
    sys.exit(main())
