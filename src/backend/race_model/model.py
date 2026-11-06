"""Race model: where boats are, which approach they took, and what it gained.

Reads data/race_model/ (filled by fetch_data.py). Steps follow the whiteboard:
  1 legs()            time each boat rounds each mark, its rank and gap to the leader there
  2 mark_positions()  buoy position = median GPS position of the boats at their rounding time
  3 snapshots()       every minute: each boat's distance still to sail -> ranking during the race
  4 approaches()      per boat per leg: side of the course and how far out (aggressive / conservative)
  5 fit()             seconds gained on a leg ~ approach x wind shift; trained without the race
                      winners, tested on them (winner = benchmark / test data)

Run: .venv/bin/python -m backend.race_model.model
"""

import json
import math

import numpy as np
import pandas as pd

from backend import paths
from backend.race_analysis import _to_metres
from backend.strategy import angle_diff

DATA = paths.RACE_MODEL_DIR
AGGRESSIVE = 0.25  # furthest point >= 25% of the leg length away from the straight line


def legs(data=DATA):
    """One row per boat per leg: times, rank and gap at the mark, seconds gained on the leg."""
    rows = []
    for analysis_file in sorted(data.glob("*/analysis.json")):
        session = analysis_file.parent
        analysis = json.loads(analysis_file.read_text())
        directions = {(r["id"], g["leg_index"]): g.get("direction") for r in analysis.get("races", []) for g in r["legs"]}
        for results_file in sorted(session.glob("*/results.json")):
            race = results_file.parent.name
            final = {r["boat_id"]: r for r in json.loads(results_file.read_text())["results"]}
            for leg_file in sorted(results_file.parent.glob("leg_*.json")):
                k = int(leg_file.stem.split("_")[1])
                for r in json.loads(leg_file.read_text())["results"]:
                    leg = r.get("requested_leg") or {}
                    span, wind = leg.get("time_range") or {}, leg.get("wind_context") or {}
                    if span.get("start") is None or span.get("end") is None:
                        continue  # boat did not sail (or finish) this leg
                    rows.append({
                        "session": session.name, "race": race, "boat_id": r["boat_id"],
                        "name": r.get("boat_name", r["boat_id"]), "position": final.get(r["boat_id"], {}).get("position"),
                        "leg": k, "direction": directions.get((race, k)),
                        "t_start": span["start"], "t_end": span.get("end_precise") or span["end"],
                        "wind_dir": (wind.get("direction") or {}).get("mean"),
                        "wind_kt": (wind.get("speed") or {}).get("mean"),
                    })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    by_leg = df.groupby(["session", "race", "leg"])
    df["rank_at_mark"] = by_leg["t_end"].rank(method="min").astype(int)
    df["behind_s"] = df["t_end"] - by_leg["t_end"].transform("min")
    df["behind_entry_s"] = df["t_start"] - by_leg["t_start"].transform("min")
    # + = faster over this leg than the typical boat (leg 1 starts level, so this is the fleet median, not the leader)
    df["gained_s"] = by_leg["t_end"].transform("median") - by_leg["t_start"].transform("median") - (df["t_end"] - df["t_start"])
    return df.sort_values(["session", "race", "leg", "rank_at_mark"]).reset_index(drop=True)


def tracks(session, data=DATA):
    """{boat_id: DataFrame(time_epoch, lat, lng)} for the boats downloaded in this session."""
    return {p.stem: pd.read_csv(p).sort_values("time_epoch") for p in sorted((data / str(session) / "tracks").glob("*.csv"))}


def position_at(track, t):
    """(lat, lng) at time t, interpolated; None outside the track."""
    if track.empty or not track["time_epoch"].iloc[0] <= t <= track["time_epoch"].iloc[-1]:
        return None
    return (np.interp(t, track["time_epoch"], track["lat"]), np.interp(t, track["time_epoch"], track["lng"]))


def mark_positions(legs_df, tracks_by_session):
    """Median position of the boats at each rounding. Mark 0 = start (positions at the gun)."""
    rows = []
    for (session, race), race_legs in legs_df.groupby(["session", "race"]):
        trk = tracks_by_session.get(session, {})
        first = race_legs[race_legs["leg"] == race_legs["leg"].min()]
        moments = [(0, first["boat_id"], first["t_start"])]
        moments += [(k, g["boat_id"], g["t_end"]) for k, g in race_legs.groupby("leg")]
        for mark, boats, times in moments:
            spots = [position_at(trk[b], t) for b, t in zip(boats, times) if b in trk]
            spots = [s for s in spots if s]
            if spots:
                lat, lng = np.median(spots, axis=0)
                rows.append({"session": session, "race": race, "mark": mark, "lat": lat, "lng": lng, "n_boats": len(spots)})
    return pd.DataFrame(rows)


def _marks_xy(marks, session, race):
    m = marks[(marks["session"] == session) & (marks["race"] == race)].sort_values("mark")
    lat0, lng0 = m["lat"].iloc[0], m["lng"].iloc[0]
    return {r.mark: np.array(_to_metres(r.lat, r.lng, lat0, lng0)) for r in m.itertuples()}, (lat0, lng0)


