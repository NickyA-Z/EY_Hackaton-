"""The plan as a LangGraph workflow, with scripted models: no key, no network. Live runs are in docs/ai.md."""

from __future__ import annotations

import json

import numpy as np
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage

from backend import paths
from backend.ai import service
from backend.ai.plan_graph import build_plan_graph, stored_packs
from backend.ai.snapshot import conditions_from_pack
from backend.ai.testing import ScriptedChatModel
from backend.location_agent import providers, simulate as sim
from backend.location_agent.prompt import compact_schema

DAY, AREA = "2026-07-19", "port_la_course"
PACK = json.loads((paths.LOCATION_AGENT_OUTPUT_DIR / f"{DAY}_{AREA}" / "briefing_pack.json").read_text())


def strategist_reply(answer=None, **meta):
    answer = answer if answer is not None else providers._mock({}, PACK)[0]
    return AIMessage(content=json.dumps(answer),
                     response_metadata={"stop_reason": "end_turn", "model_name": "scripted-model", **meta},
                     usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})


def rag_reply():
    return AIMessage(content="Favour the right toward the breakwater [TS-10].")


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOCATION_AGENT_RUNS_DIR", tmp_path)
    monkeypatch.setattr("backend.rag.config.load_dotenv", lambda *a, **k: False)
    return tmp_path


def run(use_rag=True, evaluate=True, area=AREA, strategist=None, rag=None):
    strategist = strategist or ScriptedChatModel(script=[strategist_reply()])
    rag = rag or ScriptedChatModel(script=[rag_reply()])
    events = list(service.plan(DAY, area, use_rag=use_rag, run_evaluation=evaluate, races=[1],
                               strategist_model=strategist, rag_model=rag))
    return events, strategist, rag


def test_the_full_plan_runs_every_node_in_order_and_writes_one_run_folder(runs):
    events, strategist, _ = run()
    assert [e.name for e in events if isinstance(e, service.PlanStep)] == [
        "load_pack", "rag_insights", "strategist", "verify", "evaluate", "save"]
    done = events[-1]
    folder = paths.ROOT / done.run_dir
    assert folder.parent == runs and sorted(p.name for p in folder.iterdir() if p.is_file()) == sorted(done.files) == [
        "briefing.md", "evaluation.json", "evaluation.md", "rag_insights.txt", "strategy.json"]
    assert done.checks["schema_errors"] == [] and done.evaluation["races"][0]["full_race"]["agent"]["finish"]
    assert done.rag_docs and done.briefing.startswith("# Race-day briefing")


@pytest.mark.usefixtures("runs")
def test_the_rag_text_reaches_the_strategist_prompt_and_is_traceable():
    _, strategist, _ = run(evaluate=False)
    sent = strategist.calls[0][1].content
    assert "rag_insights" in sent and "Favour the right toward the breakwater" in sent


@pytest.mark.usefixtures("runs")
def test_without_rag_there_is_no_rag_step_and_no_rag_text_in_the_prompt():
    events, strategist, rag = run(use_rag=False, evaluate=False)
    assert "rag_insights" not in [e.name for e in events if isinstance(e, service.PlanStep)]
    assert rag.calls == [] and "Favour the right toward the breakwater" not in strategist.calls[0][1].content
    assert "rag_insights.txt" not in events[-1].files


@pytest.mark.usefixtures("runs")
def test_the_simulator_is_skipped_only_when_not_wanted():
    names = lambda ev: [e.name for e in ev if isinstance(e, service.PlanStep)]  # noqa: E731
    assert "evaluate" not in names(run(evaluate=False)[0])
    assert "evaluate" in names(run(evaluate=True)[0])


@pytest.mark.usefixtures("runs")
def test_an_answer_that_fails_the_schema_is_saved_but_not_briefed_or_simulated():
    bad = providers._mock({}, PACK)[0]
    del bad["q1_favoured_side"]
    events, *_ = run(strategist=ScriptedChatModel(script=[strategist_reply(bad)]))
    done = events[-1]
    assert done.checks["schema_errors"] and done.briefing == "" and done.evaluation is None
    assert "briefing.md" not in done.files and "strategy.json" in done.files


