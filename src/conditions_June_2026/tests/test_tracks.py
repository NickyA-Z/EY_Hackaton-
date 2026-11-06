import math
import shutil

import pandas as pd
import pytest
from ingest import gpx, run, sailsync, schema, tracks
from ingest.classify import classify


def copy_as(fixtures, tmp_path, fixture, rel):
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures / fixture, dest)
    return dest


GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Coach RIB</name><trkseg>
    <trkpt lat="33.7480" lon="-118.1400"><time>2026-07-19T21:00:00Z</time></trkpt>
    <trkpt lat="33.7480" lon="-118.1390"><time>2026-07-19T21:00:10Z</time></trkpt>
    <trkpt lat="bad" lon="-118.1380"><time>2026-07-19T21:00:20Z</time></trkpt>
    <trkpt lat="33.7490" lon="-118.1390"><time>2026-07-19T21:00:30Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


# --- motion helpers -------------------------------------------------------------------

def test_haversine_and_bearing():
    # one minute of latitude is one nautical mile (1852 m) to within ~0.5 %
    assert tracks.haversine_m(33.0, -118.0, 33.0 + 1 / 60, -118.0) == pytest.approx(1852, rel=0.005)
    assert tracks.bearing_deg(33.0, -118.0, 33.1, -118.0) == pytest.approx(0, abs=1e-6)
    assert tracks.bearing_deg(33.0, -118.0, 33.0, -117.9) == pytest.approx(90, abs=0.1)


# --- SailSync CSV -------------------------------------------------------------------------

def test_sailsync_identity_and_times(fixtures, tmp_path):
    p = copy_as(fixtures, tmp_path, "sailsync_track.csv", "winners/2796_15377_Matt_Wearn_AUS_199015.csv")
    df = sailsync.parse(p)
    assert schema.validate(df, "tracks") == []
    r = df.iloc[0]
    assert (r["track_id"], r["sailor"], r["nation"], r["sail_no"]) == ("2796_15377", "Matt Wearn", "AUS", "AUS 199015")
    assert r["is_top_finisher"] and r["source"] == "sailsync"
    assert r["time_utc"] == pd.Timestamp("2026-07-19 21:05:02.300", tz="UTC")   # epoch float noise rounded
    assert math.isnan(r["speed_kn"])                                            # first fix has no speed


def test_anonymous_and_non_top(fixtures, tmp_path):
    df = sailsync.parse(copy_as(fixtures, tmp_path, "sailsync_track.csv", "2796_15347_USA_211414.csv"))
    r = df.iloc[0]
    assert pd.isna(r["sailor"]) and r["nation"] == "USA" and not r["is_top_finisher"]


def test_speed_and_gap_handling(fixtures, tmp_path):
    df = sailsync.parse(copy_as(fixtures, tmp_path, "sailsync_track_gap.csv", "2796_1_A_B_AUS_1.csv"))
    dt = df["time_utc"].diff().dt.total_seconds()
    assert df.loc[dt > tracks.MAX_GAP_S, "speed_kn"].isna().all()          # no speed across a gap
    moving = df["speed_kn"].dropna()
    assert len(moving) >= 5 and moving.between(0, tracks.MAX_SPEED_KN).all()
    assert df["course_deg"].dropna().between(0, 360).all()


def test_gps_jump_is_dropped(tmp_path):
    p = tmp_path / "jumpy.csv"
    p.write_text("time_epoch,lat,lng\n1784495100,33.70,-118.27\n1784495101,33.70,-118.2699\n"
                 "1784495102,33.80,-118.2699\n")                         # 11 km in 1 s
    df = sailsync.parse(p)
    assert df["speed_kn"].iloc[1] > 0 and math.isnan(df["speed_kn"].iloc[2])


def test_generic_csv_with_iso_time(tmp_path):
    p = tmp_path / "rib.csv"
    p.write_text("Timestamp,Latitude,Longitude\n2026-07-19T14:00:00-07:00,33.75,-118.14\n"
                 "2026-07-19T14:00:10-07:00,33.75,-118.1395\nnot a time,33.75,-118.139\n")
    df = sailsync.parse(p)
    assert list(df["time_utc"]) == [pd.Timestamp("2026-07-19 21:00:00", tz="UTC"),
                                    pd.Timestamp("2026-07-19 21:00:10", tz="UTC")]
    assert df["track_id"].iloc[0] == "rib"


def test_missing_columns_returns_empty(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n")
    assert sailsync.parse(p).empty


# --- GPX -----------------------------------------------------------------------------------

def test_gpx(tmp_path):
    p = tmp_path / "coach_rib.gpx"
    p.write_text(GPX)
    df = gpx.parse(p)
    assert schema.validate(df, "tracks") == []
    assert len(df) == 3 and df["sailor"].iloc[0] == "Coach RIB" and df["source"].iloc[0] == "gpx"
    # 0.001 deg lon at 33.7 N ~ 92.6 m in 10 s ~ 18 kn, heading east
    assert df["speed_kn"].iloc[1] == pytest.approx(18.0, rel=0.02)
    assert df["course_deg"].iloc[1] == pytest.approx(90, abs=0.5)


def test_gpx_bad_xml(tmp_path):
    p = tmp_path / "broken.gpx"
    p.write_text("<gpx><trk>")
    assert gpx.parse(p).empty


# --- classification and end to end -------------------------------------------------------------

def test_classifier_routes_tracks(fixtures, tmp_path):
    csv = copy_as(fixtures, tmp_path, "sailsync_track.csv", "race.csv")
    g = tmp_path / "rib.gpx"
    g.write_text(GPX)
    assert classify(csv, use_llm=False).category == "gps_track"
    assert classify(g, use_llm=False).category == "gpx_track"


def test_end_to_end_tracks_table(fixtures, tmp_path):
    raw = tmp_path / "raw"
    copy_as(fixtures, raw, "sailsync_track_gap.csv", "tracks/2796_15377_Matt_Wearn_AUS_199015.csv")
    (raw / "tracks" / "rib.gpx").write_text(GPX)
    tables = run.ingest(raw, months=(7,))
    trk = tables["tracks"]
    assert schema.validate(trk, "tracks") == []
    assert set(trk["source"]) == {"sailsync", "gpx"} and trk["track_id"].nunique() == 2
    assert tables["observations"].empty                       # nothing else in this raw folder
    assert run.ingest(raw, months=(6,))["tracks"].empty      # July race filtered out for June
