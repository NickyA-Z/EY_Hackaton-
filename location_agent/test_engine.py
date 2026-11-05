"""Run: uv run --with pandas python location_agent/test_engine.py"""

import datetime as dt

import pandas as pd

import engine

assert engine.angle_diff(350, 10) == 20
assert engine.angle_diff(10, 350) == -20
assert engine.sector(225) == "SW" and engine.sector(359) == "N"
assert engine.map_file("race_results_2024.xlsx") == ("XLSX", "Race results")
assert engine.map_file("wind_log.csv") == ("CSV", "Wind observations")
assert engine.map_file("unknown.bin")[1] is None

tides = pd.DataFrame({"time": pd.to_datetime(["2026-06-01 08:00", "2026-06-01 14:00"]),
                      "Type": ["L", "H"]})
assert engine.tide_state(tides, dt.datetime(2026, 6, 1, 10))["state"] == "Flood"

now = {"time": dt.datetime(2026, 6, 1, 13), "speed": 12, "dir": 225}
assert engine.live_check("SW", 10, 15, now, [])["status"] == "Plan holds"
assert engine.live_check("SW", 10, 15, {**now, "dir": 290}, [])["status"] == "Change"
later = {"time": dt.datetime(2026, 6, 1, 15), "speed": 4, "dir": 225}
result = engine.live_check("SW", 10, 15, now, [later])
assert result["status"] == "Change coming" and result["warning"]

history = engine.load_wind(engine.HISTORY_YEARS)
insight = engine.venue_insight(history, "SSW", 13)
assert insight["n_days"] > 0 and insight["side"] in ("Left", "Right", "Middle")
brief = engine.briefing(insight, engine.tide_state(engine.load_tides(), dt.datetime(2025, 6, 10, 13)), "ILCA 7")
assert len(brief["questions"]) == 4

print("ok", {k: insight[k] for k in ("n_days", "speed", "veer_rate", "side", "onset_hour")}, brief["confidence"])
