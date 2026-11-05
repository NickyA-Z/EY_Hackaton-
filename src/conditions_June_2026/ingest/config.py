"""Static configuration: paths, demo months and station coordinates.

Coordinates were looked up once (2026-11-05) and hard-coded so that ingest
runs offline:
  - METAR LGB:  IEM network CA_ASOS geojson
  - CO-OPS:     api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{id}.json
  - NDBC:       www.ndbc.noaa.gov/station_page.php?station={id}
Open-Meteo files carry their own (grid-snapped) coordinates, so they are not listed.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPO_ROOT = BASE_DIR.parent.parent

# Data that lives outside data/raw and is read in place (no copies).
# Only used when ingesting the real RAW_DIR, never for test folders.
EXTERNAL_DIRS = {
    "gps_track": REPO_ROOT / "sailsync_api_results",   # SailSync ILCA 7 tracks, 19 Jul 2026
}

# Months (1-12) the demo covers; rows outside these UTC months are dropped in run.py.
REQUESTED_MONTHS = (6, 7)

# (lat, lon) per source -> source_id
STATIONS = {
    "metar": {
        "LGB": (33.8118, -118.1472),  # Long Beach Airport ASOS
    },
    "coops": {
        "9410660": (33.7200, -118.2720),  # Los Angeles (tide predictions)
        "9410665": (33.7330, -118.1857),  # Long Beach Pier J
        "9410670": (33.7463, -118.2156),  # Long Beach Pier F
        "9410692": (33.7683, -118.2257),  # Long Beach Pier S
    },
    "ndbc": {
        "46025": (33.765, -119.077),  # Santa Monica Basin
        "46222": (33.614, -118.314),  # San Pedro (CDIP wave buoy)
    },
}


def station_coords(source: str, source_id: str) -> tuple[float, float]:
    """Return (lat, lon) for a known station, or (NaN, NaN) if unknown."""
    return STATIONS.get(source, {}).get(source_id, (float("nan"), float("nan")))