def approaches(legs_df, tracks_by_session, marks):
    """Per boat per leg: side (left/right looking along the leg), how far out, and the label."""
    rows = []
    for r in legs_df.itertuples():
        trk = tracks_by_session.get(r.session, {}).get(r.boat_id)
        xy, origin = _marks_xy(marks, r.session, r.race)
        if trk is None or r.leg not in xy or (r.leg - 1) not in xy:
            continue
        a, b = xy[r.leg - 1], xy[r.leg]
        length = np.linalg.norm(b - a)
        on_leg = trk[(trk["time_epoch"] >= r.t_start) & (trk["time_epoch"] <= r.t_end)]
        if on_leg.empty or length < 50:
            continue
        x, y = _to_metres(on_leg["lat"].to_numpy(), on_leg["lng"].to_numpy(), *origin)
        axis = (b - a) / length
        lateral = axis[0] * (y - a[1]) - axis[1] * (x - a[0])  # + = left of the straight line
        far = lateral[np.argmax(np.abs(lateral))]
        bearing = math.degrees(math.atan2(axis[0], axis[1])) % 360
        rows.append({
            "session": r.session, "race": r.race, "boat_id": r.boat_id, "leg": r.leg,
            "side": "Left" if far > 0 else "Right", "offset": far / length,
            "style": "Aggressive" if abs(far) / length >= AGGRESSIVE else "Conservative",
            "leg_bearing": bearing, "leg_m": length,
        })
    return pd.DataFrame(rows)


def snapshots(session, race, legs_df, tracks_by_session, marks, every_s=60):
    """Every `every_s` seconds: each boat's leg, distance still to sail, rank, and metres behind the winner."""
    race_legs = legs_df[(legs_df["session"] == session) & (legs_df["race"] == race)]
    xy, origin = _marks_xy(marks, session, race)
    last = max(xy)
    remaining = {k: sum(np.linalg.norm(xy[j] - xy[j - 1]) for j in range(k + 1, last + 1)) for k in xy}
    start, end = race_legs["t_start"].min(), race_legs["t_end"].max()
    winner = race_legs.loc[race_legs["position"] == 1, "boat_id"]
    rows = []
    for t in np.arange(start, end, every_s):
        for boat_id, boat_legs in race_legs.groupby("boat_id"):
            now = boat_legs[(boat_legs["t_start"] <= t) & (boat_legs["t_end"] > t)]
            pos = position_at(tracks_by_session.get(session, {}).get(boat_id, pd.DataFrame()), t)
            if now.empty or pos is None or now["leg"].iloc[0] not in xy:
                continue
            k = now["leg"].iloc[0]
            here = np.array(_to_metres(pos[0], pos[1], *origin))
            rows.append({"minute": round((t - start) / 60), "boat_id": boat_id, "leg": k,
                         "to_go_m": np.linalg.norm(xy[k] - here) + remaining[k]})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["rank"] = df.groupby("minute")["to_go_m"].rank(method="min").astype(int)
    if not winner.empty:
        ref = df[df["boat_id"] == winner.iloc[0]].set_index("minute")["to_go_m"]
        df["behind_winner_m"] = df["to_go_m"] - df["minute"].map(ref)
    return df


def summary(table):
    """Whiteboard view: per leg type x approach, how often it gained and the average gain."""
    return (table.groupby(["direction", "side", "style"])["gained_s"]
            .agg(legs="count", gained_pct=lambda s: round(100 * (s > 0).mean()), avg_gain_s="mean")
            .round(1).reset_index())


FEATURES = ["offset", "far_out", "offset_x_shift"]


def features(table):
    """Inputs for fit(): side and distance out, and side combined with the wind shift on that leg."""
    shift = [angle_diff(b, w) if pd.notna(w) else 0.0 for b, w in zip(table["leg_bearing"], table["wind_dir"])]
    return pd.DataFrame({"offset": table["offset"], "far_out": table["offset"].abs(),
                         "offset_x_shift": table["offset"] * np.array(shift) / 10})


def fit(table):
    """Least squares gained_s ~ FEATURES on non-winners; tested on the race winners (benchmark)."""
    train, test = table[table["position"] != 1], table[table["position"] == 1]
    X = np.column_stack([np.ones(len(train)), features(train)])
    coef, *_ = np.linalg.lstsq(X, train["gained_s"].to_numpy(), rcond=None)
    predict = lambda t: np.column_stack([np.ones(len(t)), features(t)]) @ coef  # noqa: E731
    test_error = float(np.mean(np.abs(predict(test) - test["gained_s"]))) if len(test) else None
    return {"coef": dict(zip(["base", *FEATURES], coef.round(2))), "train_rows": len(train),
            "test_rows": len(test), "test_mae_s": test_error, "predict": predict}


def build(data=DATA):
    """Everything joined: one row per boat per leg with times, approach and gain."""
    leg_table = legs(data)
    if leg_table.empty:
        raise SystemExit(f"No data in {data}. Run: python -m backend.race_model.fetch_data")
    trk = {s: tracks(s, data) for s in leg_table["session"].unique()}
    marks = mark_positions(leg_table, trk)
    table = leg_table.merge(approaches(leg_table, trk, marks), on=["session", "race", "boat_id", "leg"])
    return table, marks, trk


if __name__ == "__main__":
    table, marks, _ = build()
    print("Mark positions (median at rounding):\n", marks.round(5).to_string(index=False))
    print("\nApproach vs gain:\n", summary(table).to_string(index=False))
    result = fit(table)
    print("\nModel:", {k: v for k, v in result.items() if k != "predict"})
