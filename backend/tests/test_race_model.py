"""Synthetic race check for backend.race_model.model. Run from the repo root:
.venv/bin/python -m backend.tests.test_race_model
"""

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from backend.race_model import model

LAT0, LNG0 = 33.70, -118.27


def latlng(x, y):
    return LAT0 + y / 110_540, LNG0 + x / (111_320 * math.cos(math.radians(LAT0)))


def write_race(root):
    """Start (0,0) -> mark 1 at (0,1000) -> mark 2 back at (0,0). Boat 1 goes far left and wins."""
    session, race = root / "100", root / "100" / "7"
    (session / "tracks").mkdir(parents=True)
    race.mkdir()
    t0 = 1_000_000.0
    # boat: (x reached halfway up the beat, rounding time, finish time)
    boats = {"1": (-400, t0 + 600, t0 + 1000), "2": (50, t0 + 650, t0 + 1080), "3": (150, t0 + 700, t0 + 1100)}
    for boat, (wide, t1, t2) in boats.items():
        times = np.arange(t0, t2 + 1, 2.0)
        up = np.clip((times - t0) / (t1 - t0), 0, 1)
        down = np.clip((times - t1) / (t2 - t1), 0, 1)
        x = np.where(times <= t1, wide * np.sin(np.pi * up), 0)
        y = np.where(times <= t1, 1000 * up, 1000 * (1 - down))
        lat, lng = latlng(x, y)
        pd.DataFrame({"time_epoch": times, "lat": lat, "lng": lng}).to_csv(session / "tracks" / f"{boat}.csv", index=False)
    legs = [{"leg_index": 1, "direction": "upwind"}, {"leg_index": 2, "direction": "downwind"}]
    (session / "analysis.json").write_text(json.dumps({"races": [{"id": "7", "legs": legs}]}))
    order = sorted(boats, key=lambda b: boats[b][2])
    (race / "results.json").write_text(json.dumps({"results": [
        {"boat_id": b, "boat_name": f"Boat {b}", "position": order.index(b) + 1} for b in boats]}))
    for k in (1, 2):
        rows = []
        for b, (_, t1, t2) in boats.items():
            span = {"start": t0, "end": t1} if k == 1 else {"start": t1, "end": t2}
            wind = {"direction": {"mean": 350.0}, "speed": {"mean": 10.0}}
            rows.append({"boat_id": b, "boat_name": f"Boat {b}", "requested_leg": {"time_range": span, "wind_context": wind}})
        (race / f"leg_{k}.json").write_text(json.dumps({"results": rows}))


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write_race(root)
    table, marks, trk = model.build(root)

    # 1 roundings: rank and gap at mark 1
    leg1 = table[table["leg"] == 1].set_index("boat_id")
    assert list(leg1.sort_values("rank_at_mark").index) == ["1", "2", "3"]
    assert leg1.loc["3", "behind_s"] == 100 and leg1.loc["2", "gained_s"] == 0 and leg1.loc["1", "gained_s"] == 50

    # 2 mark 1 recovered from the rounding positions (within 5 m of (0, 1000))
    m1 = marks[marks["mark"] == 1].iloc[0]
    x, y = model._to_metres(m1["lat"], m1["lng"], LAT0, LNG0)
    assert abs(x) < 5 and abs(y - 1000) < 5, (x, y)

    # 4 approach: boat 1 far left = aggressive, boat 2 a little right = conservative
    assert (leg1.loc["1", "side"], leg1.loc["1", "style"]) == ("Left", "Aggressive")
    assert (leg1.loc["2", "side"], leg1.loc["2", "style"]) == ("Right", "Conservative")
    assert abs(leg1.loc["1", "offset"] - 0.4) < 0.02

    # 3 snapshots: winner leads by the end of the beat
    snap = model.snapshots("100", "7", table, trk, marks)
    assert snap[snap["minute"] == 9].set_index("boat_id").loc["1", "rank"] == 1
    assert (snap[snap["boat_id"] == "1"]["behind_winner_m"] == 0).all()

    # 5 summary + model run on the joined table
    assert set(model.summary(table)["style"]) == {"Aggressive", "Conservative"}
    result = model.fit(table)
    assert result["test_rows"] == 2 and result["train_rows"] == 4

print("race_model ok")
