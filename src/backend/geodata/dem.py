"""Terrain: Copernicus GLO-30 DSM (30 m) from the public AWS Open Data bucket.

Note: Copernicus GLO-30 is a *surface* model, so it already includes some
buildings and tree canopy. Sea pixels are ~0 m.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.merge import merge

from .config import BBox, Venue, raster_matches

log = logging.getLogger(__name__)

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"

GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    AWS_NO_SIGN_REQUEST="YES",
    GDAL_HTTP_MAX_RETRY="3",
    GDAL_HTTP_RETRY_DELAY="2",
)


def tile_name(lat_floor: int, lon_floor: int) -> str:
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"


def tiles_for_bbox(bbox: BBox) -> list[str]:
    w, s, e, n = bbox
    return [
        tile_name(lat, lon)
        for lat in range(math.floor(s), math.floor(n) + 1)
        for lon in range(math.floor(w), math.floor(e) + 1)
    ]


def fetch_dem(venue: Venue, force: bool = False) -> Path:
    out = venue.out_dir / "terrain.tif"
    if not force and raster_matches(out, venue.area_bbox):
        log.info("terrain: cached %s", out)
        return out

    with rasterio.Env(**GDAL_ENV):
        sources = []
        for name in tiles_for_bbox(venue.area_bbox):
            url = f"/vsicurl/{BASE_URL}/{name}/{name}.tif"
            try:
                sources.append(rasterio.open(url))
                log.info("terrain: using tile %s", name)
            except RasterioIOError:
                # Tiles that are entirely ocean do not exist in the bucket.
                log.info("terrain: no tile %s (open ocean)", name)
        if not sources:
            raise RuntimeError("No Copernicus DEM tiles cover this venue")

        mosaic, transform = merge(sources, bounds=venue.area_bbox, nodata=0)
        crs = sources[0].crs
        for src in sources:
            src.close()

    data = mosaic[0].astype(np.float32)
    profile = dict(
        driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
        dtype="float32", crs=crs, transform=transform, nodata=None,
        compress="deflate", tiled=True,
    )
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(source="Copernicus GLO-30 DSM (ESA), via AWS Open Data", units="m above EGM2008")
    log.info("terrain: wrote %s (%dx%d, max %.0f m)", out.name, data.shape[1], data.shape[0], float(data.max()))
    return out


def pull(venue: Venue, force: bool = False):
    from .catalog import DatasetRecord, inspect_raster

    out = fetch_dem(venue, force)
    return [DatasetRecord(
        id="terrain_copernicus", layer="terrain", source="Copernicus GLO-30 DSM",
        provider="ESA / Airbus, via AWS Open Data", url=BASE_URL,
        access="Cloud file window read (Cloud-Optimized GeoTIFF on AWS S3, HTTP range requests; no key)",
        license="Copernicus DEM licence (free, attribution)", kind="static", crs="EPSG:4326",
        vertical_datum="EGM2008", resolution="1 arc-second (~30 m)", bbox=list(venue.area_bbox),
        files=[out], time_coverage="TanDEM-X acquisitions 2011-2015", refresh="Static",
        notes="Surface model: includes buildings and tree canopy. Sea = 0 m.",
        stats=inspect_raster(out, venue),
    )]
