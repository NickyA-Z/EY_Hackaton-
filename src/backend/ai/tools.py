"""The tools the chat agent may call. Each one wraps a function that already exists. Only build_strategy_plan reaches an LLM,

Every result is JSON ``{"result": ..., "provenance": {...}}`` or ``{"unavailable": reason}``. The agent is told
to state a number only if a tool returned it, and ``verify.untraced_numbers`` checks that after the fact.

The plain functions (``select_strategy_docs`` ...) return dicts and are what the tests compare with the
direct calls; ``build_tools`` wraps them for LangChain. Docstrings are written for the model: LangChain sends
them as the tool description.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, tool

from backend import paths, race_analysis
from backend.rag.triggers import Conditions, select_documents

AREAS = ("port_la_course", "belmont_course")


def _unavailable(reason: str, **extra: Any) -> dict:
    return {"unavailable": reason, **extra}


def select_strategy_docs(conditions: dict) -> dict:
    try:
        selection = select_documents(Conditions.from_dict(conditions))
    except ValueError as error:  # a mistyped key must not become "no information"
        return _unavailable(str(error))
    return {
        "result": {"doc_ids": list(selection.doc_ids), "reasons": selection.reasons,
                   "tiers": selection.tiers, "not_provided": list(selection.missing)},
        "provenance": {"tool": "select_strategy_docs", "data_scope": "synthetic team-strategy corpus data/rag",
                       "deterministic": True},
    }


def search_strategy(question: str, doc_ids: Sequence[str] | None, k: int, store: Any) -> dict:
    try:
        if store.count() == 0:
            return _unavailable("the strategy index is empty; build it with `python -m backend.rag index`")
        hits = store.search(question, k=k, doc_ids=list(doc_ids) if doc_ids else None)
    except Exception as error:  # noqa: BLE001 - a dead embedding key must reach the model as text, not crash the run
        return _unavailable(f"strategy search failed: {type(error).__name__}: {str(error)[:200]}")
    return {
        "result": [{"doc_id": h.doc_id, "section": h.section, "text": h.body} for h in hits],
        "provenance": {"tool": "search_strategy", "data_scope": "synthetic team-strategy corpus data/rag"},
    }


def get_briefing_pack(race_day: str, area: str) -> dict:
    from backend.location_agent.features import pack_path  # noqa: PLC0415 - imports scipy and rasterio

    if area not in AREAS:
        return _unavailable(f"unknown area {area!r}", areas=list(AREAS))
    try:
        day = date.fromisoformat(race_day)
    except ValueError:
        return _unavailable(f"race_day must be YYYY-MM-DD, got {race_day!r}")
    path = pack_path(day, area, True)
    if not path.exists():  # stored packs only: a tool must not build files as a side effect
        have = sorted(p.parent.name for p in paths.LOCATION_AGENT_OUTPUT_DIR.glob("*/briefing_pack.json")
                      if not p.parent.name.endswith("_hindsight"))
        return _unavailable(f"no stored briefing pack for {race_day} {area}", available=have)
    pack = json.loads(path.read_text(encoding="utf-8"))
    return {
        "result": pack,
        "provenance": {"tool": "get_briefing_pack", "data_scope": pack["context"]["mode"],
                       "venue": pack["context"]["venue"], "fingerprint": pack["context"].get("fingerprint")},
    }


def winners_first_beat() -> dict:
    try:
        summary = race_analysis.summary()
    except Exception as error:  # noqa: BLE001 - missing track files must read as "unavailable"
        return _unavailable(f"track analysis failed: {type(error).__name__}: {str(error)[:200]}")
    return {
        "result": summary,
        "provenance": {"tool": "winners_first_beat",
                       "data_scope": f"SailSync GPS, {summary['boat_class']}, {summary['date']}: "
                                     f"{len(summary['winners'])} winners vs a fleet of {summary['fleet_size']}",
                       "telemetry": True},
    }


def get_stored_strategy(race_day: str, area: str) -> dict:
    day_dir = paths.LOCATION_AGENT_OUTPUT_DIR / f"{race_day}_{area}"
    files = sorted(day_dir.glob("strategy_*.json")) if day_dir.is_dir() and area in AREAS else []
    files = [f for f in files if "mock" not in f.name]  # a mock answer is not a strategy
    if not files:
        return _unavailable(f"no stored strategy for {race_day} {area}")
    stored = json.loads(files[-1].read_text(encoding="utf-8"))
    answer = {k: v for k, v in stored["answer"].items() if k not in ("block_readings", "briefing_card_markdown")}
    return {
        "result": answer,
        "provenance": {"tool": "get_stored_strategy", "file": files[-1].name, "model_run": stored["run"],
                       "checks": stored["checks"]["number_trace"]["by_status"]},
    }


def _evaluation_summary(evaluation: dict | None) -> dict | None:
    if not evaluation:
        return None
    if evaluation.get("kind") == "forecast_world":
        return {"kind": "forecast_world: the plan sailed in the day-ahead wind forecast on a placeholder course; NOT a "
                        "comparison with a real race", "assumptions": evaluation["assumptions"],
                "mark_fetchable_without_tacking": evaluation["mark_fetchable_without_tacking"],
                "plan": {"time_to_windward_mark": evaluation["plan"]["time"], "tacks": evaluation["plan"]["tacks"]},
                "pure_side_variants": {s: {"time": r["time"], "tacks": r["tacks"]} for s, r in evaluation["alternatives"].items()}}
    return {"kind": "real_race: the plan sailed in a simplified simulator and compared with the real fleet and winners",
            "races": [{"race": r["race"], "plan_finish_simulated": r["full_race"]["agent"]["finish"],
                       "race_winner_real_finish": (r["full_race"]["race_winner"] or {}).get("finish"),
                       "rank_vs_real_finishers": r["full_race"]["agent"]["indicative_rank_vs_real_finishers"],
                       "plan_side": r["strategy"]["q1_side"], "side_that_paid": r["real_fleet_first_beat"]["side_paid"],
                       "side_called_right": r["match"]["side"]} for r in evaluation["races"]]}


def build_strategy_plan(race_day: str, area: str, use_rag: bool, simulate: bool, runner: Callable[..., Any]) -> dict:
    """Run the plan workflow and return a summary. ``runner`` is ``service.plan`` (injected in tests)."""
    if area not in AREAS:
        return _unavailable(f"unknown area {area!r}", areas=list(AREAS))
    steps, done = [], None
    try:
        for event in runner(race_day, area, use_rag=use_rag, run_evaluation=simulate):
            if hasattr(event, "run_dir"):
                done = event
            else:
                steps.append(f"{event.name}: {event.detail}")
    except Exception as error:  # noqa: BLE001 - e.g. no stored pack, no key: the agent must be able to tell the user why
        return _unavailable(f"the plan could not be built: {type(error).__name__}: {str(error)[:300]}", steps_done=steps)
    a = done.answer
    trace = done.checks["number_trace"]
    return {
        "result": {
            "steps": steps,
            "favoured_side": {"side": a["q1_favoured_side"]["side"], "confidence": a["q1_favoured_side"]["confidence"],
                              "reasons": [r["text"] for r in a["q1_favoured_side"]["reasons"]]},
            "shift_pattern": {"pattern": a["q2_shift_pattern"]["pattern"], "detail": a["q2_shift_pattern"]["cycle_or_rate"]},
            "start": {"favoured_end": a["q3_start"]["favoured_end"], "reasons": [r["text"] for r in a["q3_start"]["reasons"]]},
            "first_beat_plan": a["first_beat_plan"], "action_plan": a.get("action_plan"),
            "contingencies": a["q4_contingencies"], "uncertainty": a["data_gaps_and_uncertainty"],
            "checks": {"schema_errors": done.checks["schema_errors"], "cited_numbers": trace["cited_numbers"],
                       "verified_at_path": trace["by_status"].get("verified_at_path", 0)},
            "simulation": _evaluation_summary(done.evaluation),
            "rag": {"briefing_documents": done.rag_docs, "vector_passages": done.rag_hits, "note": done.rag_note or None},
            "saved_in": done.run_dir,
        },
        "provenance": {"tool": "build_strategy_plan", "model_run": done.meta,
                       "data_scope": f"stored briefing pack {race_day} {area}, backtest: only what was known the morning before"},
    }


def _dump(result: dict) -> str:
    return json.dumps(result, default=str, ensure_ascii=False)


def build_tools(store_factory: Callable[[], Any] | None = None, plan_runner: Callable[..., Any] | None = None) -> list[BaseTool]:
    """The tool list. ``store_factory`` builds the strategy-index store on first use; ``plan_runner`` runs the plan
    workflow (both injected in tests)."""

    @tool("select_strategy_docs")
    def select_strategy_docs_tool(conditions: dict) -> str:
        """Choose which team-strategy documents apply to the given conditions (deterministic thresholds, no
        similarity search). `conditions` keys: wind_mean_kt, gust_kt, wind_rise_kt_2h, precipitation_mm_h,
        cloud_cover_pct, cloud_cover_change_pct_h, squall_line_forecast, current_kt, tide_change_during_race,
        land_sea_temp_diff_c, gradient_wind_kt, wind_from_land, terrain_height_m_upwind, wave_height_m,
        swell_direction_diff_deg. Omit what is unknown; never pass 0 for unknown. Returns document ids in
        priority order with the reason each applies and which inputs were not provided."""
        return _dump(select_strategy_docs(conditions))

    @tool("search_strategy")
    def search_strategy_tool(question: str, doc_ids: list[str] | None = None, k: int = 6) -> str:
        """Search the team-strategy documents for passages that answer a tactics question. Optionally restrict to
        document ids returned by select_strategy_docs. Quote passages with their [DOC-ID section]."""
        make = store_factory or default_store
        try:
            store = make()
        except Exception as error:  # noqa: BLE001 - e.g. no OpenAI key
            return _dump(_unavailable(f"strategy search is not set up: {type(error).__name__}: {str(error)[:200]}"))
        return _dump(search_strategy(question, doc_ids, k, store))

    @tool("get_briefing_pack")
    def get_briefing_pack_tool(race_day: str, area: str) -> str:
        """The stored weather and venue briefing pack for a race day: wind shifts, persistent shift, pressure,
        sea breeze, tide and current, start-line bias, laylines, with the evidence behind each. race_day is
        YYYY-MM-DD; area is port_la_course or belmont_course. Only stored packs exist (today: 2026-07-19)."""
        return _dump(get_briefing_pack(race_day, area))

    @tool("winners_first_beat")
    def winners_first_beat_tool() -> str:
        """How the race winners sailed the first beat compared with the fleet, from real GPS tracks (ILCA 7,
        San Pedro, 19 July 2026): per race, the side each winner took and the sideways offset in metres, plus
        an overall verdict. One day and four winners only: say so when you use it."""
        return _dump(winners_first_beat())

    @tool("get_stored_strategy")
    def get_stored_strategy_tool(race_day: str, area: str) -> str:
        """The strategy the AI strategist already produced for a race day and area: favoured side, shift pattern,
        start, contingencies, first-beat plan and action plan, each with cited evidence. Prefer this over
        re-deriving a plan."""
        return _dump(get_stored_strategy(race_day, area))

    @tool("build_strategy_plan")
    def build_strategy_plan_tool(race_day: str, area: str, use_rag: bool = True, simulate: bool = True) -> str:
        """Build a NEW race-day strategy plan with the full workflow: the general strategy documents (briefing plus vector
        search, if use_rag), the AI strategist on the stored weather briefing pack, schema and number checks, and a
        simulation of the plan. Takes about a minute and costs a model call, so use it only when the user asks for a
        plan; to read an existing plan use get_stored_strategy. race_day is YYYY-MM-DD (only 2026-07-19 has a pack);
        area is port_la_course (simulated against the real race) or belmont_course (simulated in the forecast wind on a
        placeholder course, not compared with a real race). Say which of the two simulations the numbers come from."""
        runner = plan_runner or _default_plan_runner()
        return _dump(build_strategy_plan(race_day, area, use_rag, simulate, runner))

    return [select_strategy_docs_tool, search_strategy_tool, get_briefing_pack_tool, winners_first_beat_tool,
            get_stored_strategy_tool, build_strategy_plan_tool]


def _default_plan_runner() -> Callable[..., Any]:
    from backend.ai import service  # noqa: PLC0415 - service imports this module

    return service.plan


def default_store() -> Any:
    from backend.rag.config import load_settings  # noqa: PLC0415 - chromadb import is slow
    from backend.rag.store import OpenAIEmbedder, Store  # noqa: PLC0415

    settings = load_settings()
    return Store(settings.chroma_dir, settings.embedding_model, OpenAIEmbedder(settings.embedding_model))


__all__ = ["build_tools", "default_store", "get_briefing_pack", "get_stored_strategy", "search_strategy",
           "select_strategy_docs", "winners_first_beat"]
