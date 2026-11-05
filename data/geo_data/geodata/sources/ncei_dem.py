"""Seamless topo-bathymetry: best available NOAA NCEI DEM for the venue.

Uses the NCEI 'DEM_all' ArcGIS ImageServer, which mosaics every NCEI DEM (CUDEM,
regional tsunami / coastal DEMs, Coastal Relief Models, ETOPO). We query which DEMs
cover the venue box, pick the finest one with good coverage, and export just that one
(lock-raster) so the output has a single, known vertical datum and survey vintage.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..catalog import DatasetRecord, inspect_raster
from ..config import Venue, raster_matches
from .http import arcgis_export_image, get_json

log = logging.getLogger(__name__)

SERVICE = "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer"
MIN_COVERAGE = 0.6


def _datum(name: str) -> str:
    n = name.lower()
    for key, label in (("navd", "NAVD88"), ("mhw", "MHW"), ("mllw", "MLLW"), ("msl", "MSL"), ("egm", "EGM2008")):
        if key in n:
            return label
    return "see NCEI metadata (often NAVD88 or MHW)"


def candidates(venue: Venue) -> list[dict]:
    w, s, e, n = venue.bathy_bbox
    q = get_json(f"{SERVICE}/query", params={
        "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outSR": 4326, "returnGeometry": "true",
        "outFields": "OBJECTID,Name,CellsizeArcseconds,DateCompleted", "f": "json",
    })
    target = box(w, s, e, n)
    out = []
    for f in q.get("features", []):
        a = f["attributes"]
        rings = (f.get("geometry") or {}).get("rings") or []
        polys = [Polygon(r) for r in rings if len(r) >= 4]
        foot = unary_union([p.buffer(0) for p in polys]) if polys else target
        cov = foot.intersection(target).area / target.area
        done = a.get("DateCompleted")
        out.append({
            "oid": a["OBJECTID"], "name": a["Name"], "cellsize_arcsec": a["CellsizeArcseconds"],
            "date_completed": datetime.fromtimestamp(done / 1000, timezone.utc).date().isoformat() if done else None,
            "coverage": round(cov, 3), "vertical_datum": _datum(a["Name"]),
        })
    return out


def _rank(c: dict):
    # finest resolution first; prefer an orthometric datum (NAVD88) over tidal (MHW); newest first
    return (round(c["cellsize_arcsec"], 2), 0 if c["vertical_datum"] == "NAVD88" else 1,
            -(int(c["date_completed"][:4]) if c["date_completed"] else 0))


def pull(venue: Venue, force: bool = False) -> list[DatasetRecord]:
    out = venue.out_dir / "bathymetry_ncei.tif"
    meta_path = out.with_suffix(".meta.json")  # which DEM was chosen, so cached re-runs need no network
    cached = not force and meta_path.exists() and raster_matches(out, venue.bathy_bbox)
    if cached:
        meta = json.loads(meta_path.read_text())
        cands, usable = meta["candidates"], [meta["selected"]]
    else:
        cands = candidates(venue)
        usable = sorted([c for c in cands if c["coverage"] >= MIN_COVERAGE and not c["name"].startswith("ETOPO")],
                        key=_rank)
    rec = DatasetRecord(
        id="bathymetry_ncei", layer="bathymetry", source="NOAA NCEI best-available coastal DEM (topo-bathy)",
        provider="NOAA NCEI", url=SERVICE, access="API (ArcGIS ImageServer exportImage by bbox -> GeoTIFF; getSamples for single points; no key)", license="US Government public domain", kind="static",
        crs="EPSG:4326", refresh="Static; NCEI publishes new DEMs / CUDEM tiles every few years",
    )
    rec.stats["candidates"] = sorted(cands, key=_rank)
    if not usable:
        rec.status = "unavailable"
        rec.notes = "Only global ETOPO covers this venue; falling back to ETOPO / EMODnet."
        return [rec]

    best = usable[0]
    res_deg = best["cellsize_arcsec"] / 3600
    rec.source += f": {best['name']}"
    rec.vertical_datum = best["vertical_datum"]
    rec.resolution = f"{best['cellsize_arcsec']:.2f} arc-second (~{best['cellsize_arcsec'] * 30.87:.0f} m)"
    rec.time_coverage = f"DEM completed {best['date_completed']} (survey data from earlier years)"
    rec.bbox = list(venue.bathy_bbox)
    rec.files = [out]
    rec.notes = (f"Coverage of analysis box {best['coverage'] * 100:.0f}%. Negative = below the vertical datum. "
                 "Not for navigation (use official nautical charts).")

    if not cached:
        log.info("bathymetry: exporting %s at %.2f arcsec", best["name"], best["cellsize_arcsec"])
        arcgis_export_image(
            SERVICE, venue.bathy_bbox, res_deg, out,
            extra={"mosaicRule": '{"mosaicMethod":"esriMosaicLockRaster","lockRasterIds":[%d]}' % best["oid"]},
            tags={"source": best["name"], "vertical_datum": best["vertical_datum"]},
        )
    if not cached:
        meta_path.write_text(json.dumps({"selected": best, "candidates": cands}, indent=2))
    rec.stats.update(inspect_raster(out, venue))
    return [rec]
