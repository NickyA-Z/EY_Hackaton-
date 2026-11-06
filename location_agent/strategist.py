#!/usr/bin/env python3
"""
Step 3 - the AI strategist: briefing pack -> AI model -> strategy JSON + printable briefing card.

    python -m location_agent.strategist --date 2026-07-19 --area port_la_course
    python -m location_agent.strategist --date 2026-07-19 --provider mock          # offline pipeline test
    python -m location_agent.strategist --pack location_agent/output/.../briefing_pack.json

The model / provider / key come from location_agent/.env (see .env.example); --provider and
--model override it for one run. Outputs go next to the briefing pack:
    strategy_<provider>_<model>.json   the full answer + run metadata + checks
    briefing_<provider>_<model>.md     the printable coach card
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

from . import checks
from .features import PKG, ROOT, load_or_build
from .prompt import OUTPUT_SCHEMA
from .providers import generate, load_config


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", s or "none").strip("-")[:40]


def _action_lines(ap: dict | None) -> list[str]:
    if not ap:
        return ["- (none)"]
    s, u = ap["start"], ap["upwind"]
    out = [f"- **Start:** {s['line_position']:.2f} along the line (0 = left end, 1 = right end), "
           f"{s['first_tack']} tack, hold {s['hold_first_tack_s']:.0f} s",
           f"- **Upwind:** go {u['target_side']} up to {u['max_lateral_m']:.0f} m off the rhumb line; tack on headers "
           f">= {u['tack_on_header_deg']:.0f} deg held {u['header_hold_s']:.0f} s; overstand laylines {u['layline_overstand_m']:.0f} m",
           f"- **Downwind:** favour {ap['downwind']['target_side']}"]
    out += [f"- **If** {t['condition']} {t['value']:g} -> side {t['then_target_side']}, tack on {t['then_tack_on_header_deg']:.0f} deg "
            f"({t['why']})" for t in ap.get("triggers", [])]
    return out


def briefing_markdown(ans: dict, pack: dict, meta: dict) -> str:
    c = pack["context"]
    q1, q2, q3 = ans["q1_favoured_side"], ans["q2_shift_pattern"], ans["q3_start"]
    lines = [
        f"# Race-day briefing - {c['venue']}",
        f"**{c['race_day']}, racing {c['race_window_local']} local - {c['boat_class']}**  ",
        f"_Mode: {c['mode']}. Model: {meta.get('served_by')} ({meta.get('provider')})._",
        "",
        ans["briefing_card_markdown"],
        "",
        "## The four questions",
        f"1. **Side:** {q1['side']} (confidence {q1['confidence']})",
        *[f"   - {r['text']}" for r in q1["reasons"]],
        f"2. **Shifts:** {q2['pattern']} - {q2['cycle_or_rate']}",
        *[f"   - {r['text']}" for r in q2["reasons"]],
        f"3. **Start:** {q3['favoured_end']}",
        *[f"   - {r['text']}" for r in q3["reasons"]],
        "4. **If the forecast is wrong:**",
        *[f"   - *{x['scenario']}* - watch: {x['signs_to_watch']} - then: {x['then']}" for x in ans["q4_contingencies"]],
        "",
        f"**First beat:** {ans['first_beat_plan']}",
        "",
        "## Action plan (sailed by the simulator)",
        *_action_lines(ans.get("action_plan")),
        "",
        "## Uncertainty",
        *[f"- {x}" for x in ans["data_gaps_and_uncertainty"]],
    ]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="2026-07-19")
    p.add_argument("--area", default="port_la_course", choices=["port_la_course", "belmont_course"])
    p.add_argument("--window", help="race window, local hours, e.g. 13-17 (default: settings.yaml)")
    p.add_argument("--no-backtest", action="store_true")
    p.add_argument("--pack", help="use this briefing_pack.json file")
    p.add_argument("--rebuild", action="store_true",
                   help="refresh the stored features, but only if their inputs changed (default: use the stored pack)")
    p.add_argument("--provider", choices=["anthropic", "openai_compatible", "mock"])
    p.add_argument("--model")
    a = p.parse_args()

    if a.pack:
        pack_path = Path(a.pack)
        pack, status = json.loads(pack_path.read_text(encoding="utf-8")), "given file"
    else:
        w = tuple(int(x) for x in a.window.split("-")) if a.window else None
        pack, pack_path, status = load_or_build(date.fromisoformat(a.date), a.area, w, backtest=not a.no_backtest,
                                                rebuild=a.rebuild)
    out_dir = pack_path.parent
    print(f"Features: {status} ({pack_path.resolve().relative_to(ROOT)}, fingerprint {pack['context'].get('fingerprint')})")

    # RAG insights: text the RAG produced from the user's inputs; attached now, never stored in the feature pack
    tf = PKG / "inputs" / f"{pack['context']['race_day']}_rag_insights.txt"
    rag = tf.read_text(encoding="utf-8").strip() if tf.exists() else ""
    if rag:
        pack = {**pack, "rag_insights": rag}
    print(f"RAG insights: {f'{len(rag)} characters from {tf.name}' if rag else 'none'}")

    cfg = load_config({"LLM_PROVIDER": a.provider, "LLM_MODEL": a.model})
    print(f"Provider: {cfg['LLM_PROVIDER']}  model: {cfg.get('LLM_MODEL') or '-'}  pack: {pack['context']['race_day']} "
          f"{pack['context']['venue']} ({pack['context']['mode'].split(':')[0]})")
    answer, meta = generate(pack, cfg)

    result = {
        "run": {**meta, "created": datetime.now().strftime("%Y-%m-%d %H:%M")},
        "checks": {"schema_errors": checks.validate(answer, OUTPUT_SCHEMA),
                   "number_trace": checks.trace_numbers(answer, pack)},
        "answer": answer,
    }
    tag = f"{_slug(cfg['LLM_PROVIDER'])}_{_slug(meta.get('served_by') or cfg.get('LLM_MODEL'))}"
    jf, mf = out_dir / f"strategy_{tag}.json", out_dir / f"briefing_{tag}.md"
    jf.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    if not result["checks"]["schema_errors"]:
        mf.write_text(briefing_markdown(answer, pack, meta), encoding="utf-8")

    tr = result["checks"]["number_trace"]
    print(f"Answer: side={answer['q1_favoured_side']['side']} ({answer['q1_favoured_side']['confidence']}), "
          f"shifts={answer['q2_shift_pattern']['pattern']}, start={answer['q3_start']['favoured_end']}")
    print(f"Checks: schema errors={len(result['checks']['schema_errors'])}; cited numbers={tr['cited_numbers']} "
          f"{tr['by_status']}")
    print(f"Run: {meta}")
    print(f"-> {jf.resolve().relative_to(ROOT)}" + (f"\n-> {mf.resolve().relative_to(ROOT)}" if mf.exists() else ""))


if __name__ == "__main__":
    main()
