"""Race boundaries and uncertain buoy approaches must not leak into other races."""

import pandas as pd

from backend import paths
from frontend.race_progress import load_race_progress, race_track_window


def course():
    return {"gun": 1000, "end": 3700, "first_beat_end": 2500,
            "mark1": [33.0, -118.0], "mark1_uncertainty_m": 80}


def track():
    return pd.DataFrame({"time_epoch": [900, 1000, 1200, 1400, 1600, 2000, 3800],
                         "lat": [33.01, 33.01, 33.005, 33.0001, 33.004, 33.01, 33.01],
                         "lng": [-118.0] * 7})


def test_first_beat_stops_at_first_observed_arrival():
    window, arrival = race_track_window(track(), course())
    assert arrival == 1400
    assert window.time_epoch.tolist() == [1000, 1200, 1400]


def test_missing_rounding_ends_at_closest_approach_without_claiming_arrival():
    frame = track()
    frame.loc[frame.time_epoch == 1400, "lat"] = 33.002
    window, arrival = race_track_window(frame, course())
    assert arrival is None
    assert window.time_epoch.tolist() == [1000, 1200, 1400]


def test_full_race_excludes_session_points_outside_window():
    window, arrival = race_track_window(track(), course(), first_beat=False)
    assert arrival is None
    assert window.time_epoch.tolist() == [1000, 1200, 1400, 1600, 2000]


def test_real_race_tracks_are_scoped_and_windows_do_not_overlap():
    races = load_race_progress()
    assert len(races) == 2
    assert [race["race"] for race in races] == [1, 2]
    assert [entry["name"] for entry in races[0]["rankings"]] == [
        "Rasmus Granzin", "Lawson McAullay", "Clemente Seguel Lacámara"]
    assert [entry["name"] for entry in races[1]["rankings"]] == [
        "Duko Bos", "Pavlos Kontides", "Dimitri Peroni"]
    for race in races:
        for boat in race["tracks"]:
            assert all(race["gun"] <= p[0] <= race["first_beat_end"] for p in boat["points"])
            assert all(race["gun"] <= p[0] <= race["end"] for p in boat["full_points"])
        assert len(race["start_line"]) == 2
    assert all(a["end"] < b["gun"] for a, b in zip(races, races[1:]))


def test_race_two_winner_illustration_follows_gps_then_reaches_mark():
    race = load_race_progress()[1]
    duko = next(track for track in race["tracks"] if track["name"] == "Duko Bos")
    assert duko["synthetic"]
    assert len(duko["points"]) > 2
    assert duko["recorded_until"] == duko["points"][-2][0]
    assert 600 < duko["arrival"] - race["gun"] < 686.8
    assert duko["points"][-1][1:] == race["mark1"]
    assert duko["full_points"][-1][0] > duko["arrival"]


def test_dimitri_gap_is_illustrated_to_buoy_after_recorded_points():
    race = load_race_progress()[1]
    dimitri = next(track for track in race["tracks"] if track["name"] == "Dimitri Peroni")
    assert dimitri["synthetic"]
    assert len(dimitri["points"]) > 100
    assert dimitri["recorded_until"] == dimitri["points"][-2][0]
    assert dimitri["arrival"] > dimitri["recorded_until"]
    assert dimitri["points"][-1][1:] == race["mark1"]


def test_ranked_boats_with_gps_keep_a_visible_arrival():
    for race in load_race_progress():
        ranked = race["tracks"][:3]
        assert all(track["arrival"] is not None for track in ranked if track["points"])
        arrivals = [track["arrival"] for track in ranked if track["arrival"] is not None]
        assert arrivals == sorted(arrivals)


def test_agent_full_replay_uses_full_simulation_and_missing_race_stays_empty():
    races = load_race_progress()
    race = races[0]
    agent = next(track for track in race["tracks"] if track["agent"])
    source = pd.read_csv(paths.LOCATION_AGENT_OUTPUT_DIR / "2026-07-19_port_la_course" / "sim" / "race1_agent_full.csv")
    expected, _ = race_track_window(source, race, first_beat=False)
    assert agent["full_points"] == expected[["time_epoch", "lat", "lng"]].values.tolist()
    assert agent["full_points"][-1][0] > agent["points"][-1][0]
    missing = next(track for track in races[1]["tracks"] if track["agent"])
    assert missing["points"] == missing["full_points"] == []
