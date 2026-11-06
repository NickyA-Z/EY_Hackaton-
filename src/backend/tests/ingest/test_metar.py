import math

import pandas as pd
import pytest

from backend.ingest import metar, schema


@pytest.fixture
def df(fixtures):
    return metar.parse(fixtures / "metar_LGB.csv").set_index("time_utc")


def row(df, ts):
    return df.loc[pd.Timestamp(ts, tz="UTC")]


def test_schema_valid(df):
    assert schema.validate(df.reset_index()) == []
    assert (df["source"] == "metar").all()
    assert (df["source_id"] == "LGB").all()
    assert not df["is_sample"].any()


def test_normal_report(df):
    r = row(df, "2026-06-01 00:53")
    assert r["wind_dir_deg"] == 300
    assert r["wind_speed_kn"] == 9
    assert math.isnan(r["wind_gust_kn"])
    assert r["air_temp_c"] == pytest.approx(24.4)   # from remark T02440122, not 24
    assert r["cloud_cover_pct"] == 0


def test_calm_has_zero_speed_and_no_direction(df):
    r = row(df, "2025-06-01 13:53")
    assert r["wind_speed_kn"] == 0
    assert math.isnan(r["wind_dir_deg"])


def test_variable_direction_is_nan(df):
    r = row(df, "2025-06-01 17:53")
    assert r["wind_speed_kn"] == 3
    assert math.isnan(r["wind_dir_deg"])


def test_gust(df):
    r = row(df, "2021-06-04 20:53")
    assert (r["wind_dir_deg"], r["wind_speed_kn"], r["wind_gust_kn"]) == (230, 6, 14)


def test_variability_group_does_not_break_parsing(df):
    r = row(df, "2023-06-03 17:53")
    assert (r["wind_dir_deg"], r["wind_speed_kn"]) == (190, 7)
    assert r["cloud_cover_pct"] == 75   # BKN


def test_missing_temperature_and_missing_wind(df):
    assert math.isnan(row(df, "2021-06-13 10:53")["air_temp_c"])
    r = row(df, "2021-06-05 00:53")
    assert math.isnan(r["wind_speed_kn"]) and r["air_temp_c"] == pytest.approx(18.3)


def test_madis_duplicate_dropped(df):
    assert df.index.is_unique
    assert row(df, "2026-06-13 23:15")["wind_dir_deg"] == 300   # regular report, not MADISHF (290)


@pytest.mark.parametrize("report, temp", [
    ("KXXX 010000Z 00000KT 10SM CLR M05/M10 A2992", -5.0),
    ("KXXX 010000Z 00000KT 10SM CLR M05/M10 A2992 RMK T10521103", -5.2),
])
def test_negative_temperature(report, temp):
    assert metar.parse_metar(report)["air_temp_c"] == pytest.approx(temp)


def test_rmk_wind_like_group_is_ignored():
    assert math.isnan(metar.parse_metar("KXXX 010000Z 10SM CLR RMK PK WND 27030/1234")["wind_speed_kn"])


def test_bad_rows_are_skipped(tmp_path, fixtures):
    p = tmp_path / "LGB_bad.csv"
    p.write_text((fixtures / "metar_LGB.csv").read_text()
                 + "LGB,not-a-date,KLGB 010053Z 30009KT\nLGB,2026-06-02 00:53,\nLGB,a,b,c,d\n")
    out = metar.parse(p)
    assert len(out) == 8
