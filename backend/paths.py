"""Where the data lives. The one place that knows folder locations.

Every backend module imports its data folder from here, so moving a dataset is a one-line edit
(plus a `git mv`) and two modules can never read two different copies of the same data.
tests/test_paths.py checks that these folders exist, that the ingest package agrees with them,
and that the old duplicate folders do not come back.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# SailSync GPS tracks (ILCA 7, San Pedro OCR, 19 July 2026) plus the API probe report.
SAILSYNC_DIR = ROOT / "sailsync_api_results"

# Bathymetry and terrain of the LA28 venue as grid JSON (geo_data/ also holds the scripts that make them).
GEO_JSON_DIR = ROOT / "geo_data" / "data" / "la28" / "json"

# Raw weather / tide / buoy files written by the ingest package and read by backend/strategy.py.
CONDITIONS_RAW_DIR = ROOT / "src" / "conditions_June_2026" / "data" / "raw"

# What backend/race_model/fetch_data.py downloads (results, mark roundings, a few GPS tracks).
RACE_MODEL_DIR = ROOT / "data" / "race_model"

# The (synthetic) team-strategy documents the RAG indexes.
STRATEGY_CORPUS_DIR = ROOT / "rag-system"