@pytest.mark.usefixtures("runs")
def test_committed_outputs_are_untouched():
    before = {p: p.stat().st_mtime_ns for p in paths.LOCATION_AGENT_OUTPUT_DIR.rglob("*") if p.is_file()}
    run()
    assert before == {p: p.stat().st_mtime_ns for p in paths.LOCATION_AGENT_OUTPUT_DIR.rglob("*") if p.is_file()}


@pytest.mark.usefixtures("runs")
def test_a_missing_pack_is_an_error_not_a_silent_build():
    with pytest.raises(FileNotFoundError, match="no stored briefing pack"):
        list(service.plan("2026-06-15", AREA, strategist_model=ScriptedChatModel(script=[strategist_reply()])))
    assert (DAY, AREA) in stored_packs() and all(not d.endswith("hindsight") for _, d in stored_packs())


def test_the_graph_is_a_compiled_langgraph_with_the_documented_nodes():
    nodes = set(build_plan_graph(strategist_model=ScriptedChatModel(script=[]), rag_model=ScriptedChatModel(script=[])).get_graph().nodes)
    assert {"load_pack", "rag_insights", "strategist", "verify", "evaluate", "save"} <= nodes


# ---- the strategist call itself (providers._anthropic through LangChain) ----

@pytest.mark.parametrize(("meta", "message"), [({"stop_reason": "max_tokens"}, "cut off"),
                                               ({"stop_reason": "refusal"}, "refused")])
def test_strategist_call_reports_a_cut_off_or_refused_answer(meta, message):
    reply = AIMessage(content="{}", response_metadata=meta)
    cfg = providers.load_config({"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-sonnet-5-5"})
    with pytest.raises(RuntimeError, match=message):
        providers.generate(PACK, cfg, model=ScriptedChatModel(script=[reply]))


def test_strategist_call_never_returns_an_empty_answer():
    reply = AIMessage(content=[{"type": "thinking", "thinking": "..."}], response_metadata={"stop_reason": "end_turn"})
    cfg = providers.load_config({"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-sonnet-5-5"})
    with pytest.raises(RuntimeError, match="Empty answer"):
        providers.generate(PACK, cfg, model=ScriptedChatModel(script=[reply]))


def test_the_strategist_request_has_the_shape_the_raw_sdk_call_had():
    """Strict JSON-schema output, effort, the refusal-fallback beta, and no thinking override."""
    model = ChatAnthropic(model="claude-sonnet-5-5", max_tokens=8000, api_key="x",
                          output_config={"effort": "medium", "format": {"type": "json_schema", "schema": compact_schema()}},
                          betas=["server-side-fallback-2026-07-01"], model_kwargs={"fallbacks": "default"})
    payload = model._get_request_payload([("system", "s"), ("user", "u")])
    assert payload["output_config"]["format"]["type"] == "json_schema" and payload["output_config"]["effort"] == "medium"
    assert payload["betas"] == ["server-side-fallback-2026-07-01"] and payload["fallbacks"] == "default"
    assert "thinking" not in payload


def test_conditions_come_from_the_packs_race_day_forecast():
    c = conditions_from_pack(PACK)
    assert (c.wind_mean_kt, c.gust_kt) == (16.3, 17.4) and c.current_kt is None


# ---- vector passages, Belmont forecast-world, wind-unit regression ----

class FakeHit:
    def __init__(self, n):
        self.id, self.doc_id, self.section, self.body = f"TS-10#{n}", "TS-10", f"Section {n}", f"Passage text number {n}."


class FakeStore:
    def __init__(self):
        self.queries = []

    def search(self, query, k=6, doc_ids=None):
        self.queries.append((query, k, list(doc_ids or [])))
        return [FakeHit(len(self.queries) * 10 + i) for i in range(k)]


