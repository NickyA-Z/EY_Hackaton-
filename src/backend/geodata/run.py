"""CLI: pull geographic data for a venue and record what was pulled in catalog.json.

    .venv\\Scripts\\python -m geodata.run --list
    .venv\\Scripts\\python -m geodata.run --venue la28
    .venv\\Scripts\\python -m geodata.run --venue la28 --steps terrain      # one dataset only
    .venv\\Scripts\\python -m geodata.run --venue la28 --steps json         # GeoTIFF -> grid JSON only
    .venv\\Scripts\\python -m geodata.run --venue la28 --force              # re-fetch from the APIs
    .venv\\Scripts\\python -m geodata.run --venue cadiz --list-sources
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time

from .catalog import Catalog, DatasetRecord
from .config import load_venues

# step -> ordered candidates (module path, regions it applies to). First that succeeds wins;
# later candidates are fallbacks and get status "fallback".
ALL = {"us", "europe", "global"}
STEPS: dict[str, list[tuple[str, set[str]]]] = {
    # 1. water depth: NOAA NCEI best coastal DEM (API), else ETOPO / EMODnet (API)
    "bathymetry": [("geodata.sources.ncei_dem", ALL), ("geodata.bathy", ALL)],
    # 2. land shape: Copernicus GLO-30 (cloud-optimized GeoTIFF window read)
    "terrain": [("geodata.dem", ALL)],
    # 3. standardized grid JSON of both rasters (local conversion, no network)
    "json": [("geodata.export_json", ALL)],
}


def candidates_for(step: str, region: str) -> list[str]:
    return [m for m, regions in STEPS[step] if region in regions]


def run_step(venue, step: str, force: bool) -> list[DatasetRecord]:
    mods = candidates_for(step, venue.region)
    if not mods:
        return [DatasetRecord(id=step, layer=step, source="-", status="unavailable",
                              notes=f"No source configured for region '{venue.region}'.")]
    failures = []
    for i, modname in enumerate(mods):
        mod = importlib.import_module(modname)
        try:
            recs = mod.pull(venue, force)
        except Exception as exc:
            logging.exception("[%s] %s failed", venue.key, modname)
            failures.append(f"{modname}: {type(exc).__name__}: {exc}")
            continue
        if i < len(mods) - 1 and recs and all(r.status == "unavailable" for r in recs):
            failures.append(f"{modname}: {recs[0].notes or 'unavailable'}")
            continue
        if i > 0 or failures:
            for r in recs:
                if r.status == "ok":
                    r.status = "fallback"
                r.notes = (r.notes + " | " if r.notes else "") + "Primary skipped/failed: " + "; ".join(failures)
        return recs
    return [DatasetRecord(id=step, layer=step, source=" / ".join(mods), status="failed", error=" | ".join(failures))]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--venue", nargs="+", help="venue key(s) from venues.yaml")
    g.add_argument("--all", action="store_true", help="process every venue")
    g.add_argument("--list", action="store_true", help="list venues")
    p.add_argument("--steps", nargs="+", choices=list(STEPS), default=list(STEPS))
    p.add_argument("--force", action="store_true", help="re-download even if cached")
    p.add_argument("--list-sources", action="store_true", help="show which source each step would use")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    venues = load_venues()
    if args.list:
        for k, v in venues.items():
            print(f"{k:12s} {v.region:7s} {v.name}  areas={[a.key for a in v.areas]}")
        return 0

    keys = list(venues) if args.all else args.venue
    unknown = [k for k in keys if k not in venues]
    if unknown:
        p.error(f"unknown venue(s): {unknown}. Known: {list(venues)}")

    if args.list_sources:
        for k in keys:
            v = venues[k]
            print(f"{k} (region={v.region})")
            for s in args.steps:
                print(f"  {s:11s} -> {' then '.join(candidates_for(s, v.region)) or 'none'}")
        return 0

    any_failed = False
    for k in keys:
        v = venues[k]
        cat = Catalog(v)
        logging.info("[%s] region=%s bbox=%s", k, v.region, [round(x, 4) for x in v.area_bbox])
        for step in args.steps:
            t = time.time()
            logging.info("[%s] step %s ...", k, step)
            for r in run_step(v, step, args.force):
                cat.add(r)
                logging.info("[%s]   %-34s %-11s %s", k, r.id, r.status, r.error[:120] if r.error else "")
                any_failed |= r.status == "failed"
            cat.save()
            logging.info("[%s] step %s done in %.0fs", k, step, time.time() - t)
        logging.info("[%s] catalog: %s", k, cat.path)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
