import math

import pandas as pd
import pytest

from backend.ingest import coops, schema, units


def test_wind(fixtures):
    df = coops.parse(fixtures / "coops_9410670_wind_202106.csv")
    assert schema.validate(df) == []
    assert len(df) == 4
    r = df.iloc[0]
    assert r["time_utc"] == pd.Timestamp("2021-06-01 00:00", tz="UTC")
    assert r["wind_speed_kn"] == pytest.approx(7.2 * units.MS_TO_KN)
    assert r["wind_gust_kn"] == pytest.approx(8.0 * units.MS_TO_KN)
    assert r["wind_dir_deg"] == 216.0          # numeric Direction, not the "SW" column
    assert (r["source"], r["source_id"]) == ("coops", "9410670")
    assert (r["lat"], r["lon"]) == pytest.approx((33.7463, -118.2156))


def test_blank_values_become_nan(fixtures):
    df = coops.parse(fixtures / "coops_9410670_wind_202106.csv")
    assert df.iloc[2:][["wind_speed_kn", "wind_dir_deg", "wind_gust_kn"]].isna().all().all()


def test_air_temperature(fixtures):
    df = coops.parse(fixtures / "coops_9410670_air_temperature_202106.csv")
    assert df["air_temp_c"].iloc[0] == 18.7
    assert df["wind_speed_kn"].isna().all()


def test_wind_and_temperature_merge_into_one_row(fixtures):
    both = pd.concat([coops.parse(fixtures / "coops_9410670_wind_202106.csv"),
                      coops.parse(fixtures / "coops_9410670_air_temperature_202106.csv")])
    merged = schema.coalesce_duplicates(both)
    assert len(merged) == 4
    first = merged.iloc[0]
    assert first["air_temp_c"] == 18.7 and not math.isnan(first["wind_speed_kn"])


def test_tide_events(fixtures):
    df = coops.parse_tide_events(fixtures / "coops_9410660_predictions_202606.csv")
    assert schema.validate(df, "tide_events") == []
    assert list(df["type"]) == ["H", "L", "H"]
    assert df["height_m"].iloc[1] == -0.186
    assert df["time_utc"].iloc[0] == pd.Timestamp("2026-06-01 04:32", tz="UTC")


def test_predictions_file_is_not_an_observation(fixtures):
    assert coops.parse(fixtures / "coops_9410660_predictions_202606.csv").empty


def test_unknown_columns_and_bad_time(tmp_path):
    p = tmp_path / "9999999_water_temperature_202606.csv"
    p.write_text("Date Time, Water Temperature, X, N, R \n2026-06-01 00:00,19.5,0,0,0\nbroken,1,0,0,0\n")
    df = coops.parse(p)
    assert list(df["water_temp_c"]) == [19.5]
    assert df["lat"].isna().all()   # unknown station -> NaN coordinates, logged