class BrokenStore:
    def search(self, *a, **k):
        raise RuntimeError("401 Incorrect API key")


@pytest.mark.usefixtures("runs")
def test_vector_passages_are_searched_per_question_limited_to_the_triggered_documents_and_given_to_the_strategist():
    store = FakeStore()
    events = list(service.plan(DAY, AREA, run_evaluation=False, strategist_model=ScriptedChatModel(script=[strategist_reply()]),
                               rag_model=ScriptedChatModel(script=[rag_reply()]), store_factory=lambda: store))
    done = events[-1]
    assert len(store.queries) == 4 and all(q[1] == 3 and q[2] == done.rag_docs for q in store.queries)
    assert len(done.rag_hits) == 12 and done.rag_note == ""
    assert "Passages found by vector search" in done.rag_text and "Passage text number 11." in done.rag_text


@pytest.mark.usefixtures("runs")
def test_when_the_vector_search_fails_the_plan_still_runs_and_says_so():
    events = list(service.plan(DAY, AREA, run_evaluation=False, strategist_model=ScriptedChatModel(script=[strategist_reply()]),
                               rag_model=ScriptedChatModel(script=[rag_reply()]), store_factory=BrokenStore))
    done = events[-1]
    assert done.rag_hits == [] and "vector search unavailable" in done.rag_note and "401" in done.rag_note
    assert "Passages found" not in done.rag_text
    assert any("NO vector passages" in e.detail for e in events if isinstance(e, service.PlanStep) and e.name == "rag_insights")


@pytest.mark.usefixtures("runs")
def test_belmont_is_simulated_in_a_forecast_world_not_against_a_real_race():
    belmont = json.loads((paths.LOCATION_AGENT_OUTPUT_DIR / f"{DAY}_belmont_course" / "briefing_pack.json").read_text())
    events = list(service.plan(DAY, "belmont_course", use_rag=False, strategist_model=ScriptedChatModel(
        script=[strategist_reply(providers._mock({}, belmont)[0])])))
    done = events[-1]
    assert [e.name for e in events if isinstance(e, service.PlanStep)] == ["load_pack", "strategist", "verify", "evaluate", "save"]
    ev = done.evaluation
    assert ev["kind"] == "forecast_world" and set(ev["alternatives"]) == {"left", "middle", "right"}
    assert ev["plan"]["reached_mark"] and all(r["reached_mark"] for r in ev["alternatives"].values())
    # the pack estimates a 11.8 min beat from the class priors. On 19 July the forecast wind (231 deg) is only 39 deg off the
    # E-W placeholder course, so the mark is fetchable on one tack: faster than a beat, and the run must say so.
    assert ev["mark_fetchable_without_tacking"] and ev["mark_off_wind_deg"] == 39 and ev["plan"]["tacks"] <= 2
    assert 0.5 * 11.8 < ev["plan"]["seconds"] / 60 < 11.8
    assert any(a.startswith("WARNING: the placeholder mark is 39") for a in ev["assumptions"])
    assert "NOT" not in ev["note"] and "not a comparison with a real race" in ev["note"]
    assert any("placeholder" in a for a in ev["assumptions"])


def test_the_real_race_wind_is_the_forecast_table_at_the_right_times_not_one_stuck_value():
    """Regression: the conditions table is in microseconds; dividing by 10**9 made every lookup return the last row (2.3 kn)."""
    probe = json.loads((sim.TRACK_DIR / "probe_report.json").read_text())
    session = next(s["assignment"] for s in probe["events"][0]["matching_sessions"] if s["assignment"]["date"] == DAY)
    wind = sim.truth_wind(sim.load_fleet(session["session_id"]))
    assert len(np.unique(np.round(wind.tws, 2))) > 1
    assert wind.tws.min() > 10 and wind.tws.max() < 25
