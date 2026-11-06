"""Venue configuration: loads venues.yaml and derives bounding boxes / paths.

A venue has one or more race *areas* (circles). Data is pulled once for a box that
covers every area plus a buffer, so a venue with candidate course areas (e.g. LA28)
and a single-point home venue are handled the same way.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backend import paths

DATA_DIR = paths.GEO_DIR
VENUES_FILE = paths.GEO_VENUES_FILE

BBox = tuple[float, float, float, float]  # (west, south, east, north) in degrees

REGIONS: dict[str, BBox] = {
    # checked in order; first region that fully contains the venue box wins
    "us": (-125.0, 24.0, -66.0, 50.0),          # contiguous US (NOAA / USGS sources)
    "europe": (-36.0, 15.0, 43.0, 90.0),        # EMODnet coverage
}


def bbox_around(lat: float, lon: float, half_km: float) -> BBox:
    dlat = half_km / 111.32
    dlon = half_km / (111.32 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def union(boxes: list[BBox]) -> BBox:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def expand(b: BBox, km: float) -> BBox:
    lat = (b[1] + b[3]) / 2
    dlat = km / 111.32
    dlon = km / (111.32 * math.cos(math.radians(lat)))
    return (b[0] - dlon, b[1] - dlat, b[2] + dlon, b[3] + dlat)


def contains(outer: BBox, inner: BBox) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


@dataclass
class Area:
    key: str
    lat: float
    lon: float
    radius_km: float = 1.5
    events: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def bbox(self) -> BBox:
        return bbox_around(self.lat, self.lon, self.radius_km)


@dataclass
class Venue:
    key: str
    name: str
    areas: list[Area]
    buffer_km: float = 10.0          # terrain box around the areas (upwind hills)
    bathy_km: float = 2.0            # bathymetry box around the areas (depth matters near the course)
    notes: str = ""

    # ---- geometry ---------------------------------------------------------------
    @property
    def areas_bbox(self) -> BBox:
        return union([a.bbox for a in self.areas])

    @property
    def area_bbox(self) -> BBox:
        """Wide analysis box: all race areas + buffer (upwind terrain, approaches)."""
        return expand(self.areas_bbox, self.buffer_km)

    @property
    def bathy_bbox(self) -> BBox:
        return expand(self.areas_bbox, self.bathy_km)

    @property
    def lat(self) -> float:
        b = self.areas_bbox
        return (b[1] + b[3]) / 2

    @property
    def lon(self) -> float:
        b = self.areas_bbox
        return (b[0] + b[2]) / 2

    @property
    def region(self) -> str:
        for name, box in REGIONS.items():
            if contains(box, self.area_bbox):
                return name
        return "global"

    # ---- paths ------------------------------------------------------------------
    @property
    def out_dir(self) -> Path:
        p = DATA_DIR / self.key
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def raw_dir(self) -> Path:
        p = self.out_dir / "raw"
        p.mkdir(parents=True, exist_ok=True)
        return p


def _venue_from_cfg(key: str, cfg: dict) -> Venue:
    cfg = dict(cfg)
    if "areas" in cfg:
        areas = [Area(key=k, **v) for k, v in cfg.pop("areas").items()]
    else:  # short form: a single race area given by lat/lon
        areas = [Area(key="main", lat=cfg.pop("lat"), lon=cfg.pop("lon"),
                      radius_km=cfg.pop("race_radius_km", 1.5))]
    return Venue(key=key, areas=areas, **cfg)


def raster_matches(path: Path, bbox: BBox, tol_cells: float = 2.0) -> bool:
    """True if a saved raster still covers `bbox` (edges within `tol_cells` cells).

    Used to decide whether a cached file can be reused or must be re-fetched because the
    race areas in venues.yaml changed.
    """
    import rasterio

    if not path.exists():
        return False
    with rasterio.open(path) as src:
        b, (rx, ry) = src.bounds, src.res
    return (abs(b.left - bbox[0]) <= tol_cells * rx and abs(b.bottom - bbox[1]) <= tol_cells * ry
            and abs(b.right - bbox[2]) <= tol_cells * rx and abs(b.top - bbox[3]) <= tol_cells * ry)


def load_venues(path: Path = VENUES_FILE) -> dict[str, Venue]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {key: _venue_from_cfg(key, vals) for key, vals in cfg["venues"].items()}
