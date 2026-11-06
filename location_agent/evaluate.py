#!/usr/bin/env python3
"""
Step 5 - evaluate a strategy against what really happened (race 1 by default, full course).

    python -m location_agent.evaluate --date 2026-07-19                         # newest strategy file
    python -m location_agent.evaluate --date 2026-07-19 --strategy <strategy_*.json>
    python -m location_agent.evaluate --date 2026-07-19 --rerun --provider mock --note "what I changed"
    python -m location_agent.evaluate --date 2026-07-19 --races 1,2,3

(A) Decisions vs the REAL fleet (44 SailSync tracks), first beat: which side and which end of the line
    paid, and the real shift pattern (wind from the boats' tacking angles).
(B) Full race: our action_plan is sailed over every leg of the course by the rule-following simulator.
    Our positions are written at EXACTLY the timestamps of the race winner's real track (gun -> its
    finish), so both can be plotted together. Times at each mark are compared with the 4 winners' real
    tracks (where their trackers had data) and the finish with all real finishers.
    Our boat sails a simplified world (uniform wind, constant speeds, no other boats); the winners' times
    are real, so time gaps include that simplification.

Iteration is manual: read evaluation.md, change prompt / settings / features (never race-specific
facts), re-run with --rerun --note "...". Each run appends one line to output/iterations.md.
Writes output/<date>_<area>/evaluation.{json,md} and sim/ (SailSync CSV format).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import simulate as sim

PKG = Path(__file__).resolve().parent
OUT_ROOT = PKG / "output"
SIDE_MARGIN_M = 50           # "side paid" needs the leaders this much further to one side than the rest
END_MARGIN = 0.15            # "end paid" needs the leaders' line position this much (0..1) toward one end
TOP_N = 10                   # leaders = first TOP_N boats


def r(x, nd=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def hms(s):
    return None if s is None else f"{int(s) // 60}:{int(s) % 60:02d}"


def progress_ranking(fleet, rows, gun, course, at_s, wind):
    """Upwind distance still to go to mark 1 (along the wind, as race trackers rank) at gun + at_s, for every
    boat tracked then - tracker gaps hide many real roundings, so this ranks far more boats."""
    out = []
    tt = gun + at_s
    up = sim.unit(wind.at(tt)[0])
    for rb in rows:
        raw = fleet.raw[rb["boat"]]
        t = raw.time_epoch.to_numpy(dtype=float)
        if t[0] <= tt <= t[-1] and np.min(np.abs(t - tt)) <= 30:
            p = np.array([np.interp(tt, t, raw.x), np.interp(tt, t, raw.y)])
            b = fleet.boats[rb["boat"]]
            t0 = pd.Timestamp(gun, unit="s", tz="UTC").tz_convert(sim.TZ)
            seg = b[(b.index >= t0) & (b.index <= t0 + pd.Timedelta(seconds=at_s))]
            lat = (seg[["x", "y"]].to_numpy() - course["centre"]) @ sim.unit(course["rhumb_deg"] + 90)
            out.append({**rb, "dist_to_mark_m": float((course["mark"] - p) @ up),
                        "lateral_mean_m": float(lat.mean()) if len(lat) else float("nan")})
    return sorted(out, key=lambda x: x["dist_to_mark_m"])


def shift_pattern(wind: sim.Wind, gun, minutes=45):
    m = (wind.t >= gun) & (wind.t <= gun + minutes * 60)
    if m.sum() < 5:
        return {}
    t, d = (wind.t[m] - gun) / 3600, wind.twd[m]
    un = d[0] + np.cumsum(np.r_[0, sim.angdiff(d[1:], d[:-1])])
    k = np.polyfit(t, un, 1)
    sd = float((un - np.polyval(k, t)).std())
    turn = float(k[0]) * minutes / 60
    # evaluation rule (stated): persistent if the turn over the race is >= 2x the swing SD; a trend if >= 1x
    if abs(turn) >= 2 * sd:
        label = "persistent_right" if turn > 0 else "persistent_left"
    elif abs(turn) >= sd:
        label = "oscillating_with_right_trend" if turn > 0 else "oscillating_with_left_trend"
    else:
        label = "oscillating"
    return {"trend_deg_per_h": r(k[0]), "swing_sd_deg": r(sd), "turn_over_race_deg": r(turn), "label": label,
            "rule": "persistent if turn over 45 min >= 2x swing SD; 'with trend' if >= 1x"}


def side_word(x, margin):
    return "right" if x > margin else "left" if x < -margin else "middle"


def first_beat_decisions(fleet, wind, gun, course, answer, plan):
    """(A) what really paid on the first beat, and whether the strategy called it."""
    rows = [rb for n in fleet.boats if (rb := sim.real_first_beat(fleet, n, gun, course))]
    real_t = [x["real_time_to_mark_s"] for x in rows if x["real_time_to_mark_s"]]
    at_s = 0.8 * float(np.median(real_t)) if real_t else 540.0
    rank = progress_ranking(fleet, rows, gun, course, at_s, wind)
    both = [x for x in rank if x["real_time_to_mark_s"]]
    rho_check = spearmanr([x["dist_to_mark_m"] for x in both], [x["real_time_to_mark_s"] for x in both])[0] if len(both) > 5 else float("nan")
    top, rest = rank[:TOP_N], rank[TOP_N:]
    d_lat = np.nanmean([x["lateral_mean_m"] for x in top]) - np.nanmean([x["lateral_mean_m"] for x in rest]) if rest else float("nan")
    d_pos = np.mean([x["line_position"] for x in top]) - np.mean([x["line_position"] for x in rest]) if rest else float("nan")
    real = {"boats_ranked": len(rank), "ranked_at_s_after_gun": round(at_s),
            "ranking_vs_real_rounding_order_spearman": r(rho_check, 2), "boats_with_real_rounding": len(both),
            "leaders_minus_rest_lateral_m": r(d_lat, 0), "leaders_minus_rest_line_position": r(d_pos, 2),
            "side_paid": side_word(d_lat, SIDE_MARGIN_M), "end_paid": side_word(d_pos, END_MARGIN),
            "leaders": [x["boat"] for x in top[:5]], "shift_pattern": shift_pattern(wind, gun)}
    q3 = {"south_left_end": "left", "north_right_end": "right", "square": "middle"}.get(answer["q3_start"]["favoured_end"], "unclear")
    strat = {"q1_side": answer["q1_favoured_side"]["side"], "q1_confidence": answer["q1_favoured_side"]["confidence"],
             "q2_pattern": answer["q2_shift_pattern"]["pattern"], "q3_end": q3,
             "plan_target_side": plan["upwind"]["target_side"], "plan_line_position": plan["start"]["line_position"]}
    match = {"side": strat["q1_side"] == real["side_paid"], "start_end": q3 == real["end_paid"],
             "shift_pattern": strat["q2_pattern"] == real["shift_pattern"].get("label"),
             "plan_side": strat["plan_target_side"] == real["side_paid"]}
    return real, strat, match


def evaluate_race(fleet, wind, date, ri, gun, plan, answer, out_dir):
    course = sim.course_race(date, ri)
    bm = sim.boat_model(fleet, gun)
    real, strat, match = first_beat_decisions(fleet, wind, gun, course, answer, plan)

    # ---------- (B) full race: our boat
    lp = float(np.clip(plan["start"]["line_position"], 0, 1))
    start_xy = course["left"] + lp * (course["right"] - course["left"])
    ag = sim.sail_race(start_xy, plan["start"]["first_tack"], gun, wind, bm, course, sim.PlanPolicy(plan, gun))

    # ---------- real boats: whole race (all 44 for the finish order, details for the 4 winners)
    reals = {n: sim.real_race(fleet, n, gun, course) for n in fleet.boats}
    winners = sorted((reals[n] for n in fleet.winners), key=lambda x: x["finish_s"] if x["finish_s"] else 1e9)
    race_winner = winners[0] if winners and winners[0]["finish_s"] else None
    finishers = sorted(x["finish_s"] for x in reals.values() if x["finish_s"])

    # ---------- outputs: our positions at the race winner's timestamps (gun -> its finish)
    sim_dir = out_dir / "sim"
    sim_dir.mkdir(exist_ok=True)
    for old in sim_dir.glob(f"race{ri}_ghost_*.csv"):          # ghosts are no longer used
        old.unlink()
    sim.write_track(sim_dir / f"race{ri}_agent_full.csv", ag["track"])
    aligned = None
    if race_winner:
        raw = fleet.raw[race_winner["boat"]]
        ts = raw.time_epoch[(raw.time_epoch >= gun) & (raw.time_epoch <= gun + race_winner["finish_s"])].to_numpy()
        aligned = sim.at_timestamps(ag["track"], ts)
        aligned.round({"lat": 7, "lng": 7}).to_csv(sim_dir / f"race{ri}_agent.csv", index=False)
    (sim_dir / f"race{ri}_course.json").write_text(json.dumps({
        "race": ri, "gun_epoch": gun,
        "start_line": [list(sim.to_latlon(course["left"])), list(sim.to_latlon(course["right"]))],
        "legs": [{"leg": i + 1, "type": lg["type"], "to": lg["to"], "mark_lat_lon": list(sim.to_latlon(lg["mark"])),
                  "uncertain": lg["uncertain"], "spread_m": lg["spread_m"]} for i, lg in enumerate(course["legs"])]},
        indent=1), encoding="utf-8")
    leg_rows = [{"boat": "OUR BOAT (sim)", **lg} for lg in ag["legs"]]
    for w in winners:
        leg_rows += [{"boat": w["boat"] + " (real)", **lg} for lg in w["legs"]]
    pd.DataFrame(leg_rows).to_csv(sim_dir / f"race{ri}_legs.csv", index=False)

    a_fin = ag["finish_s"]
    simres = {
        "agent": {"finished": ag["finished"], "finish_s": a_fin, "finish": hms(a_fin), "legs": ag["legs"],
                  "tacks_and_gybes": ag["turns"],
                  "indicative_rank_vs_real_finishers": (1 + sum(t < a_fin for t in finishers)) if a_fin else None,
                  "real_finishers_seen": len(finishers)},
        "race_winner": {"boat": race_winner["boat"], "finish_s": race_winner["finish_s"], "finish": hms(race_winner["finish_s"]),
                        "timestamps_used": int(len(aligned)) if aligned is not None else 0} if race_winner else None,
        "winners_real": [{"boat": w["boat"], "finish_s": w["finish_s"], "finish": hms(w["finish_s"]), "legs": w["legs"],
                          "gap_agent_minus_winner_s": (a_fin - w["finish_s"]) if a_fin and w["finish_s"] else None}
                         for w in winners],
        "boat_model": {k: r(v, 2) for k, v in bm.__dict__.items()},
    }
    return {"race": ri, "gun_local": f"{pd.Timestamp(gun, unit='s', tz='UTC').tz_convert(sim.TZ):%H:%M:%S}",
            "course": {"legs": [f"{lg['type']} -> {lg['to']}{' (uncertain)' if lg['uncertain'] else ''}" for lg in course["legs"]],
                       "mark_1_method": course["mark_method"], "mark_1_uncertainty_m": course["mark_uncertainty_m"]},
            "real_fleet_first_beat": real, "strategy": strat, "match": match, "full_race": simres}


def markdown(res: dict) -> str:
    L = [f"# Evaluation - {res['date']} ({res['area']})", f"Strategy: `{res['strategy_file']}` - model {res['model']}", "",
         "Our boat sails the strategy's action plan over the whole course in a simplified simulator (wind from the "
         "boats' tacking, the same everywhere; constant speeds measured from the fleet; no other boats). The winners' "
         "times are real, so time gaps include that simplification.", ""]
    for x in res["races"]:
        rf, st, fr = x["real_fleet_first_beat"], x["strategy"], x["full_race"]
        tick = lambda ok: "✅" if ok else "❌"  # noqa: E731
        ag = fr["agent"]
        L += [f"## Race {x['race']} (gun {x['gun_local']})", "",
              f"**Course:** {' → '.join(x['course']['legs'])}", "",
              "### (A) What really paid on the first beat (all real boats)",
              "| | Real fleet | Strategy |", "|---|---|---|",
              f"| Side | {rf['side_paid']} ({rf['leaders_minus_rest_lateral_m']} m) | {st['q1_side']} {tick(x['match']['side'])} |",
              f"| Start end | {rf['end_paid']} ({rf['leaders_minus_rest_line_position']}) | {st['q3_end']} {tick(x['match']['start_end'])} |",
              f"| Shifts | {rf['shift_pattern'].get('label')} (trend {rf['shift_pattern'].get('trend_deg_per_h')}°/h, "
              f"SD {rf['shift_pattern'].get('swing_sd_deg')}°) | {st['q2_pattern']} {tick(x['match']['shift_pattern'])} |", "",
              "### (B) Full race: our boat (simulated) vs the winners (real)",
              "Time from the gun when within 80 m of each mark (m:ss). '–' = the real tracker had no data there.", ""]
        hdr = ["Boat"] + [f"L{lg['leg']} {lg['type']}→{lg['to']}" for lg in ag["legs"]] + ["Finish"]
        L += ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
        L.append("| **Our boat (sim)** | " + " | ".join(f"{hms(lg['within_80m_s']) or '–'}" for lg in ag["legs"])
                 + f" | **{ag['finish'] or 'not finished'}** |")
        for w in fr["winners_real"]:
            L.append(f"| {w['boat']} (real) | " + " | ".join(f"{hms(lg['within_80m_s']) or '–'}" for lg in w["legs"])
                     + f" | {w['finish'] or '–'} |")
        rw = fr["race_winner"]
        L += ["",
              f"- **Race winner (of the 4 winner files):** {rw['boat']} in {rw['finish']}." if rw else "- Race winner: not found.",
              f"- **Our boat:** finish {ag['finish']}; {ag['tacks_and_gybes']} tacks/gybes in total; indicative rank "
              f"{ag['indicative_rank_vs_real_finishers']} of {ag['real_finishers_seen'] + 1} against the real boats whose finish "
              f"was visible.",
              "- **Gap to each winner (our sim finish − real finish):** "
              + ", ".join(f"{w['boat'].split(' (')[0].split()[-1]} {w['gap_agent_minus_winner_s']:+d} s" for w in fr["winners_real"]
                          if w["gap_agent_minus_winner_s"] is not None),
              f"- **Boat model (measured from the fleet):** {fr['boat_model']}", "",
              f"Files: `sim/race{x['race']}_agent.csv` = our positions at the race winner's {rw['timestamps_used'] if rw else 0} "
              f"timestamps (gun → its finish); `sim/race{x['race']}_agent_full.csv` = our 2 s track; "
              f"`sim/race{x['race']}_course.json` = marks; `sim/race{x['race']}_legs.csv` = leg table.", ""]
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="2026-07-19")
    p.add_argument("--area", default="port_la_course", choices=["port_la_course"])
    p.add_argument("--races", default="1", help="races to evaluate, e.g. 1 or 1,2,3 (default 1)")
    p.add_argument("--strategy", help="strategy_*.json to evaluate (default: newest in the output folder)")
    p.add_argument("--rerun", action="store_true", help="run the strategist first (backtest), then evaluate")
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--note", default="", help="what changed since the last run (goes to output/iterations.md)")
    a = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    out_dir = OUT_ROOT / f"{a.date}_{a.area}"
    if a.rerun:
        cmd = [sys.executable, "-m", "location_agent.strategist", "--date", a.date, "--area", a.area]
        cmd += ["--provider", a.provider] if a.provider else []
        cmd += ["--model", a.model] if a.model else []
        subprocess.run(cmd, check=True, cwd=PKG.parent)
    sf = Path(a.strategy) if a.strategy else max(out_dir.glob("strategy_*.json"), key=lambda f: f.stat().st_mtime)
    st = json.loads(sf.read_text(encoding="utf-8"))
    answer = st["answer"]
    if "action_plan" not in answer:
        sys.exit(f"{sf.name} has no action_plan (made before the action-plan schema) - re-run the strategist.")
    probe = json.loads((sim.TRACK_DIR / "probe_report.json").read_text())
    sess = next(s["assignment"] for s in probe["events"][0]["matching_sessions"] if s["assignment"]["date"] == a.date)
    fleet = sim.load_fleet(sess["session_id"])
    wind = sim.truth_wind(fleet)
    wanted = {int(x) for x in a.races.split(",")}
    races = [evaluate_race(fleet, wind, a.date, i, rc["time_range"]["start"], answer["action_plan"], answer, out_dir)
             for i, rc in enumerate(sess["races"], 1) if i in wanted]
    res = {"date": a.date, "area": a.area, "strategy_file": sf.name, "model": st["run"].get("served_by"),
           "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "races": races}
    (out_dir / "evaluation.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    (out_dir / "evaluation.md").write_text(markdown(res), encoding="utf-8")
    log = OUT_ROOT / "iterations.md"
    head = ("# Iteration log\n\n| When | Strategy | Note | Races | Side ✓ | Start ✓ | Shifts ✓ | Our finish | "
            "Race winner finish | Rank vs real finishers |\n|---|---|---|---|---|---|---|---|---|---|\n")
    if not log.exists() or "Race winner finish" not in log.read_text(encoding="utf-8"):
        log.write_text(head, encoding="utf-8")                         # new format (full race)
    f = lambda k: "/".join("✓" if x["match"][k] else "✗" for x in races)  # noqa: E731
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"| {res['created']} | {sf.name} | {a.note or '-'} | {a.races} | {f('side')} | {f('start_end')} | "
                 f"{f('shift_pattern')} | " + "/".join(str(x["full_race"]["agent"]["finish"]) for x in races) + " | "
                 + "/".join(str((x["full_race"]["race_winner"] or {}).get("finish")) for x in races) + " | "
                 + "/".join(str(x["full_race"]["agent"]["indicative_rank_vs_real_finishers"]) for x in races) + " |\n")
    print(markdown(res))
    print("->", (out_dir / "evaluation.md").relative_to(PKG.parent))


if __name__ == "__main__":
    main()
