"""First-beat analysis of the SailSync ILCA 7 tracks (San Pedro, 19 July 2026).

For each race: the fleet's average move in the first minutes after the start
gives the upwind axis. Each boat's sideways distance from that axis tells
which side of the course it sailed. We compare the four winners with the fleet.
"""

import json
import math
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent.parent / "sailsync_api_results"
BEAT_MINUTES = 8  # long enough to commit to a side, short enough to stay on beat 1


def load_tracks():
    """{name: DataFrame(time_epoch, lat, lng)} with a 'winner' flag per name."""
    tracks, winners = {}, set()
    for path in sorted(RESULTS.rglob("*.csv")):
        name = " ".join(path.stem.split("_")[2:-2]) or path.stem
        tracks[name] = pd.read_csv(path).sort_values("time_epoch").reset_index(drop=True)
        if path.parent.name == "winners":
            winners.add(name)
    return tracks, winners


def race_starts():
    report = json.loads((RESULTS / "probe_report.json").read_text())
    session = report["events"][0]["matching_sessions"][0]["assignment"]
    return [(race["label"], race["time_range"]["start"]) for race in session["races"]], session


def _position(track, t):
    index = int(track["time_epoch"].searchsorted(t))
    if index == 0 or index >= len(track):
        return None
    row = track.iloc[index]
    if abs(row["time_epoch"] - t) > 30:  # gap in the log
        return None
    return float(row["lat"]), float(row["lng"])


def _to_metres(lat, lng, lat0, lng0):
    return (lng - lng0) * 111_320 * math.cos(math.radians(lat0)), (lat - lat0) * 110_540


def first_beat(tracks, winners, start):
    """Sideways offset (m, + = right looking upwind) of every boat after BEAT_MINUTES."""
    later = start + BEAT_MINUTES * 60
    pairs = {name: (_position(t, start), _position(t, later)) for name, t in tracks.items()}
    pairs = {name: p for name, p in pairs.items() if p[0] and p[1]}
    if len(pairs) < 5:
        return None
    lat0 = sum(p[0][0] for p in pairs.values()) / len(pairs)
    lng0 = sum(p[0][1] for p in pairs.values()) / len(pairs)
    moves = {name: _to_metres(*p[1], lat0, lng0) for name, p in pairs.items()}
    ax = sum(x for x, _ in moves.values()) / len(moves)
    ay = sum(y for _, y in moves.values()) / len(moves)
    length = math.hypot(ax, ay) or 1.0
    ux, uy = ax / length, ay / length
    offsets = {name: x * uy - y * ux for name, (x, y) in moves.items()}  # right-hand normal
    fleet = sorted(offsets.values())
    median = fleet[len(fleet) // 2]
    winner_offsets = {name: offsets[name] for name in winners if name in offsets}
    winner_mean = sum(winner_offsets.values()) / len(winner_offsets) if winner_offsets else None
    side = None
    if winner_mean is not None:
        side = "Right" if winner_mean - median > 25 else "Left" if winner_mean - median < -25 else "Middle"
    return {
        "upwind_bearing": (math.degrees(math.atan2(ux, uy)) + 360) % 360,
        "boats": len(offsets),
        "fleet_median_m": median,
        "winner_offsets": winner_offsets,
        "winner_side": side,
        "offsets": offsets,
    }


def summary():
    """Per-race first-beat result plus an overall verdict."""
    tracks, winners = load_tracks()
    starts, session = race_starts()
    races = []
    for label, start in starts:
        result = first_beat(tracks, winners, start)
        if result:
            races.append({"race": label, **result})
    sides = [race["winner_side"] for race in races if race["winner_side"]]
    verdict = max(set(sides), key=sides.count) if sides else None
    return {"date": session["date"], "boat_class": session["boat_class"], "races": races,
            "winners": sorted(winners), "fleet_size": len(tracks), "verdict": verdict,
            "agreement": sides.count(verdict) if verdict else 0}
