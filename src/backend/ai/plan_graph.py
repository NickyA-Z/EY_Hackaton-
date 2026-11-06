"""The strategy plan as one LangGraph workflow: stored features -> RAG text -> strategist -> checks -> simulation.

    load_pack -> [rag_insights] -> strategist -> verify -> [evaluate] -> save

Square brackets are optional steps (``use_rag``, ``evaluate``). Every step is a node, so the dashboard can show
progress, and every run writes one folder under ``data/location_agent/runs/`` (inputs, answer, checks, evaluation):
a run never touches the committed outputs.

The nodes reuse the existing code: ``features`` (stored pack), ``ai.brief`` (RAG text), ``providers`` (the strategist
call, itself LangChain), ``checks`` (schema and number trace), ``evaluate`` (simulator). Nothing is reimplemented here.
The RAG text goes into the pack as ``rag_insights`` exactly as ``strategist.py`` attaches the hand-saved file.

The RAG text has two parts: the briefing built from the documents the conditions trigger, and passages found by vector
search in the strategy index, one search per coach question (side, shifts, start, plan B), limited to those same
documents. If the index or the embedding key is unavailable the plan still runs on the briefing alone and says so
(``rag_note``); it never pretends the vector search happened.

The simulation step depends on the course: Port of LA is compared with the real race (``evaluate``); Belmont has no real
race, so the plan is sailed in a forecast world instead (``forecast_sim``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from backend import paths
from backend.ai.brief import ai_brief
from backend.ai.models import current_override, model_id
from backend.ai.snapshot import conditions_from_pack
from backend.ai.tools import default_store
from backend.location_agent import checks, evaluate, forecast_sim, providers
from backend.location_agent.features import pack_path
from backend.location_agent.prompt import OUTPUT_SCHEMA
from backend.location_agent.strategist import briefing_markdown

REAL_RACE_AREAS = ("port_la_course",)  # courses with real GPS tracks to compare with; others get the forecast-world run
QUESTIONS = (  # the coach's four pre-start questions, as search queries
    "Which side of the course is favoured, and when should we avoid a side?",
    "How should we play the shifts: oscillating or persistent wind, when to tack?",
    "How should we start: line bias, which end, and what to do in the first minutes?",
    "Plan B: what to do if the forecast is wrong or we are losing out?",
)
PASSAGES_PER_QUESTION = 3


class PlanState(TypedDict, total=False):
    race_day: str
    area: str
    use_rag: bool
    run_evaluation: bool
    races: list[int]
    run_dir: str
    pack: dict
    rag_text: str
    rag_docs: list[str]
    answer: dict
    meta: dict
    checks: dict
    evaluation: dict
    rag_hits: list[str]
    rag_note: str
    files: list[str]


def stored_packs() -> list[tuple[str, str]]:
    """(race_day, area) of every stored backtest pack: what a plan can be built for."""
    found = []
    for f in sorted(paths.LOCATION_AGENT_OUTPUT_DIR.glob("*/briefing_pack.json")):
        name = f.parent.name
        if name.endswith("_hindsight"):
            continue
        day, _, area = name.partition("_")
        found.append((day, area))
    return found


def _run_dir(state: PlanState) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return paths.LOCATION_AGENT_RUNS_DIR / f"{stamp}_{state['race_day']}_{state['area']}_{'rag' if state['use_rag'] else 'norag'}"


def vector_passages(doc_ids: list[str], store: Any) -> list:
    """Passages from the strategy index for the four coach questions, limited to ``doc_ids``, best first, no duplicates.

    The query is the bare question. A prefix with venue, class and wind numbers was tried and made the four searches
    return the same passages (4 unique of 12, against 7 unique for the bare question): the conditions are already
    applied by limiting the search to the documents they trigger."""
    seen, hits = set(), []
    for question in QUESTIONS:
        for hit in store.search(question, k=PASSAGES_PER_QUESTION, doc_ids=doc_ids):
            if hit.id not in seen:
                seen.add(hit.id)
                hits.append(hit)
    return hits


def build_rag_text(pack: dict, rag_model: BaseChatModel | None, store_factory: Callable[[], Any] | None) -> dict:
    """The RAG step: the briefing from the triggered documents, plus vector passages when the index can be searched."""
    briefing = ai_brief(conditions_from_pack(pack), model=rag_model)
    docs = list(briefing.selection.doc_ids)
    text, hits, note = briefing.text, [], ""
    try:
        found = vector_passages(docs, (store_factory or default_store)())
        hits = [f"{h.doc_id} {h.section}" for h in found]
        text += ("\n\nPassages found by vector search in the team strategy documents (one search per coach question):\n"
                 + "\n".join(f"- [{h.doc_id} {h.section}] {h.body.strip()}" for h in found))
    except Exception as error:  # noqa: BLE001 - no index or a dead embedding key must be reported, not hidden
        note = f"vector search unavailable ({type(error).__name__}: {str(error)[:120]}); the RAG text is the briefing alone"
    return {"rag_text": text, "rag_docs": docs, "rag_hits": hits, "rag_note": note}


def build_plan_graph(*, strategist_model: BaseChatModel | None = None, rag_model: BaseChatModel | None = None,
                     llm_config: dict | None = None, store_factory: Callable[[], Any] | None = None):
    """Compile the graph. The ``*_model`` arguments replace the real chat models (tests pass scripted ones)."""

    def load_pack(state: PlanState) -> dict:
        f = pack_path(date.fromisoformat(state["race_day"]), state["area"], True)
        if not f.exists():  # the graph only reads stored features; building one is a separate, explicit step
            raise FileNotFoundError(f"no stored briefing pack for {state['race_day']} {state['area']}; have: {stored_packs()}")
        return {"pack": json.loads(f.read_text(encoding="utf-8")), "run_dir": str(_run_dir(state))}

    def rag_insights(state: PlanState) -> dict:
        return build_rag_text(state["pack"], rag_model, store_factory)

    def strategist(state: PlanState) -> dict:
        pack = {**state["pack"], "rag_insights": state["rag_text"]} if state.get("rag_text") else state["pack"]
        # one model setting for the whole AI layer: CLAUDE_MODEL (the strategist's own LLM_MODEL is not used here);
        # LLM_EFFORT and LLM_MAX_TOKENS still come from .env
        cfg = llm_config or providers.load_config({"LLM_PROVIDER": "anthropic", "LLM_MODEL": model_id()})
        answer, meta = providers.generate(pack, cfg, model=strategist_model or current_override())
        return {"answer": answer, "meta": {**meta, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}}

    def verify(state: PlanState) -> dict:
        # the trace runs against the pack the model saw, so numbers cited from the RAG text resolve as "rag_insights"
        seen = {**state["pack"], "rag_insights": state["rag_text"]} if state.get("rag_text") else state["pack"]
        return {"checks": {"schema_errors": checks.validate(state["answer"], OUTPUT_SCHEMA),
                           "number_trace": checks.trace_numbers(state["answer"], seen)}}

    def evaluate_plan(state: PlanState) -> dict:
        strategy = {"run": state["meta"], "answer": state["answer"]}
        out = Path(state["run_dir"])
        if state["area"] in REAL_RACE_AREAS:
            result = evaluate.evaluate_strategy(state["race_day"], state["area"], strategy, "strategy.json",
                                                set(state.get("races") or [1, 2, 3]), out)
        else:
            result = forecast_sim.forecast_world(state["race_day"], state["area"], state["pack"], strategy, out)
        return {"evaluation": result}

    def save(state: PlanState) -> dict:
        out = Path(state["run_dir"])
        out.mkdir(parents=True, exist_ok=True)
        written = []
        result = {"run": state["meta"], "checks": state["checks"], "answer": state["answer"]}
        (out / "strategy.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        written.append("strategy.json")
        if not state["checks"]["schema_errors"]:
            (out / "briefing.md").write_text(briefing_markdown(state["answer"], state["pack"], state["meta"]), encoding="utf-8")
            written.append("briefing.md")
        if state.get("rag_text"):
            (out / "rag_insights.txt").write_text(state["rag_text"] + "\n", encoding="utf-8")
            written.append("rag_insights.txt")
        if state.get("evaluation"):
            written += ["evaluation.json", "evaluation.md"]
        return {"files": written}

    def after_load(state: PlanState) -> str:
        return "rag_insights" if state.get("use_rag") else "strategist"

    def after_verify(state: PlanState) -> str:
        wanted = (state.get("run_evaluation") and not state["checks"]["schema_errors"] and "action_plan" in state["answer"])
        return "evaluate" if wanted else "save"

    graph = StateGraph(PlanState)
    for name, fn in (("load_pack", load_pack), ("rag_insights", rag_insights), ("strategist", strategist),
                     ("verify", verify), ("evaluate", evaluate_plan), ("save", save)):
        graph.add_node(name, fn)
    graph.add_edge(START, "load_pack")
    graph.add_conditional_edges("load_pack", after_load, {"rag_insights": "rag_insights", "strategist": "strategist"})
    graph.add_edge("rag_insights", "strategist")
    graph.add_edge("strategist", "verify")
    graph.add_conditional_edges("verify", after_verify, {"evaluate": "evaluate", "save": "save"})
    graph.add_edge("evaluate", "save")
    graph.add_edge("save", END)
    return graph.compile()


def run_plan(race_day: str, area: str, *, use_rag: bool = True, run_evaluation: bool = True,
             races: list[int] | None = None, **models: Any) -> PlanState:
    """Run the whole graph and return the final state (blocking)."""
    graph = build_plan_graph(**models)
    return graph.invoke({"race_day": race_day, "area": area, "use_rag": use_rag, "run_evaluation": run_evaluation,
                         "races": races or [1, 2, 3]})
