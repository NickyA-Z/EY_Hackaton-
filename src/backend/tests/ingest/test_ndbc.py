import gzip
import math

import pandas as pd
import pytest

from backend.ingest import ndbc, schema, units


def test_annual_file_keeps_only_requested_months(fixtures):
    df = ndbc.parse(fixtures / "ndbc_46025_2025.txt.gz", months=(6,))
    assert schema.validate(df) == []
    assert list(df["time_utc"]) == [pd.Timestamp("2025-06-01 00:00", tz="UTC"),
                                    pd.Timestamp("2025-06-01 00:10", tz="UTC")]
    assert len(ndbc.parse(fixtures / "ndbc_46025_2025.txt.gz", months=None)) == 4


def test_values_and_units(fixtures):
    r = ndbc.parse(fixtures / "ndbc_46025_2025.txt.gz", months=(6,)).iloc[1]
    assert r["wind_dir_deg"] == 242
    assert r["wind_speed_kn"] == pytest.approx(3.7 * units.MS_TO_KN)
    assert r["wind_gust_kn"] == pytest.approx(5.1 * units.MS_TO_KN)
    assert (r["air_temp_c"], r["water_temp_c"], r["wave_height_m"]) == (14.7, 17.8, 0.87)
    assert (r["source"], r["source_id"]) == ("ndbc", "46025")


def test_missing_sentinels(fixtures):
    first = ndbc.parse(fixtures / "ndbc_46025_2025.txt.gz", months=(6,)).iloc[0]
    assert math.isnan(first["wave_height_m"])          # 99.00
    wave_buoy = ndbc.parse(fixtures / "ndbc_46222_202606.txt.gz", months=(6,))
    assert wave_buoy[["wind_dir_deg", "wind_speed_kn", "wind_gust_kn", "air_temp_c"]].isna().all().all()
    assert list(wave_buoy["wave_height_m"]) == [0.91, 0.86]
    assert list(wave_buoy["water_temp_c"]) == [18.6, 18.5]


def test_mm_and_bad_rows(tmp_path, fixtures):
    lines = gzip.open(fixtures / "ndbc_46222_202606.txt.gz", "rt").read().splitlines()
    lines += ["2026 06 01 01 26  MM   MM   MM  0.95 12.50  5.50 250     MM    MM  18.4    MM   MM    MM",
              "2026 13 45 01 26 999 99.0 99.0  0.95 12.50  5.50 250 9999.0 999.0 18.4 999.0 99.0 99.00",
              "garbage"]
    p = tmp_path / "46222_202606.txt.gz"
    with gzip.open(p, "wt") as f:
        f.write("\n".join(lines) + "\n")
    df = ndbc.parse(p, months=(6,))
    assert len(df) == 3
    assert df["wave_height_m"].iloc[-1] == 0.95 and math.isnan(df["wind_speed_kn"].iloc[-1])
