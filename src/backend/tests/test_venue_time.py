"""Run with: .venv/bin/python -m pytest backend/tests/test_venue_time.py (from the repo root)."""
import pandas as pd

from backend.venue_time import open_meteo_to_local, open_meteo_to_local_labels, utc_to_local


def test_open_meteo_gmt_minus_8_labels_become_pdt():
    # A June file labelled with GMT-8: "13:00" is 21:00 UTC, i.e. 14:00 PDT.
    out = open_meteo_to_local(["2026-06-15T13:00"], -28800)
    assert out.iloc[0] == pd.Timestamp("2026-06-15 14:00")


def test_offset_matching_the_real_clock_changes_nothing():
    assert open_meteo_to_local(["2026-06-15T13:00"], -25200).iloc[0] == pd.Timestamp("2026-06-15 13:00")
    assert open_meteo_to_local(["2026-01-15T13:00"], -28800).iloc[0] == pd.Timestamp("2026-01-15 13:00")


def test_missing_offset_keeps_labels():
    assert open_meteo_to_local(["2026-06-15T13:00"], None).iloc[0] == pd.Timestamp("2026-06-15 13:00")


def test_noaa_gmt_to_local_is_dst_aware():
    out = utc_to_local(["2026-06-15 20:00", "2026-12-15 20:00"])
    assert list(out) == [pd.Timestamp("2026-06-15 13:00"), pd.Timestamp("2026-12-15 12:00")]


def test_labels_keep_open_meteo_format():
    assert open_meteo_to_local_labels(["2026-06-15T23:00"], -28800) == ["2026-06-16T00:00"]
