"""Tests for backend.previous_strategy (the data behind the 3D "Previous strategy" tab).

The synthetic tests pin the bugs found while building it against the real SailSync files:
a GPS fix at lat -85 (Antarctica), a result file with no sailor name, one boat that took
1,786 s on a 440 s race, and holes in a track. The last tests use the real data and skip
when it is not in the checkout.
"""

import json
import math

import numpy as np
import pandas as pd
import pytest

from backend import previous_strategy as ps
from backend.race_model import model
from frontend import previous_strategy_view as view

LAT0, LNG0 = 33.69, -118.27


def fix(x, y):
    lng, lat = ps.to_lnglat(x, y, LAT0, LNG0)
    return float(lat), float(lng)


def write_track(folder, name, rows):
    pd.DataFrame(rows, columns=["time_epoch", "lat", "lng"]).to_csv(folder / name, index=False)


def straight_track(t_start, seconds, *, step=2.0, x_speed=0.0, y_speed=3.0, skip=None):
    """Boat sailing north at 3 m/s; `skip` = (from_s, to_s) offsets without any GPS fix."""
    rows = []
    for t in np.arange(0, seconds + step, step):
        if skip and skip[0] <= t <= skip[1]:
            continue
        lat, lng = fix(x_speed * t, y_speed * t)
        rows.append((t_start + t, lat, lng))
    return rows


def legs_frame(entries, *, race="1", t_start=1_000_000.0):
    """entries: [(boat_id, position, elapsed_s)] -> a minimal race_model.legs() frame."""
    return pd.DataFrame([{
        "session": ps.SESSION, "race": race, "boat_id": b, "name": f"boat {b}", "position": p, "leg": 1,
        "direction": "upwind", "t_start": t_start, "t_end": t_start + e, "wind_dir": 265.0, "wind_kt": np.nan,
    } for b, p, e in entries])


# ---------- geometry ----------

def test_metres_roundtrip():
    x, y = ps.to_metres(33.7, -118.25, LAT0, LNG0)
    lng, lat = ps.to_lnglat(x, y, LAT0, LNG0)
    assert (lat, lng) == pytest.approx((33.7, -118.25), abs=1e-9)
    # 0.02 deg lng at 33.69 N = 0.02 * 111320 * cos(33.69 deg) = 1852 m; 0.01 deg lat = 1105 m
    assert float(x) == pytest.approx(1852.5, abs=1.0) and float(y) == pytest.approx(1105.4, abs=1.0)


def test_bearing():
    assert ps.bearing_deg(0, 1) == 0 and ps.bearing_deg(1, 0) == 90 and ps.bearing_deg(-1, 0) == 270


# ---------- loading ----------

def test_load_drops_antarctica_and_glitch_and_keeps_nameless_file(tmp_path):
    rows = straight_track(1_000_000, 60)
    rows.insert(10, (rows[10][0] + 0.1, -85.6, -37.3))          # lat -85: outside the venue box
    lat, lng = fix(5_000, 0)
    rows.insert(20, (rows[20][0] + 0.1, lat, lng))              # inside the box but 5 km away in 0.1 s
    write_track(tmp_path, "2796_15336_Weston_Fremont_CAN_220882.csv", rows)
    write_track(tmp_path, "2796_15347_USA_211414.csv", straight_track(1_000_000, 60))   # no sailor name
    tracks = ps.load_fleet_tracks(tmp_path)
    assert set(tracks) == {"15336", "15347"}
    frame = tracks["15336"]["df"]
    assert frame["lat"].between(*ps.LAT_RANGE).all() and len(frame) == 31   # 31 real fixes survive
    assert tracks["15347"]["name"] == "USA 211414"
    assert tracks["15336"]["name"] == "Weston Fremont (CAN 220882)"


def test_winner_folder_flags_winner(tmp_path):
    (tmp_path / "winners").mkdir()
    write_track(tmp_path / "winners", "2796_1_Matt_Wearn_AUS_199015.csv", straight_track(1_000_000, 30))
    write_track(tmp_path, "2796_2_Ann_Other_GBR_1.csv", straight_track(1_000_000, 30))
    tracks = ps.load_fleet_tracks(tmp_path)
    assert tracks["1"]["winner"] and not tracks["2"]["winner"]


# ---------- building a race ----------

def tracks_for(boats, **kwargs):
    return {b: {"name": f"boat {b}", "winner": False,
                "df": pd.DataFrame(straight_track(1_000_000, 700, **kwargs.get(b, {})), columns=["time_epoch", "lat", "lng"])}
            for b in boats}


