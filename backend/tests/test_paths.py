"""Guards for backend/paths.py, written after a byte-identical duplicate folder was deleted and a
reader that still pointed at it broke two dashboard tabs (the unit tests did not notice)."""

import pytest

from backend import paths, race_analysis, strategy
from backend.race_model import fetch_data, model
from backend.retrieval import geolocation


def test_every_data_folder_exists_and_has_files():
    for name in ("SAILSYNC_DIR", "GEO_JSON_DIR", "CONDITIONS_RAW_DIR", "RACE_MODEL_DIR", "STRATEGY_CORPUS_DIR"):
        folder = getattr(paths, name)
        assert folder.is_dir() and any(folder.iterdir()), f"{name} -> {folder} is missing or empty"


def test_sailsync_folder_has_all_44_tracks_and_the_provenance_note():
    assert len(list(paths.SAILSYNC_DIR.rglob("2796_*.csv"))) == 44
    assert (paths.SAILSYNC_DIR / "winners" / "explain.md").is_file()      # where the data came from


def test_every_reader_takes_its_folder_from_paths():
    assert race_analysis.RESULTS == paths.SAILSYNC_DIR
    assert strategy.DATA == paths.CONDITIONS_RAW_DIR
    assert model.DATA == paths.RACE_MODEL_DIR and fetch_data.OUT == paths.RACE_MODEL_DIR
    assert geolocation.GEO_DATA_DIRECTORY == paths.GEO_JSON_DIR
    assert all((geolocation.GEO_DATA_DIRECTORY / name).is_file() for name in geolocation.GEO_DATA_FILES)


def test_ingest_package_reads_the_same_sailsync_folder(monkeypatch):
    """src/conditions_June_2026 is a standalone package, so it keeps its own constant; it must agree."""
    monkeypatch.syspath_prepend(str(paths.ROOT / "src" / "conditions_June_2026"))
    from ingest import config  # noqa: PLC0415

    assert config.EXTERNAL_DIRS["gps_track"].resolve() == paths.SAILSYNC_DIR.resolve()


@pytest.mark.parametrize("old", ["data/src", "data/geo_data", "data/sailsync_api_results"])
def test_removed_duplicate_folders_stay_gone(old):
    assert not (paths.ROOT / old).exists(), (
        f"{old}/ is back. It was a byte-identical copy of {old.removeprefix('data/')}/; "
        "two copies let two modules read different data.")
