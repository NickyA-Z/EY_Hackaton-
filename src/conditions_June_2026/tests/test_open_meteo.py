import json

import pandas as pd
import pytest

from ingest import open_meteo, schema

FIXTURE = "open_meteo_racecourse_belmont_202606.json"


def write_variant(tmp_path, fixtures, name=FIXTURE, **changes):
    d = json.loads((fixtures / FIXTURE).read_text())
    for k, v in changes.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    p = tmp_path / name
    p.write_text(json.dumps(d))
    return p


def test_parse(fixtures):
    df = open_meteo.parse(fixtures / FIXTURE)
    assert schema.validate(df) == []
    r = df.iloc[0]
    assert (r["source"], r["source_id"]) == ("open_meteo", "racecourse_belmont")
    assert (r["lat"], r["lon"]) == (33.778557, -118.097)     # snapped grid cell
    assert (r["wind_speed_kn"], r["wind_gust_kn"], r["wind_dir_deg"]) == (1.8, 5.8, 186)
    assert (r["air_temp_c"], r["cloud_cover_pct"]) == (17.7, 1)


def test_local_time_uses_file_offset(fixtures):
    # The real file says utc_offset_seconds=-28800 (GMT-8) -> local 00:00 is 08:00 UTC.
    df = open_meteo.parse(fixtures / FIXTURE)
    assert df["time_utc"].iloc[0] == pd.Timestamp("2026-06-01 08:00", tz="UTC")


def test_dst_offset(tmp_path, fixtures):
    # A PDT file (-25200) must shift by 7 h instead.
    p = write_variant(tmp_path, fixtures, utc_offset_seconds=-25200)
    assert open_meteo.parse(p)["time_utc"].iloc[0] == pd.Timestamp("2026-06-01 07:00", tz="UTC")


def test_fallback_to_iana_zone_handles_dst(tmp_path, fixtures):
    p = write_variant(tmp_path, fixtures, utc_offset_seconds=None)
    june = open_meteo.parse(p)                                  # America/Los_Angeles, PDT
    assert june["time_utc"].iloc[0] == pd.Timestamp("2026-06-01 07:00", tz="UTC")

    d = json.loads(p.read_text())
    d["hourly"]["time"] = ["2026-01-15T00:00", "2026-03-08T02:00", "2026-03-08T03:00"]
    p.write_text(json.dumps(d))
    df = open_meteo.parse(p)                                    # PST, spring-forward gap, PDT
    assert list(df["time_utc"]) == [pd.Timestamp("2026-01-15 08:00", tz="UTC"),
                                    pd.Timestamp("2026-03-08 10:00", tz="UTC")]


def test_unit_conversion_and_nulls(tmp_path, fixtures):
    d = json.loads((fixtures / FIXTURE).read_text())
    d["hourly_units"]["wind_speed_10m"] = "km/h"
    d["hourly"]["wind_speed_10m"] = [10.0, None, 20.0]
    p = tmp_path / FIXTURE
    p.write_text(json.dumps(d))
    df = open_meteo.parse(p)
    assert df["wind_speed_kn"].iloc[0] == pytest.approx(5.39957)
    assert pd.isna(df["wind_speed_kn"].iloc[1])


def test_missing_variable_and_ragged_arrays(tmp_path, fixtures):
    d = json.loads((fixtures / FIXTURE).read_text())
    del d["hourly"]["cloud_cover"]
    d["hourly"]["temperature_2m"] = d["hourly"]["temperature_2m"][:2]
    p = tmp_path / FIXTURE
    p.write_text(json.dumps(d))
    df = open_meteo.parse(p)
    assert len(df) == 2 and df["cloud_cover_pct"].isna().all()
