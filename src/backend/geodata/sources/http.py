"""Shared HTTP session and ArcGIS ImageServer export helper."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import BBox

log = logging.getLogger(__name__)

USER_AGENT = "sail-geodata/0.2 (hackathon research project)"


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


SESSION = session()


def get_json(url: str, params: dict | None = None, timeout: int = 120) -> dict:
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _export_block(service: str, params: dict) -> np.ndarray:
    # short, bounded retries: a stuck image server should fail fast, not hang for many minutes
    last = None
    for attempt in range(3):
        try:
            r = requests.get(f"{service}/exportImage", params=params, timeout=(30, 180),
                             headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            if "image" not in r.headers.get("content-type", "") and r.content[:4] not in (b"II*\x00", b"MM\x00*"):
                raise RuntimeError(f"exportImage returned {r.headers.get('content-type')}: {r.text[:300]}")
            with MemoryFile(r.content) as mf, mf.open() as src:
                arr = src.read(1).astype(np.float32)
                nd = src.nodata
            arr[(arr <= -99998) | ((nd is not None) & (arr == nd))] = np.nan
            return arr
        except (requests.RequestException, RuntimeError) as exc:
            last = exc
            log.warning("  block retry %d after %s", attempt + 1, type(exc).__name__)
    raise RuntimeError(f"exportImage failed after 3 attempts: {last}")


def arcgis_export_image(service: str, bbox: BBox, res_deg: float, out: Path,
                        extra: dict | None = None, block: int = 500, workers: int = 6,
                        tags: dict | None = None) -> Path:
    """Export a GeoTIFF (EPSG:4326, float32) for bbox at res_deg from an ArcGIS ImageServer.

    The area is split into blocks of at most `block` pixels per side, fetched in parallel
    and mosaicked - small blocks keep each request fast on busy public servers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    w, s, e, n = bbox
    width = math.ceil((e - w) / res_deg)
    height = math.ceil((n - s) / res_deg)
    transform = from_origin(w, n, res_deg, res_deg)
    full = np.full((height, width), np.nan, dtype=np.float32)

    jobs = {}
    for r0 in range(0, height, block):
        for c0 in range(0, width, block):
            bh, bw = min(block, height - r0), min(block, width - c0)
            bw_, bn_ = w + c0 * res_deg, n - r0 * res_deg
            be_, bs_ = bw_ + bw * res_deg, bn_ - bh * res_deg
            params = {
                "bbox": f"{bw_},{bs_},{be_},{bn_}", "bboxSR": 4326, "imageSR": 4326,
                "size": f"{bw},{bh}", "format": "tiff", "pixelType": "F32",
                "noData": -99999, "noDataInterpretation": "esriNoDataMatchAny",
                "interpolation": "RSP_BilinearInterpolation", "f": "image", **(extra or {}),
            }
            jobs[(r0, c0, bh, bw)] = params
    log.info("  exporting %dx%d px in %d blocks (%d parallel)", width, height, len(jobs), workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_export_block, service, p): k for k, p in jobs.items()}
        for i, fut in enumerate(as_completed(futs), 1):
            r0, c0, bh, bw = futs[fut]
            arr = fut.result()
            arr = arr[:bh, :bw]
            full[r0:r0 + arr.shape[0], c0:c0 + arr.shape[1]] = arr
            log.info("  block %d/%d done", i, len(jobs))

    profile = dict(driver="GTiff", height=height, width=width, count=1, dtype="float32",
                   crs="EPSG:4326", transform=transform, nodata=np.nan,
                   compress="deflate", predictor=3, tiled=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(full, 1)
        if tags:
            dst.update_tags(**{k: (json.dumps(v) if not isinstance(v, str) else v) for k, v in tags.items()})
    return out
