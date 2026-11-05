"""Dataset catalog: one record per pulled dataset, with automatic inspection stats.

data/<venue>/catalog.json is the machine-readable answer to "what did we pull and what
does it contain" - for the team, the other workstreams and the AI agent.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import Venue


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class DatasetRecord:
    id: str                         # unique within the venue, e.g. "bathymetry_ncei", "json_terrain"
    layer: str                      # bathymetry | terrain
    source: str                     # human-readable source name
    provider: str = ""
    url: str = ""
    access: str = ""                # how it was obtained: API call, cloud-file window read, local conversion
    license: str = ""
    kind: str = "static"            # static (no time dimension) for both current datasets
    status: str = "ok"              # ok | fallback | unavailable | failed
    files: list[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=now_utc)
    crs: str = ""
    vertical_datum: str = ""
    resolution: str = ""
    bbox: list[float] | None = None
    time_coverage: str = ""
    refresh: str = ""               # how often the source changes / can be re-pulled
    notes: str = ""
    error: str = ""
    stats: dict = field(default_factory=dict)


class Catalog:
    def __init__(self, venue: Venue):
        self.venue = venue
        self.path = venue.out_dir / "catalog.json"
        self.records: dict[str, dict] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = {r["id"]: r for r in data.get("datasets", [])}

    def add(self, rec: DatasetRecord) -> None:
        d = asdict(rec)
        d["files"] = [_rel(self.venue, f) for f in rec.files]
        self.records[rec.id] = _clean(d)

    def save(self) -> Path:
        v = self.venue
        doc = {
            "venue": {
                "key": v.key, "name": v.name, "region": v.region, "notes": v.notes,
                "analysis_bbox": [round(x, 5) for x in v.area_bbox],
                "areas": [
                    {"key": a.key, "lat": a.lat, "lon": a.lon, "radius_km": a.radius_km,
                     "events": a.events, "notes": a.notes}
                    for a in v.areas
                ],
            },
            "updated_at": now_utc(),
            "datasets": sorted(self.records.values(), key=lambda r: (r["layer"], r["id"])),
        }
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.path


def _rel(venue: Venue, f) -> str:
    p = Path(f)
    try:
        return p.relative_to(venue.out_dir).as_posix()
    except ValueError:
        return p.as_posix()


def _clean(o):
    """Make numpy / NaN values JSON-safe."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, datetime):
        return o.isoformat()
    return o


# ---- inspection helpers -----------------------------------------------------------

def inspect_raster(path: Path, venue: Venue) -> dict:
    import rasterio
    from pyproj import Transformer

    with rasterio.open(path) as src:
        data = src.read(1, masked=True).astype("float64")
        if src.nodata is None or (isinstance(src.nodata, float) and math.isnan(src.nodata)):
            data = np.ma.masked_invalid(data)
        valid = data.compressed()
        res_x, res_y = src.res
        if src.crs and src.crs.is_geographic:
            lat = (src.bounds.bottom + src.bounds.top) / 2
            res_m = f"{res_x * 111320 * math.cos(math.radians(lat)):.1f} m x {res_y * 110540:.1f} m"
        else:
            res_m = f"{res_x:.1f} x {res_y:.1f} (CRS units)"
        tr = Transformer.from_crs(4326, src.crs, always_xy=True)
        samples = {}
        for a in venue.areas:
            x, y = tr.transform(a.lon, a.lat)
            try:
                r, c = src.index(x, y)
                v = data[r, c]
                samples[a.key] = None if v is np.ma.masked else round(float(v), 2)
            except IndexError:
                samples[a.key] = None
        stats = {
            "width": src.width, "height": src.height, "crs": str(src.crs),
            "pixel_size": res_m, "dtype": src.dtypes[0],
            "valid_pct": round(100 * valid.size / data.size, 1) if data.size else 0,
            "value_at_area_centers": samples,
        }
        if valid.size:
            stats.update(min=float(valid.min()), max=float(valid.max()), mean=float(valid.mean()),
                         p05=float(np.percentile(valid, 5)), p95=float(np.percentile(valid, 95)))
        return stats
