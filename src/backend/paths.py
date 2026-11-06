"""Where the data lives. The one place that knows folder locations.

Every module that reads or writes data imports its folder from here (the ingest, geodata and RAG
packages included), so moving a dataset is a one-line edit plus a `git mv`, and two modules can
never read two different copies of the same data.
tests/test_paths.py checks that these folders exist and that nothing builds its own data path.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent  # <repo>/src
ROOT = SRC.parent  # <repo>

# SailSync GPS tracks (ILCA 7, San Pedro OCR, 19 July 2026) plus the API probe report.
SAILSYNC_DIR = ROOT / "sailsync_api_results"

# Bathymetry and terrain of the LA28 venue (GeoTIFF + grid JSON), one folder per venue, and the
# venue list that backend/geodata reads.
GEO_DIR = ROOT / "geo_data" / "data"
GEO_VENUES_FILE = ROOT / "geo_data" / "venues.yaml"
GEO_JSON_DIR = GEO_DIR / "la28" / "json"

# Weather: raw files written by backend/ingest (and backend/scripts/fetch_long_beach_data.py), the
# parquet tables built from them, and a few one-off Open-Meteo marine downloads.
CONDITIONS_DIR = SRC / "conditions_June_2026" / "data"
CONDITIONS_RAW_DIR = CONDITIONS_DIR / "raw"
CONDITIONS_PROCESSED_DIR = CONDITIONS_DIR / "processed"
WEATHER_SAMPLES_DIR = SRC / "weather_meteo_com"

# What backend/race_model/fetch_data.py downloads (results, mark roundings, a few GPS tracks).
RACE_MODEL_DIR = ROOT / "data" / "race_model"

# The (synthetic) team-strategy documents the RAG indexes.
STRATEGY_CORPUS_DIR = ROOT / "rag-system"

# Sample coach uploads (notes, transcripts, sailing instructions) for the demo.
DEMO_UPLOADS_DIR = SRC / "backend" / "analysis" / "demo"

# Derived search index of the strategy corpus; rebuilt by `python -m backend.rag index`, not tracked.
RAG_INDEX_DIR = ROOT / ".chroma"