def test_race_clock_starts_at_zero_and_speed_is_right():
    race = ps.build_race("1", legs_frame([("a", 1, 400), ("b", 2, 420)]), tracks_for(["a", "b"]))
    boat = race["boats"][0]
    assert boat["t"][0] == 0 and boat["position"] == 1 and race["duration_s"] < 420
    middle = boat["speed_kn"][len(boat["t"]) // 2]
    assert middle == pytest.approx(3.0 * ps.KN, rel=0.02)           # 3 m/s north = 5.8 kn


def test_hole_in_track_stays_a_hole():
    tracks = tracks_for(["a"], a={"skip": (100, 200)})
    race = ps.build_race("1", legs_frame([("a", 1, 400)]), tracks)
    boat = race["boats"][0]
    gap = (boat["t"] > 125) & (boat["t"] < 175)
    assert not boat["valid"][gap].any() and boat["valid"][boat["t"] < 80].all()
    seg = ps.segments_frame(race)
    assert not ((seg["t0"] > 120) & (seg["t1"] < 180)).any()         # nothing drawn across the hole
    assert seg["t1"].max() - seg["t0"].min() > 300                   # but the rest is there


def test_straggler_is_cut_not_allowed_to_stretch_the_time_axis():
    entries = [("a", 1, 400), ("b", 2, 420), ("c", 3, 440), ("d", 4, 1786)]
    race = ps.build_race("1", legs_frame(entries), tracks_for(["a", "b", "c", "d"]))
    assert race["truncated"] == ["d"]
    assert race["duration_s"] <= race["cap_s"] == pytest.approx(1.5 * 430)
    assert race["duration_s"] < 700


def test_untracked_boats_are_counted_not_invented():
    race = ps.build_race("1", legs_frame([("a", 1, 400), ("zz", 2, 410)]), tracks_for(["a"]))
    assert race["tracked"] == 1 and race["in_race"] == 2 and race["skipped"] == 1


def test_unknown_race_and_no_track_raise():
    with pytest.raises(KeyError):
        ps.build_race("nope", legs_frame([("a", 1, 400)]), tracks_for(["a"]))
    with pytest.raises(ValueError):
        ps.build_race("1", legs_frame([("zz", 1, 400)]), tracks_for(["a"]))


def test_positions_at_is_clamped_and_flags_finished():
    race = ps.build_race("1", legs_frame([("a", 1, 400)]), tracks_for(["a"]))
    early, late = ps.positions_at(race, 100).iloc[0], ps.positions_at(race, 10_000).iloc[0]
    assert not early["finished"] and late["finished"] and late["t"] < 400 and early["lat"] < late["lat"]


# ---------- weather helpers ----------

def test_direction_interpolation_wraps_through_north():
    frame = pd.DataFrame({"epoch": [0.0, 3600.0], "dir": [350.0, 10.0]})
    mid = ps._interp_dir(frame, 1800.0)
    assert min(mid, 360 - mid) < 1.0                                  # ~0 deg (N), not 180


def test_interp_refuses_a_big_gap_instead_of_guessing():
    frame = pd.DataFrame({"epoch": [0.0, 20_000.0], "speed_kn": [5.0, 9.0]})
    assert ps._interp(frame, "speed_kn", 10_000.0) is None       # samples 5.5 h apart: no value, not a guess
    assert ps._interp(frame, "speed_kn", -5.0) is None           # before the first sample
    assert ps._interp(frame, "speed_kn", 10_000.0, max_gap_s=30_000) == pytest.approx(7.0)


def test_compass():
    assert ps.compass(268.7) == "W" and ps.compass(224) == "SW" and ps.compass(2) == "N"


# ---------- real data (skipped when not in the checkout) ----------

real = pytest.mark.skipif(not (ps.race_analysis.RESULTS / "probe_report.json").exists()
                          or not ps.BATHYMETRY.exists(), reason="SailSync / geodata files not present")


@real
def test_real_data_loads_all_boats_inside_the_venue_box():
    tracks = ps.load_fleet_tracks()
    assert len(tracks) == 45                                          # 45 CSVs incl. the nameless USA 211414
    assert all(t["df"]["lat"].between(*ps.LAT_RANGE).all() and t["df"]["lng"].between(*ps.LNG_RANGE).all()
               for t in tracks.values())


@real
def test_real_race_geometry_and_conditions():
    tracks, legs = ps.load_fleet_tracks(), model.legs()
    assert ps.race_ids(legs) == ["6067", "6068", "6069"]
    race = ps.build_race("6068", legs, tracks)
    assert race["truncated"] and race["duration_s"] <= race["cap_s"]            # the 1,786 s boat
    marks = ps.race_marks("6068", legs, tracks).sort_values("mark")
    dx, dy = ps.to_metres(marks.iloc[1]["lat"], marks.iloc[1]["lng"], marks.iloc[0]["lat"], marks.iloc[0]["lng"])
    assert 800 < math.hypot(float(dx), float(dy)) < 1500                        # ~1.1 km beat
    assert 250 < ps.bearing_deg(float(dx), float(dy)) < 300                     # sailed into a westerly
    c = ps.conditions_at(race["t0"] + 200, race["origin"], window=(race["t0"], race["t0"] + 400))
    assert 3 < c["noaa"]["speed_kn"] < 25 and 200 < c["noaa"]["dir"] < 300
    assert 0 < c["open_meteo"]["speed_kn"] < 25 and c["waves"]["height_m"] < 3
    assert c["tide"]["state"] in ("Flood", "Ebb") and "km from the course" in c["noaa"]["source"]


@real
def test_documents_report_what_they_could_not_check():
    cond = {"noaa": {"speed_kn": 9.1, "gust_kn": 10.7, "rise_2h_kn": 0.1}, "open_meteo": {"cloud_pct": 1.0},
            "waves": {"height_m": 0.8}, "tide": {"turns_in_race": False}}
    result = ps.strategy_documents(cond)
    ids = [d["id"] for d in result["selected"]]
    assert {"TS-01", "TS-10", "TS-11", "TS-02"} <= set(ids) and "TS-03" not in ids and "TS-04" not in ids
    assert "current_kt" in result["missing"] and "precipitation_mm_h" in result["missing"]
    assert all(d["title"] for d in result["selected"])


@real
def test_depth_image_covers_the_request_and_is_a_png_data_uri():
    uri, (west, south, east, north) = ps.bathymetry_image((-118.30, 33.66, -118.22, 33.73))
    assert uri.startswith("data:image/png;base64,")
    assert west <= -118.30 + 1e-3 and east >= -118.22 - 1e-3 and south <= 33.66 + 1e-3 and north >= 33.73 - 1e-3


# ---------- the 3D scene itself (regression: bugs only a browser showed) ----------

def _expressions(node, found=None):
    """Every pydeck-generated "@@=" expression string in a serialised deck."""
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            _expressions(value, found)
            if key in ("widthUnits", "radiusUnits"):
                found.append(f"UNIT-KEY:{key}={value}")
    elif isinstance(node, list):
        for value in node:
            _expressions(value, found)
    elif isinstance(node, str) and node.startswith("@@="):
        found.append(node)
    return found


@real
def test_scene_has_no_expression_that_the_browser_cannot_parse():
    """pydeck wraps every UNQUOTED string argument in "@@=". Two of them broke the real page:
    width_units="pixels" (flooded the canvas) and the depth image data-URI (parse error at the ':')."""
    tracks, legs = ps.load_fleet_tracks(), model.legs()
    race = ps.build_race("6067", legs, tracks)
    marks = ps.race_marks("6067", legs, tracks)
    approaches = ps.race_approaches("6067", legs, tracks, marks)
    bundle = {"race": race, "marks": marks, "approaches": approaches,
              "segments": ps.segments_frame(race, approaches), "sailsync_wind_dir": 265.0}
    opts = view.Options(tuple(view.ALL_LAYERS), "Speed", None, None, 300.0, 1.0, ps.NOAA_DEFAULT_STATION)
    spec = json.loads(view._build_deck(bundle, opts).to_json())

    assert {layer["@@type"] for layer in spec["layers"]} >= {
        "BitmapLayer", "LineLayer", "PolygonLayer", "PathLayer", "TextLayer", "ScatterplotLayer"}
    bitmap = next(layer for layer in spec["layers"] if layer["@@type"] == "BitmapLayer")
    assert bitmap["image"].startswith("data:image/png;base64,")          # a literal, not an expression
    for expression in _expressions(spec):
        assert not expression.startswith("@@=data:"), expression[:60]
        assert "UNIT-KEY" not in expression, expression
        assert expression not in ("@@=pixels", "@@=meters", "@@=common"), expression
    line_layers = [layer for layer in spec["layers"] if layer["@@type"] == "LineLayer" and layer.get("pickable")]
    assert line_layers and all(layer["widthMinPixels"] == layer["widthMaxPixels"] for layer in line_layers)
