"""The AI layer with a scripted model: no key, no network. Live behaviour is NOT covered here (see docs/ai.md)."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from backend import paths, race_analysis
from backend.ai import models, service, tools, verify
from backend.ai.brief import ai_brief
from backend.ai.snapshot import conditions_from_insight, context_text
from backend.ai.testing import ScriptedChatModel
from backend.rag.corpus import load_documents
from backend.rag.triggers import Conditions, select_documents


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    # load_settings() would otherwise copy the real .env (keys, CLAUDE_MODEL) into the test's environment
    monkeypatch.setattr("backend.rag.config.load_dotenv", lambda *a, **k: False)
    yield
    models.set_model_override(None)


def call(name, args, id_="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_}])


# ---- tools equal the direct calls (plan gate P0) ----

def test_select_strategy_docs_equals_the_direct_call():
    data = {"wind_mean_kt": 22.0, "gust_kt": 27.0}
    direct = select_documents(Conditions.from_dict(data))
    out = tools.select_strategy_docs(data)["result"]
    assert out["doc_ids"] == list(direct.doc_ids)
    assert out["reasons"] == direct.reasons
    assert out["not_provided"] == list(direct.missing)


def test_select_strategy_docs_rejects_a_mistyped_key_instead_of_treating_it_as_no_wind():
    out = tools.select_strategy_docs({"wind_kt": 22})
    assert "unknown condition keys" in out["unavailable"]


def test_winners_first_beat_equals_race_analysis_summary():
    assert tools.winners_first_beat()["result"] == race_analysis.summary()


def test_briefing_pack_tool_returns_the_stored_pack_and_never_builds_one():
    out = tools.get_briefing_pack("2026-07-19", "port_la_course")
    stored = json.loads((paths.LOCATION_AGENT_OUTPUT_DIR / "2026-07-19_port_la_course" / "briefing_pack.json").read_text())
    assert out["result"] == stored
    missing = tools.get_briefing_pack("2026-06-15", "port_la_course")
    assert "no stored briefing pack" in missing["unavailable"]
    assert "2026-07-19_port_la_course" in missing["available"]
    assert not (paths.LOCATION_AGENT_OUTPUT_DIR / "2026-06-15_port_la_course").exists()


def test_briefing_pack_tool_rejects_bad_input():
    assert "unknown area" in tools.get_briefing_pack("2026-07-19", "nowhere")["unavailable"]
    assert "YYYY-MM-DD" in tools.get_briefing_pack("19 July", "port_la_course")["unavailable"]


def test_stored_strategy_is_the_real_model_answer_not_the_mock():
    out = tools.get_stored_strategy("2026-07-19", "port_la_course")
    assert out["provenance"]["model_run"]["provider"] != "mock"
    assert "q1_favoured_side" in out["result"] and "block_readings" not in out["result"]
    assert "unavailable" in tools.get_stored_strategy("2026-07-19", "belmont_course")


def test_search_reports_unavailable_when_the_index_or_key_is_missing():
    class Empty:
        def count(self):
            return 0

    class Broken:
        def count(self):
            return 1

        def search(self, *a, **k):
            raise RuntimeError("401 Incorrect API key")

    assert "index is empty" in tools.search_strategy("q", None, 6, Empty())["unavailable"]
    assert "401" in tools.search_strategy("q", None, 6, Broken())["unavailable"]


# ---- numbers check ----

def test_untraced_numbers_flags_only_what_no_source_contains():
    sources = [json.dumps({"offset_m": 142.3, "wind": 11.2})]
    assert verify.untraced_numbers("Winners went 142.3 m right in 11.2 kt. [TS-03 Plan B] at 13:00, 2 of 3.", sources) == []
    assert verify.untraced_numbers("They gained 250 m.", sources) == [250.0]


def test_untraced_numbers_accepts_rounding_signs_and_dates_but_not_a_wrong_value():
    """Found in the first live chat: 152.64 written as 153, -76.3 written with a Unicode minus, '19 July'."""
    sources = [json.dumps({"offsets": {"Wearn": 152.64, "Hanson": -76.3, "Bos": -219.4}})]
    ok = "On 19 July Wearn was +153 m, Hanson −76 m, Bos −219 m, and 152.6 to one decimal."
    assert verify.untraced_numbers(ok, sources) == []
    assert verify.untraced_numbers("Wearn was 152.7 m.", sources) == [152.7]  # more precise than the source allows
    assert verify.untraced_numbers("Wearn was 158 m.", sources) == [158.0]


# ---- models ----

def test_availability_names_the_fix(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-5.5")
    ok, reason = models.availability()
    assert not ok and "claude-haiku-5-5" in reason
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ok, reason = models.availability()
    assert not ok and "ANTHROPIC_API_KEY" in reason
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert models.availability() == (True, "claude-sonnet-5-5")


def test_sonnet_model_is_built_with_thinking_off_the_way_the_api_wants_it(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    model = models.chat_model(max_tokens=100)
    payload = model._get_request_payload([("user", "hi")])  # langchain raises here if the config is invalid
    assert payload["thinking"] == {"type": "between_tools"}  # "disabled" is a 400 from the API on this model
    assert payload["output_config"] == {"effort": "low"}
    assert "temperature" not in payload


def test_text_of_drops_thinking_blocks_and_empty_answers_raise():
    blocks = [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Go "}, {"type": "text", "text": "right."}]
    assert models.text_of(blocks) == "Go right."
    with pytest.raises(RuntimeError, match="no text"):
        models.require_text(models.text_of([{"type": "thinking", "thinking": "x"}]), what="chat")


# ---- brief ----

def test_ai_brief_sends_the_selected_documents_with_a_cache_marker():
    docs = load_documents(paths.STRATEGY_CORPUS_DIR)
    model = ScriptedChatModel(script=[AIMessage(content=[{"type": "thinking", "thinking": "."},
                                                          {"type": "text", "text": "Favour the right [TS-04]."}],
                                                usage_metadata={"input_tokens": 900, "output_tokens": 40, "total_tokens": 940,
                                                                "input_token_details": {"cache_read": 800, "cache_creation": 0}})])
    out = ai_brief(Conditions(wind_mean_kt=22.0, gust_kt=27.0), model=model, docs=docs)
    assert out.text == "Favour the right [TS-04]."
    assert out.usage.cache_read_tokens == 800
    system, user = model.calls[0]
    assert system.content[0]["cache_control"] == {"type": "ephemeral"}
    assert "22" in user.content and "TS-03" in user.content  # strong wind selects the safety document


# ---- chat agent ----

def run(model, question="What did the winners do?", **kw):
    return list(service.chat(question, model=model, **kw))


def test_chat_calls_the_tool_streams_events_and_flags_an_invented_number():
    model = ScriptedChatModel(script=[
        call("winners_first_beat", {}),
        AIMessage(content="Winners took the right side; the verdict is Right. They gained 987 m."),
    ])
    events = run(model)
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "ToolCall" and "ToolResult" in kinds and kinds[-1] == "Final"
    final = events[-1]
    assert final.tool_calls == 1 and not final.capped
    assert final.untraced == [987.0]  # not in any tool output
    result = next(e for e in events if isinstance(e, service.ToolResult))
    assert result.name == "winners_first_beat" and not result.unavailable


def test_chat_passes_the_dashboard_context_and_history_to_the_model():
    model = ScriptedChatModel(script=[AIMessage(content="Noted.")])
    run(model, "And the start?", history=[("user", "Hello"), ("assistant", "Hi")], context=context_text(
        {"venue": "Port of LA", "boat_class": "ILCA 7", "race_day": "2026-07-19", "wind_sector": "SSW", "map_hour": 13}))
    sent = model.calls[0]
    assert "boat class: ILCA 7" in sent[0].content
    assert [m.type for m in sent[1:]] == ["human", "ai", "human"]


def test_chat_stops_after_the_tool_call_cap_and_says_so():
    model = ScriptedChatModel(script=[call("winners_first_beat", {})], loop=True)
    final = run(model)[-1]
    assert final.capped and "stopped" in final.text
    assert final.tool_calls <= service.MAX_TOOL_CALLS + 1


def test_chat_with_an_empty_answer_raises_instead_of_showing_a_blank():
    model = ScriptedChatModel(script=[AIMessage(content="")])
    with pytest.raises(RuntimeError, match="no text"):
        run(model)


def test_chat_reports_a_failing_tool_as_text_to_the_model_not_as_a_crash():
    model = ScriptedChatModel(script=[call("get_briefing_pack", {"race_day": "2026-06-15", "area": "port_la_course"}),
                                      AIMessage(content="There is no stored pack for that day.")])
    events = run(model)
    assert next(e for e in events if isinstance(e, service.ToolResult)).unavailable
    assert events[-1].text.startswith("There is no stored pack")


# ---- snapshot ----

def test_conditions_from_insight_leaves_unknowns_unset():
    c = conditions_from_insight({"n_days": 12, "speed": 11.24, "gust": 15.06})
    assert (c.wind_mean_kt, c.gust_kt) == (11.2, 15.1)
    assert c.current_kt is None and "current_kt" in c.missing()
    assert conditions_from_insight({"n_days": 0}) == Conditions()


# ---- the chat agent triggering a plan ----

def fake_plan_runner(calls):
    """Stands in for service.plan: records its arguments and yields what the real one yields."""
    def runner(race_day, area, *, use_rag, run_evaluation):
        calls.append((race_day, area, use_rag, run_evaluation))
        yield service.PlanStep("load_pack", "pack")
        yield service.PlanStep("strategist", "side right")
        answer = {
            "q1_favoured_side": {"side": "right", "confidence": "low", "reasons": [{"text": "Wind veers 4 deg."}]},
            "q2_shift_pattern": {"pattern": "oscillating", "cycle_or_rate": "mock"},
            "q3_start": {"favoured_end": "south_left_end", "reasons": [{"text": "Line bias 188 m."}]},
            "first_beat_plan": "Go right.", "q4_contingencies": [], "data_gaps_and_uncertainty": ["one day"],
            "action_plan": {"start": {"line_position": 0.2}},
        }
        evaluation = {"kind": "forecast_world", "assumptions": ["a"], "mark_fetchable_without_tacking": True,
                      "plan": {"time": "9:26", "tacks": 1}, "alternatives": {"left": {"time": "9:30", "tacks": 1}}}
        yield service.PlanDone("data/location_agent/runs/x", ["strategy.json"], answer, {"served_by": "m"},
                               {"schema_errors": [], "number_trace": {"cited_numbers": 5, "by_status": {"verified_at_path": 5}, "problems": []}},
                               evaluation, "rag", ["TS-10"], ["TS-10 Upwind"], "", "card")
    return runner


def test_the_chat_agent_can_trigger_a_plan_and_gets_a_compact_summary_with_the_simulation_kind():
    calls = []
    model = ScriptedChatModel(script=[
        call("build_strategy_plan", {"race_day": "2026-07-19", "area": "belmont_course", "use_rag": True, "simulate": True}),
        AIMessage(content="Plan: right side. In the forecast-world simulation the plan takes 9:26 to the windward mark."),
    ])
    events = list(service.chat("Build me a plan for Belmont", model=model, plan_runner=fake_plan_runner(calls)))
    assert calls == [("2026-07-19", "belmont_course", True, True)]
    result = next(e for e in events if isinstance(e, service.ToolResult))
    assert result.name == "build_strategy_plan" and not result.unavailable
    sent_back = json.loads(next(m.content for m in model.calls[1] if m.type == "tool"))
    assert sent_back["result"]["simulation"]["kind"].startswith("forecast_world") and sent_back["result"]["rag"]["vector_passages"] == ["TS-10 Upwind"]
    assert events[-1].untraced == []  # 9:26 is a clock-style time and the plan numbers came from the tool


def test_a_plan_that_cannot_be_built_comes_back_as_unavailable_text_for_the_agent():
    def failing(race_day, area, *, use_rag, run_evaluation):  # noqa: ARG001
        raise FileNotFoundError("no stored briefing pack for 2026-06-15 port_la_course")
        yield

    out = tools.build_strategy_plan("2026-06-15", "port_la_course", True, True, failing)
    assert "the plan could not be built" in out["unavailable"] and "no stored briefing pack" in out["unavailable"]
    assert "unknown area" in tools.build_strategy_plan("2026-07-19", "nowhere", True, True, failing)["unavailable"]
