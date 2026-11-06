"""Parse every raw weather file (paths.CONDITIONS_RAW_DIR) into the common model and write parquet tables.

Usage (from the repo root, with src on the path):
  python -m backend.ingest.run              # or: python backend/ingest/run.py
  python -m backend.ingest.run --quiet      # skip the verification report
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):          # allow `python backend/ingest/run.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "backend.ingest"

import pandas as pd

from backend.ingest import schema
from backend.ingest.config import PROCESSED_DIR, RAW_DIR, REQUESTED_MONTHS
from backend.ingest.inbox import load_manifest
from backend.ingest.registry import SOURCES

log = logging.getLogger("ingest.run")
MEASUREMENTS = ["wind_dir_deg", "wind_speed_kn", "wind_gust_kn", "air_temp_c",
                "water_temp_c", "wave_height_m", "cloud_cover_pct"]


# Raw files that are metadata, not data (no parser expected).
METADATA_FILES = {"noaa_coops/stations_nearby.json", "manifest.json"}


def unclaimed_files(raw_dir: Path) -> list[Path]:
    """Raw files no registered parser picks up - usually a new format to add."""
    claimed = {p for src in SOURCES for p in src.files(raw_dir)}
    return sorted(p for p in raw_dir.rglob("*")
                  if p.is_file() and not p.name.startswith(".") and p not in claimed
                  and p.relative_to(raw_dir).as_posix() not in METADATA_FILES)


def ingest(raw_dir: Path = RAW_DIR, months=REQUESTED_MONTHS,
           include_external: bool | None = None) -> dict[str, pd.DataFrame]:
    """Parse all sources. External folders (config.EXTERNAL_DIRS) are read only for the real RAW_DIR."""
    if include_external is None:
        include_external = Path(raw_dir).resolve() == RAW_DIR.resolve()
    for p in unclaimed_files(raw_dir):
        log.warning("no parser for %s (add a module + registry entry)", p.relative_to(raw_dir))
    manifest = load_manifest(raw_dir)
    frames: dict[str, list[pd.DataFrame]] = {t: [] for t in schema.TABLES}
    for src in SOURCES:
        files = src.files(raw_dir, include_external)
        if not files:
            log.warning("%s/%s: no files found for %s", src.name, src.table, src.patterns)
        for path in files:
            try:
                df = src.parse(path)
            except Exception:
                log.exception("%s: parser failed, file skipped", path)
                continue
            rel = path.relative_to(raw_dir).as_posix() if path.is_relative_to(raw_dir) else str(path)
            if "is_sample" in df.columns and manifest.get(rel, {}).get("is_sample"):
                df["is_sample"] = True          # hand-made sample files, flagged at upload
            log.info("%-45s %6d rows", rel, len(df))
            frames[src.table].append(df)

    tables = {}
    for table, parts in frames.items():
        df = pd.concat(parts, ignore_index=True) if parts else schema.empty(table)
        df = schema.conform(df, table)

        outside = ~df["time_utc"].dt.month.isin(months)
        if outside.any():
            by = df.loc[outside, "source" if "source" in df.columns else "station_id"].value_counts()
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


def build(raw_dir: Path = RAW_DIR, out_dir: Path = PROCESSED_DIR,
          months=REQUESTED_MONTHS) -> dict[str, pd.DataFrame]:
    """Ingest everything and write one parquet file per table."""
    tables = ingest(raw_dir, months)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return tables


def report(tables: dict[str, pd.DataFrame], months) -> bool:
    """Print verification output; return True if all hard checks pass."""
    ok = True
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    obs, tides, trk = tables["observations"], tables["tide_events"], tables["tracks"]

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

    print("\n=== tracks ===")
    if trk.empty:
        print("no tracks")
    else:
        per = trk.groupby("track_id").agg(
            sailor=("sailor", "first"), top=("is_top_finisher", "first"), fixes=("time_utc", "size"),
            start=("time_utc", "min"), end=("time_utc", "max"),
            median_kn=("speed_kn", "median"), max_kn=("speed_kn", "max"))
        print(f"tracks={len(per)}  fixes={len(trk)}  top finishers={int(per['top'].sum())}  "
              f"range={trk['time_utc'].min()} .. {trk['time_utc'].max()}  "
              f"speed missing={trk['speed_kn'].isna().mean():.1%}")
        print(per.sort_values("median_kn", ascending=False).head(8).round(2).to_string())

    print("\n=== sanity checks ===")
    checks = {
        "observations schema/range/duplicate validation": schema.validate(obs),
        "tide_events schema/range/duplicate validation": schema.validate(tides, "tide_events"),
        "tracks schema/range/duplicate validation": schema.validate(trk, "tracks"),
    }
    for name, problems in checks.items():
        print(f"[{'OK' if not problems else 'FAIL'}] {name}")
        for p in problems:
            print("       -", p)
        ok &= not problems
    for name, df in (("observations", obs), ("tide_events", tides), ("tracks", trk)):
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

    tables = build(a.raw, a.out, months)
    for name, df in tables.items():
        print(f"wrote {a.out / f'{name}.parquet'}  ({len(df)} rows)")
    if a.quiet:
        return 0
    return 0 if report(tables, months) else 1


if __name__ == "__main__":
    sys.exit(main())
