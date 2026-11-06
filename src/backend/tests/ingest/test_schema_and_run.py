import shutil

import pandas as pd
import pytest

from backend.ingest import run, schema


def test_conform_adds_missing_columns_and_dtypes():
    df = schema.conform(pd.DataFrame({"time_utc": ["2026-06-01T00:00Z"], "source": ["x"],
                                      "source_id": ["y"], "wind_speed_kn": ["5"], "extra": [1]}))
    assert list(df.columns) == list(schema.OBSERVATION_COLUMNS)
    assert schema.validate(df) == []
    assert df["wind_speed_kn"].iloc[0] == 5.0 and not df["is_sample"].iloc[0]


def test_calm_rule_clears_direction():
    df = schema.conform(pd.DataFrame({"time_utc": ["2026-06-01T00:00Z"] * 2, "source": "x",
                                      "source_id": ["a", "b"], "wind_speed_kn": [0.0, 3.0],
                                      "wind_dir_deg": [0.0, 0.0]}))
    assert pd.isna(df["wind_dir_deg"].iloc[0]) and df["wind_dir_deg"].iloc[1] == 0.0


def test_validate_reports_problems():
    df = schema.conform(pd.DataFrame({"time_utc": ["2026-06-01T00:00Z"] * 2, "source": "x",
                                      "source_id": "a", "wind_speed_kn": [5.0, 99.0],
                                      "wind_dir_deg": [400.0, 10.0]}))
    problems = " | ".join(schema.validate(df))
    assert "wind_dir_deg" in problems and "wind_speed_kn" in problems and "duplicate" in problems


@pytest.fixture
def raw_dir(tmp_path, fixtures):
    """A miniature data/raw tree built from the fixtures."""
    layout = {
        "metar/LGB_202606.csv": "metar_LGB.csv",
        "noaa_coops/9410670_wind_202106.csv": "coops_9410670_wind_202106.csv",
        "noaa_coops/9410670_air_temperature_202106.csv": "coops_9410670_air_temperature_202106.csv",
        "noaa_coops/9410660_predictions_202606.csv": "coops_9410660_predictions_202606.csv",
        "ndbc/46025_2025.txt.gz": "ndbc_46025_2025.txt.gz",
        "ndbc/46222_202606.txt.gz": "ndbc_46222_202606.txt.gz",
        "open_meteo/racecourse_belmont_202606.json": "open_meteo_racecourse_belmont_202606.json",
    }
    for dest, src in layout.items():
        (tmp_path / dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures / src, tmp_path / dest)
    (tmp_path / "noaa_coops/9410670_wind_202107.csv").write_text("not, a, coops, file\n")  # broken
    (tmp_path / "coach_notes.xlsx").write_bytes(b"")                                    # unknown format
    return tmp_path


def test_end_to_end(raw_dir):
    tables = run.ingest(raw_dir, months=(6,))
    obs, tides = tables["observations"], tables["tide_events"]
    assert schema.validate(obs) == [] and schema.validate(tides, "tide_events") == []
    assert set(obs["source"]) == {"metar", "coops", "ndbc", "open_meteo"}
    assert (obs["time_utc"].dt.month == 6).all()
    # wind + air_temperature files for the same station/hour become one row; empty rows dropped
    assert len(obs[obs["source"] == "coops"]) == 2
    assert len(tides) == 3


def test_unclaimed_files_are_reported(raw_dir):
    assert [p.name for p in run.unclaimed_files(raw_dir)] == ["coach_notes.xlsx"]
