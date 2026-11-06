"""Run from the repo root: uv run --with pandas python -m backend.tests.test_backend"""

import datetime as dt
import io
import zipfile

import pandas as pd

from backend import analysis, race_analysis, strategy
from backend.analysis import audio_text, tagging, text_reader, transcripts

# --- strategy ---
assert strategy.angle_diff(350, 10) == 20 and strategy.angle_diff(10, 350) == -20
assert strategy.sector(225) == "SW" and strategy.sector(359) == "N"
tides = pd.DataFrame({"time": pd.to_datetime(["2026-06-01 08:00", "2026-06-01 14:00"]), "Type": ["L", "H"]})
assert strategy.tide_state(tides, dt.datetime(2026, 6, 1, 10))["state"] == "Flood"
now = {"time": dt.datetime(2026, 6, 1, 13), "speed": 12, "dir": 225}
assert strategy.live_check("SW", 10, 15, now, [])["status"] == "Plan holds"
assert strategy.live_check("SW", 10, 15, {**now, "dir": 290}, [])["status"] == "Change"
later = {"time": dt.datetime(2026, 6, 1, 15), "speed": 4, "dir": 225}
assert strategy.live_check("SW", 10, 15, now, [later])["warning"]
insight = strategy.venue_insight(strategy.load_wind(strategy.HISTORY_YEARS), "SSW", 13)
assert insight["n_days"] > 0
brief = strategy.briefing(insight, strategy.tide_state(strategy.load_tides(), dt.datetime(2025, 6, 10, 13)), "ILCA 7")
assert len(brief["questions"]) == 4

# --- analysis routing ---
assert analysis.map_file("race_results_2024.xlsx")[1] == "Race results"
assert analysis.map_file("wind_log.csv")[1] == "Wind observations"
assert analysis.map_file("sailing_instructions.pdf")[1] == "Venue rules"
assert analysis.map_file("whiteboard.jpg")[2] == "image"
assert analysis.map_file("call.vtt")[2] == "transcript"
assert analysis.map_file("Voice memo 12.m4a") == ("AUDIO", "Transcript", "audio")
assert analysis.map_file("x.bin")[1] is None

# --- capability 1: text ---
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w") as archive:
    archive.writestr("word/document.xml", "<w:p><w:t>Right side paid</w:t></w:p><w:p><w:t>A &amp; B</w:t></w:p>")
assert text_reader.read_text("notes.docx", buffer.getvalue())["text"] == "Right side paid\nA & B"
assert text_reader.read_text("a.txt", "héllo".encode())["text"] == "héllo"

# --- capability 3: transcripts ---
srt = "1\n00:00:01,000 --> 00:00:03,000\nCoach: Go right.\n\n2\n00:00:04,000 --> 00:00:05,000\nOk\n"
parsed = transcripts.parse_transcript(srt)
assert parsed["method"] == "transcript (srt)" and parsed["segments"][0]["speaker"] == "Coach"
assert transcripts.parse_transcript("[01:02] Sailor: windy")["segments"][0]["time"] == "01:02"
assert transcripts.parse_transcript("")["error"]

# --- capability 4: voice memos (no speech model needed: engines are not called) ---
whisper = audio_text.to_result([{"start": 3.4, "text": " Go right. "}, {"start": 3725, "text": "Ok"},
                                {"start": 9, "text": "  "}], "whisper (test)")
assert [s["time"] for s in whisper["segments"]] == ["00:03", "1:02:05"] and whisper["text"] == "Go right.\nOk"
assert audio_text.to_result([], "whisper (test)")["error"] == "No speech recognised"
assert audio_text.transcribe_audio(b"not audio")["error"]  # unreadable or PyAV missing: an error, never a crash

# --- tagging ---
assert "Wind" in tagging.tag("The breeze veered right.")
rules, covered = tagging.extract_rules("Boats shall keep clear of the exclusion zone. Use VHF channel 72.")
assert rules and covered["Exclusion zones"] and covered["Communication"]

# --- race tracks ---
summary = race_analysis.summary()
assert summary["races"] and summary["verdict"] in ("Left", "Right", "Middle")

print("ok", insight["n_days"], brief["confidence"], summary["verdict"])

# --- scenarios ---
history = strategy.load_wind(strategy.HISTORY_YEARS)
base = strategy.venue_insight(history, "SSW", 13)
calm = strategy.scenario_approach(base, "Medium", "Late", "Aggressive")
assert calm["side"] == "Middle" and calm["commitment"] == "Hedge 50/50"
bold, careful = (strategy.scenario_approach(base, "Medium", "On time", a) for a in ("Aggressive", "Conservative"))
assert bold["lean"] > careful["lean"]
rows = strategy.scenario_matrix(history, 13, "SSW", base["speed"], "Balanced")
assert rows and all(1 <= r["score"] <= 25 for r in rows)
assert all(r["lever"] == "None" for r in rows if r["within"])
assert strategy.residual(rows[0], "Plan B") <= rows[0]["score"]
strict = strategy.scenario_matrix(history, 13, "SSW", base["speed"], "Conservative")
assert sum(not r["within"] for r in strict) >= sum(not r["within"] for r in rows)
print("scenarios ok", [(r["scenario"], r["score"], r["lever"]) for r in rows[:5]])
