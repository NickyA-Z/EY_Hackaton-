"""Where the data lives. The one place that knows folder locations.

Every module that reads or writes data imports its folder from here (the ingest, geodata and RAG
packages included), so moving a dataset is a one-line edit plus a `git mv`, and two modules can
never read two different copies of the same data.
tests/test_paths.py checks that these folders exist and that nothing builds its own data path.

Layout (see docs/data.md):  data/{rag, trajectories, weather, geo, race_model, demo_uploads}
"""

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent  # <repo>/src
ROOT = SRC.parent  # <repo>
DATA_DIR = ROOT / "data"

# The (synthetic) team-strategy documents the RAG indexes.
STRATEGY_CORPUS_DIR = DATA_DIR / "rag"

# Derived search index of that corpus; rebuilt by `python -m backend.rag index`, not tracked.
RAG_INDEX_DIR = ROOT / ".chroma"

# SailSync GPS tracks (ILCA 7, San Pedro OCR, 19 July 2026) plus the API probe report.
SAILSYNC_DIR = DATA_DIR / "trajectories" / "sailsync"

# What backend/race_model/fetch_data.py downloads (results, mark roundings, a few GPS tracks).
RACE_MODEL_DIR = DATA_DIR / "race_model"

# Weather: raw files written by backend/ingest (and backend/scripts/fetch_long_beach_data.py), the
# parquet tables built from them, and a few one-off Open-Meteo marine downloads.
WEATHER_DIR = DATA_DIR / "weather"
CONDITIONS_RAW_DIR = WEATHER_DIR / "raw"
CONDITIONS_PROCESSED_DIR = WEATHER_DIR / "processed"
WEATHER_SAMPLES_DIR = WEATHER_DIR / "samples"

# Bathymetry and terrain of the venues (GeoTIFF + grid JSON), one folder per venue, and the venue
# list that backend/geodata reads.
GEO_DIR = DATA_DIR / "geo"
GEO_VENUES_FILE = GEO_DIR / "venues.yaml"
GEO_JSON_DIR = GEO_DIR / "la28" / "json"

# Sample coach uploads (notes, transcripts, sailing instructions) for the demo.
DEMO_UPLOADS_DIR = DATA_DIR / "demo_uploads"
