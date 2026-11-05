"""Bathymetry fallback for venues without a NOAA coastal DEM (i.e. outside the US).

NOAA ETOPO 2022 (~450 m, global) is always pulled; EMODnet (~115 m) is added for European
venues. Outputs bathymetry_etopo.tif / bathymetry_emodnet.tif: elevation in metres,
negative = below sea level.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_origin

from .config import REGIONS, Venue, contains, raster_matches
from .sources.http import SESSION

log = logging.getLogger(__name__)

ETOPO_URL = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.nc"
EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"


def _in_europe(venue: Venue) -> bool:
    return contains(REGIONS["europe"], venue.bathy_bbox)


def fetch_etopo(venue: Venue, force: bool = False) -> Path:
    out = venue.out_dir / "bathymetry_etopo.tif"
    if not force and raster_matches(out, venue.bathy_bbox):
        return out
    w, s, e, n = venue.bathy_bbox
    url = f"{ETOPO_URL}?z[({s:.5f}):1:({n:.5f})][({w:.5f}):1:({e:.5f})]"
    log.info("bathymetry: downloading ETOPO 2022 subset from NOAA ERDDAP")
    r = SESSION.get(url, timeout=300)
    r.raise_for_status()
    raw = venue.raw_dir / "etopo_2022_15s.nc"
    raw.write_bytes(r.content)

    with xr.open_dataset(raw) as ds:
        z = ds["z"].sortby("latitude", ascending=False).sortby("longitude")
        lats, lons = z["latitude"].values, z["longitude"].values
        data = z.values.astype(np.float32)
    res_x = float(abs(lons[1] - lons[0]))
    res_y = float(abs(lats[1] - lats[0]))
    transform = from_origin(lons.min() - res_x / 2, lats.max() + res_y / 2, res_x, res_y)
    _write(out, data, transform, "NOAA ETOPO 2022 15 arc-second (~450 m)")
    return out


def fetch_emodnet(venue: Venue, force: bool = False) -> Path | None:
    out = venue.out_dir / "bathymetry_emodnet.tif"
    if not force and raster_matches(out, venue.bathy_bbox):
        return out
    if not _in_europe(venue):
        return None
    w, s, e, n = venue.bathy_bbox
    params = dict(
        service="WCS", version="1.0.0", request="GetCoverage", coverage="emodnet:mean",
        crs="EPSG:4326", bbox=f"{w},{s},{e},{n}", format="image/tiff",
        resx=1 / 960, resy=1 / 960,
    )
    log.info("bathymetry: downloading EMODnet DTM subset")
    try:
        r = SESSION.get(EMODNET_WCS, params=params, timeout=300)
        r.raise_for_status()
        if "tiff" not in r.headers.get("content-type", ""):
            raise ValueError(f"unexpected response: {r.text[:200]}")
    except Exception as exc:  # network / service errors -> fall back to ETOPO
        log.warning("bathymetry: EMODnet unavailable (%s); using ETOPO only", exc)
        return None
    raw = venue.raw_dir / "emodnet_mean.tif"
    raw.write_bytes(r.content)
    with rasterio.open(raw) as src:
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        _write(out, data, src.transform, "EMODnet Bathymetry DTM (~115 m)", crs=src.crs)
    return out


def _write(path: Path, data: np.ndarray, transform, source: str, crs="EPSG:4326") -> None:
    profile = dict(
        driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
        dtype="float32", crs=crs, transform=transform, nodata=np.nan, compress="deflate",
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(source=source, units="m, negative below sea level")
    log.info("bathymetry: wrote %s (%s)", path.name, source)


def pull(venue: Venue, force: bool = False):
    from .catalog import DatasetRecord, inspect_raster

    recs = []
    etopo = fetch_etopo(venue, force)
    recs.append(DatasetRecord(
        id="bathymetry_etopo", layer="bathymetry", source="NOAA ETOPO 2022 15 arc-second (global)",
        provider="NOAA NCEI via CoastWatch ERDDAP", url=ETOPO_URL, access="API (ERDDAP griddap subset by bbox -> NetCDF; no key)", license="US Government public domain",
        kind="static", crs="EPSG:4326", vertical_datum="EGM2008 (~MSL)", resolution="15 arc-second (~450 m)",
        bbox=list(venue.bathy_bbox), files=[etopo], time_coverage="2022 compilation", refresh="Static",
        notes="Global baseline; too coarse for harbours (used only where no NOAA coastal DEM exists).",
        stats=inspect_raster(etopo, venue)))
    if _in_europe(venue):
        emod = fetch_emodnet(venue, force)
        rec = DatasetRecord(
            id="bathymetry_emodnet", layer="bathymetry", source="EMODnet Bathymetry DTM (mean depth)",
            provider="EMODnet", url=EMODNET_WCS, access="API (OGC WCS GetCoverage by bbox -> GeoTIFF; no key)", license="CC BY 4.0", kind="static", crs="EPSG:4326",
            vertical_datum="LAT (~chart datum)", resolution="1/16 arc-minute (~115 m)",
            bbox=list(venue.bathy_bbox), refresh="New DTM release every ~2 years")
        if emod:
            rec.files, rec.stats = [emod], inspect_raster(emod, venue)
        else:
            rec.status, rec.error = "failed", "EMODnet WCS request failed (see log)"
        recs.append(rec)
    return recs
