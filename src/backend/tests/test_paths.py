"""Guards for backend/paths.py, written after a byte-identical duplicate folder was deleted and a
reader that still pointed at it broke two dashboard tabs (the unit tests did not notice)."""

import re

import pytest

from backend import analysis, paths, race_analysis, strategy
from backend.geodata import config as geodata_config
from backend.ingest import config as ingest_config
from backend.race_model import fetch_data, model
from backend.rag.config import load_settings
from backend.retrieval import geolocation

# Folder names that no longer exist (or exist only as locations inside paths.py). If one shows up in
# code outside paths.py, somebody built a data path by hand.
RETIRED_NAMES = ("rag-system", "sailsync_api_results", "geo_data", "conditions_June_2026", "weather_meteo_com",
                 "ey_hackathon", "sea_dashboard.frontend", "frontend.frontend")


def test_every_data_folder_exists_and_has_files():
    for name in ("SAILSYNC_DIR", "GEO_JSON_DIR", "CONDITIONS_RAW_DIR", "CONDITIONS_PROCESSED_DIR",
                 "WEATHER_SAMPLES_DIR", "RACE_MODEL_DIR", "STRATEGY_CORPUS_DIR", "DEMO_UPLOADS_DIR"):
        folder = getattr(paths, name)
        assert folder.is_dir() and any(folder.iterdir()), f"{name} -> {folder} is missing or empty"
    assert paths.GEO_VENUES_FILE.is_file()


def test_sailsync_folder_has_all_44_tracks_and_the_provenance_note():
    assert len(list(paths.SAILSYNC_DIR.rglob("2796_*.csv"))) == 44
    assert (paths.SAILSYNC_DIR / "winners" / "explain.md").is_file()      # where the data came from


def test_every_reader_takes_its_folder_from_paths():
    assert race_analysis.RESULTS == paths.SAILSYNC_DIR
    assert strategy.DATA == paths.CONDITIONS_RAW_DIR
    assert model.DATA == paths.RACE_MODEL_DIR and fetch_data.OUT == paths.RACE_MODEL_DIR
    assert geolocation.GEO_DATA_DIRECTORY == paths.GEO_JSON_DIR
    assert all((geolocation.GEO_DATA_DIRECTORY / name).is_file() for name in geolocation.GEO_DATA_FILES)
    assert ingest_config.RAW_DIR == paths.CONDITIONS_RAW_DIR
    assert ingest_config.PROCESSED_DIR == paths.CONDITIONS_PROCESSED_DIR
    assert ingest_config.EXTERNAL_DIRS["gps_track"] == paths.SAILSYNC_DIR
    assert geodata_config.DATA_DIR == paths.GEO_DIR and geodata_config.VENUES_FILE == paths.GEO_VENUES_FILE
    assert analysis.DEMO_DIR == paths.DEMO_UPLOADS_DIR
    settings = load_settings()
    assert settings.corpus_dir == paths.STRATEGY_CORPUS_DIR and settings.chroma_dir == paths.RAG_INDEX_DIR


def test_layout_is_data_src_docs_at_the_top():
    """Python lives in src/{backend,frontend}; data in data/; documentation in docs/."""
    assert paths.SRC == paths.ROOT / "src"
    for stray in ("backend", "frontend", "tests", "geo_data", "sailsync_api_results", "rag-system", "sea_dashboard"):
        assert not (paths.ROOT / stray).exists(), f"{stray}/ should not be at the repo root"


def test_no_module_builds_a_data_path_by_hand():
    offenders = []
    this_file = __file__
    for source in paths.SRC.rglob("*.py"):
        if source.name == "paths.py" or str(source) == this_file or ".venv" in source.parts:
            continue
        text = source.read_text(encoding="utf-8")
        for name in RETIRED_NAMES:
            if re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", text):
                offenders.append(f"{source.relative_to(paths.ROOT)}: {name}")
    assert not offenders, "retired folder names found outside paths.py:\n" + "\n".join(offenders)


@pytest.mark.parametrize("old", ["data/src", "data/geo_data", "data/sailsync_api_results"])
def test_removed_duplicate_folders_stay_gone(old):
    assert not (paths.ROOT / old).exists(), (
        f"{old}/ is back. It was a byte-identical copy of {old.removeprefix('data/')}/; "
        "two copies let two modules read different data.")
