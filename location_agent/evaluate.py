#!/usr/bin/env python3
"""
Step 5 - evaluate a strategy against what really happened (first beat of every race of the day).

    python -m location_agent.evaluate --date 2026-07-19                         # newest strategy file
    python -m location_agent.evaluate --date 2026-07-19 --strategy <strategy_*.json>
    python -m location_agent.evaluate --date 2026-07-19 --rerun --provider mock --note "what I changed"

(A) Decisions vs the REAL fleet (44 SailSync tracks): which side and which end of the line paid, and
    the real shift pattern (wind from the boats' tacking angles).
(B) Route vs route in the SIMULATOR: our action_plan is sailed by a rule-following boat, every real
    boat is replayed as a ghost (own gun position + tack times) in the same wind -> our rank and
    time gap vs the fleet and the winners. Calibration (ghost time vs real time) says whether the
    simulated times can be trusted.

Race 1 = "tuning" race, races 2-3 = "check" races (same day, so weak proof - see README).
Iteration is manual: read evaluation.md, change prompt / settings / features (never race-specific
facts), re-run with --rerun --note "...". Each run appends one line to output/iterations.md.
Writes output/<date>_<area>/evaluation.{json,md} and sim/ tracks (SailSync CSV format).
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
CALIBRATION_OK_PCT = 5.0     # simulated times are compared only if ghosts match real times this well (median |err|)
SIDE_MARGIN_M = 50           # "side paid" needs the leaders this much further to one side than the rest
END_MARGIN = 0.15            # "end paid" needs the leaders' line position this much (0..1) toward one end
TOP_N = 10                   # leaders = first TOP_N boats


def r(x, nd=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


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


def evaluate_race(fleet, wind, date, ri, gun, plan, answer, out_dir):
    course = sim.course_race(date, ri)
    bm = sim.boat_model(fleet, gun)
    rows = [rb for n in fleet.boats if (rb := sim.real_first_beat(fleet, n, gun, course))]
    # ---------- (A) real fleet decisions
    real_t = [x["real_time_to_mark_s"] for x in rows if x["real_time_to_mark_s"]]
    at_s = 0.8 * float(np.median(real_t)) if real_t else 540.0
    rank = progress_ranking(fleet, rows, gun, course, at_s, wind)
    both = [x for x in rank if x["real_time_to_mark_s"]]
    rho_check = spearmanr([x["dist_to_mark_m"] for x in both], [x["real_time_to_mark_s"] for x in both])[0] if len(both) > 5 else float("nan")
    top, rest = rank[:TOP_N], rank[TOP_N:]
    d_lat = np.nanmean([x["lateral_mean_m"] for x in top]) - np.nanmean([x["lateral_mean_m"] for x in rest]) if rest else float("nan")
    d_pos = np.mean([x["line_position"] for x in top]) - np.mean([x["line_position"] for x in rest]) if rest else float("nan")
    rho_lat = spearmanr([x["dist_to_mark_m"] for x in rank], [x["lateral_mean_m"] for x in rank])[0] if len(rank) > 5 else float("nan")
    rho_pos = spearmanr([x["dist_to_mark_m"] for x in rank], [x["line_position"] for x in rank])[0] if len(rank) > 5 else float("nan")
    real = {"boats_ranked": len(rank), "ranked_at_s_after_gun": round(at_s),
            "ranking_vs_real_rounding_order_spearman": r(rho_check, 2), "boats_with_real_rounding": len(both),
            "leaders_minus_rest_lateral_m": r(d_lat, 0), "spearman_distance_vs_lateral": r(rho_lat, 2),
            "leaders_minus_rest_line_position": r(d_pos, 2), "spearman_distance_vs_line_position": r(rho_pos, 2),
            "side_paid": side_word(d_lat, SIDE_MARGIN_M), "end_paid": side_word(d_pos, END_MARGIN),
            "leaders": [x["boat"] for x in top[:5]], "shift_pattern": shift_pattern(wind, gun)}
    # ---------- strategy decisions
    q3 = {"south_left_end": "left", "north_right_end": "right", "square": "middle"}.get(answer["q3_start"]["favoured_end"], "unclear")
    strat = {"q1_side": answer["q1_favoured_side"]["side"], "q1_confidence": answer["q1_favoured_side"]["confidence"],
             "q2_pattern": answer["q2_shift_pattern"]["pattern"], "q3_end": q3,
             "plan_target_side": plan["upwind"]["target_side"], "plan_line_position": plan["start"]["line_position"]}
    match = {"side": strat["q1_side"] == real["side_paid"], "start_end": q3 == real["end_paid"],
             "shift_pattern": strat["q2_pattern"] == real["shift_pattern"].get("label"),
             "plan_side": strat["plan_target_side"] == real["side_paid"]}
    # ---------- (B) simulator: agent vs ghosts
    ghosts = []
    for rb in rows:
        g = sim.sail_first_beat(rb["gun_xy"], rb["first_tack"], gun, wind, bm, course, sim.GhostPolicy(rb["tack_times"]))
        ghosts.append({**rb, "sim_time_s": g["time_to_mark_s"], "sim_track": g["track"]})
    lp = float(np.clip(plan["start"]["line_position"], 0, 1))
    start_xy = course["left"] + lp * (course["right"] - course["left"])
    ag = sim.sail_first_beat(start_xy, plan["start"]["first_tack"], gun, wind, bm, course, sim.PlanPolicy(plan, gun))
    sim_dir = out_dir / "sim"
    sim_dir.mkdir(exist_ok=True)
    sim.write_track(sim_dir / f"race{ri}_agent.csv", ag["track"])
    for g in ghosts:
        if g["winner"]:
            sim.write_track(sim_dir / f"race{ri}_ghost_{g['boat'].split(' (')[0].replace(' ', '_')}.csv", g["sim_track"])
    gt = sorted(x["sim_time_s"] for x in ghosts if x["sim_time_s"] is not None)
    calib = [(x["sim_time_s"] - x["real_time_to_mark_s"]) / x["real_time_to_mark_s"] * 100 for x in ghosts
             if x["sim_time_s"] and x["real_time_to_mark_s"]]
    cal_med = float(np.median(np.abs(calib))) if calib else float("nan")
    a_t = ag["time_to_mark_s"]
    a_lat, a_right = sim.lateral_stats(ag["track"], course)
    simres = {
        "agent": {"time_to_mark_s": r(a_t, 0), "tacks": ag["tacks"], "mean_lateral_m": a_lat, "pct_time_right": a_right,
                  "rank_among_ghosts": (1 + sum(t < a_t for t in gt)) if a_t else None, "of": len(gt) + 1},
        "gap_to_best_ghost_s": r(a_t - gt[0], 0) if a_t and gt else None,
        "gap_to_median_ghost_s": r(a_t - float(np.median(gt)), 0) if a_t and gt else None,
        "winners": [{"boat": g["boat"], "sim_time_s": r(g["sim_time_s"], 0), "real_time_s": r(g["real_time_to_mark_s"], 0),
                     "gap_agent_minus_winner_s": r(a_t - g["sim_time_s"], 0) if a_t and g["sim_time_s"] else None,
                     "line_position": g["line_position"], "mean_lateral_m": g["real_mean_lateral_m"]}
                    for g in ghosts if g["winner"]],
        "boat_model": {"upwind_kn": r(bm.vup_kn, 2), "tack_angle_deg": r(bm.tack_angle, 0), "tack_loss_s": bm.tack_loss_s},
        "calibration": {"boats_with_real_time": len(calib), "median_abs_error_pct": r(cal_med),
                        "median_error_pct": r(float(np.median(calib)) if calib else float("nan")),
                        "times_comparable": bool(calib) and cal_med <= CALIBRATION_OK_PCT},
    }
    lost = simres["agent"]["rank_among_ghosts"] is None or any(
        w["gap_agent_minus_winner_s"] is not None and w["gap_agent_minus_winner_s"] > 0 for w in simres["winners"])
    return {"race": ri, "role": "tuning" if ri == 1 else "check", "gun_local": f"{pd.Timestamp(gun, unit='s', tz='UTC').tz_convert(sim.TZ):%H:%M}",
            "course": {"rhumb_deg": r(course["rhumb_deg"], 0), "mark_1_method": course["mark_method"],
                       "mark_1_uncertainty_m": course["mark_uncertainty_m"]},
            "real_fleet": real, "strategy": strat, "match": match, "simulator": simres,
            "lost_to_a_winner_in_sim": lost}


def markdown(res: dict) -> str:
    L = [f"# Evaluation - {res['date']} ({res['area']})", f"Strategy: `{res['strategy_file']}` - model {res['model']}", "",
         "First beat of each race (gun -> windward mark 1). Race 1 = tuning, races 2-3 = check. The plan is made once in the "
         "morning and used for every race. Same day, same weather, so this is weak proof.", ""]
    L.append("| Race | Role | Real: side paid | Strategy side | Real: end paid | Strategy end | Real shifts | Strategy shifts | "
             "Sim rank | Gap to best ghost | Gap to winners | Sim calibrated |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for x in res["races"]:
        rf, st, sm = x["real_fleet"], x["strategy"], x["simulator"]
        gw = ", ".join(f"{w['boat'].split(' (')[0].split()[-1]} {w['gap_agent_minus_winner_s']:+.0f}s" for w in sm["winners"]
                       if w["gap_agent_minus_winner_s"] is not None)
        tick = lambda ok: "✅" if ok else "❌"  # noqa: E731
        L.append(f"| {x['race']} | {x['role']} | {rf['side_paid']} | {st['q1_side']} {tick(x['match']['side'])} | {rf['end_paid']} | "
                 f"{st['q3_end']} {tick(x['match']['start_end'])} | {rf['shift_pattern'].get('label')} | {st['q2_pattern']} "
                 f"{tick(x['match']['shift_pattern'])} | {sm['agent']['rank_among_ghosts']}/{sm['agent']['of']} | "
                 f"{sm['gap_to_best_ghost_s']} s | {gw} | {sm['calibration']['median_abs_error_pct']} % "
                 f"{'(ok)' if sm['calibration']['times_comparable'] else '(NOT comparable)'} |")
    L += ["", "## Detail"]
    for x in res["races"]:
        rf, sm = x["real_fleet"], x["simulator"]
        L += [f"### Race {x['race']} ({x['gun_local']}, {x['role']})",
              f"- **Real fleet:** {rf['boats_ranked']} boats ranked by upwind distance to go to mark 1 at {rf['ranked_at_s_after_gun']} s "
              f"(agrees with the real rounding order of {rf['boats_with_real_rounding']} boats: Spearman {rf['ranking_vs_real_rounding_order_spearman']}). "
              f"Leaders minus rest: lateral {rf['leaders_minus_rest_lateral_m']} m (+ = right), line position "
              f"{rf['leaders_minus_rest_line_position']} (+ = right end). Leaders: {', '.join(rf['leaders'])}.",
              f"- **Real wind:** trend {rf['shift_pattern'].get('trend_deg_per_h')} deg/h, swing SD "
              f"{rf['shift_pattern'].get('swing_sd_deg')} deg → {rf['shift_pattern'].get('label')}.",
              f"- **Our boat (sim):** {sm['agent']['time_to_mark_s']} s, {sm['agent']['tacks']} tacks, mean lateral "
              f"{sm['agent']['mean_lateral_m']} m, {sm['agent']['pct_time_right']} % of the time right. Rank "
              f"{sm['agent']['rank_among_ghosts']}/{sm['agent']['of']}.",
              "- **Winners (sim / real):** " + "; ".join(f"{w['boat']} {w['sim_time_s']} / {w['real_time_s']} s, line pos "
                                                     f"{w['line_position']}, lateral {w['mean_lateral_m']} m" for w in sm["winners"]),
              f"- **Course:** rhumb {x['course']['rhumb_deg']} deg; mark 1 {x['course']['mark_1_method']} "
              f"(±{x['course']['mark_1_uncertainty_m']} m). Boat model {sm['boat_model']}.", ""]
    L += ["Tracks of our boat and the winners' ghosts: `sim/` (SailSync CSV format)."]
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="2026-07-19")
    p.add_argument("--area", default="port_la_course", choices=["port_la_course"])
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
    races = [evaluate_race(fleet, wind, a.date, i, rc["time_range"]["start"], answer["action_plan"], answer, out_dir)
             for i, rc in enumerate(sess["races"], 1)]
    res = {"date": a.date, "area": a.area, "strategy_file": sf.name, "model": st["run"].get("served_by"),
           "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "races": races}
    (out_dir / "evaluation.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    (out_dir / "evaluation.md").write_text(markdown(res), encoding="utf-8")
    log = OUT_ROOT / "iterations.md"
    if not log.exists():
        log.write_text("# Iteration log\n\n| When | Strategy | Note | Side ✓ (R1/R2/R3) | Start ✓ | Shifts ✓ | Sim rank | "
                       "Gap to best ghost (s) |\n|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    f = lambda k: "/".join("✓" if x["match"][k] else "✗" for x in races)  # noqa: E731
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"| {res['created']} | {sf.name} | {a.note or '-'} | {f('side')} | {f('start_end')} | {f('shift_pattern')} | "
                 + "/".join(str(x["simulator"]["agent"]["rank_among_ghosts"]) for x in races) + " | "
                 + "/".join(str(x["simulator"]["gap_to_best_ghost_s"]) for x in races) + " |\n")
    print(markdown(res))
    print("->", (out_dir / "evaluation.md").relative_to(PKG.parent))


if __name__ == "__main__":
    main()
