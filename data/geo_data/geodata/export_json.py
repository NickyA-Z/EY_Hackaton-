"""Convert the saved GeoTIFFs into standardized "grid JSON" files (no network, no AI).

Reads each raster's grid of numbers and georeferencing with rasterio and writes the same
numbers (rounded to 0.1 m, native resolution) into data/<venue>/json/<dataset>.json:

    {
      "schema": "sail-geodata/grid-json v1",
      "dataset": "bathymetry", "venue": "la28", "source": ..., "link": ..., ...
      "grid": {"west", "north", "south", "east", "step_deg", "rows", "cols", "order"},
      "stats": {...},
      "values": [[row 0: west -> east], [row 1], ...]      # rows run north -> south
    }

Cell center of values[r][c]:  lat = north - (r + 0.5) * step_deg,  lon = west + (c + 0.5) * step_deg
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import rasterio

from .catalog import DatasetRecord, now_utc
from .config import Venue

log = logging.getLogger(__name__)

SCHEMA = "sail-geodata/grid-json v1"
DECIMALS = 1

# dataset name -> catalog record ids that can provide it (first one present wins)
DATASETS = {
    "bathymetry": ["bathymetry_ncei", "bathymetry_emodnet", "bathymetry_etopo"],
    "terrain": ["terrain_copernicus"],
}
VALUE_DESC = {
    "bathymetry": "elevation_m, positive up (negative = water depth below the vertical datum)",
    "terrain": "elevation_m, positive up (land surface incl. buildings/trees; sea = 0)",
}


def _source_record(venue: Venue, ids: list[str]) -> dict | None:
    path = venue.out_dir / "catalog.json"
    if not path.exists():
        return None
    recs = {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["datasets"]}
    for i in ids:
        r = recs.get(i)
        if r and r["status"] in ("ok", "fallback") and r["files"]:
            return r
    return None


def _stats(arr: np.ndarray, src, venue: Venue) -> dict:
    valid = arr[~np.isnan(arr)]
    centers = {}
    for a in venue.areas:
        try:
            r, c = src.index(a.lon, a.lat)
            v = arr[r, c]
            centers[a.key] = None if np.isnan(v) else round(float(v), DECIMALS)
        except IndexError:
            centers[a.key] = None
    return {
        "cells": int(arr.size), "missing_cells": int(arr.size - valid.size),
        "min": round(float(valid.min()), DECIMALS), "max": round(float(valid.max()), DECIMALS),
        "mean": round(float(valid.mean()), DECIMALS),
        "below_zero_pct": round(float((valid < 0).mean() * 100), 1),
        "value_at_area_centers": centers,
    }


def write_grid_json(tif: Path, out: Path, header: dict, venue: Venue) -> dict:
    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float64")
        if src.nodata is not None and not np.isnan(src.nodata):
            arr[arr == src.nodata] = np.nan
        b, (sx, sy) = src.bounds, src.res
        if abs(sx - sy) > 1e-12 or not src.crs.is_geographic:
            raise ValueError(f"{tif.name}: expected square cells in a lat/lon CRS")
        grid = {
            "west": round(b.left, 7), "north": round(b.top, 7), "south": round(b.bottom, 7),
            "east": round(b.right, 7), "step_deg": round(sx, 10), "rows": src.height, "cols": src.width,
            "order": "row-major; rows north->south, columns west->east; values at cell centers",
        }
        stats = _stats(arr, src, venue)
        crs = src.crs.to_string()

    doc = {
        "schema": SCHEMA, **header, "crs": crs, "units": "m", "nodata": None,
        "cell_center_formula": "lat = north - (r + 0.5) * step_deg; lon = west + (c + 0.5) * step_deg",
        "grid": grid,
        "areas": [{"key": a.key, "lat": a.lat, "lon": a.lon, "radius_km": a.radius_km, "events": a.events}
                  for a in venue.areas],
        "stats": stats,
    }
    rounded = np.round(arr, DECIMALS)
    out.parent.mkdir(parents=True, exist_ok=True)
    head = json.dumps(doc, indent=2, ensure_ascii=False)[:-2]  # drop closing "\n}"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + ',\n  "values": [\n')
        last = rounded.shape[0] - 1
        for i, row in enumerate(rounded):
            vals = [None if np.isnan(v) else v for v in row.tolist()]
            f.write("    " + json.dumps(vals, separators=(",", ":")) + (",\n" if i < last else "\n"))
        f.write("  ]\n}\n")
    return {"grid": grid, "stats": stats, "size_mb": round(out.stat().st_size / 1e6, 2)}


def pull(venue: Venue, force: bool = False) -> list[DatasetRecord]:
    recs = []
    for name, ids in DATASETS.items():
        src_rec = _source_record(venue, ids)
        if src_rec is None:
            recs.append(DatasetRecord(id=f"json_{name}", layer=name, source="grid JSON export", status="failed",
                                      error=f"No pulled {name} raster in catalog.json; run --steps {name} first"))
            continue
        tif = venue.out_dir / src_rec["files"][0]
        out = venue.out_dir / "json" / f"{name}.json"
        header = {
            "dataset": name, "venue": venue.key, "venue_name": venue.name,
            "source": src_rec["source"], "provider": src_rec["provider"], "link": src_rec["url"],
            "access": src_rec.get("access", ""), "license": src_rec["license"],
            "data_date": src_rec.get("time_coverage", ""), "extracted_at": now_utc(),
            "converted_from": tif.name, "vertical_datum": src_rec["vertical_datum"],
            "resolution": src_rec["resolution"], "value": VALUE_DESC[name],
        }
        if out.exists() and not force and out.stat().st_mtime >= tif.stat().st_mtime:
            info = {"size_mb": round(out.stat().st_size / 1e6, 2), "note": "up to date, not rewritten"}
        else:
            log.info("json: writing %s from %s", out.name, tif.name)
            info = write_grid_json(tif, out, header, venue)
        recs.append(DatasetRecord(
            id=f"json_{name}", layer=name, source=f"Grid JSON export of {src_rec['id']}",
            provider="this pipeline (rasterio -> JSON, deterministic)", access="local conversion, no network",
            kind="static", files=[out], crs="EPSG:4326", vertical_datum=src_rec["vertical_datum"],
            resolution=src_rec["resolution"] + " (native, not resampled)", time_coverage=src_rec.get("time_coverage", ""),
            notes=f"Schema {SCHEMA}; values rounded to 0.1 m; null = missing.", stats=info))
    return recs
