"""The real dashboard with a scripted model: the AI panels render, stream a chat turn, and fail loudly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from backend import paths
from backend.ai import models
from backend.ai.testing import ScriptedChatModel
from backend.location_agent import providers

DASHBOARD = str(Path(__file__).resolve().parents[3] / "frontend" / "dashboard.py")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr("backend.rag.config.load_dotenv", lambda *a, **k: False)
    yield
    models.set_model_override(None)


def open_view(view):
    at = AppTest.from_file(DASHBOARD, default_timeout=120)
    at.session_state["active_view"] = view
    return at.run()


def test_strategy_page_chat_runs_a_tool_and_shows_the_answer():
    models.set_model_override(ScriptedChatModel(script=[
        AIMessage(content="", tool_calls=[{"name": "winners_first_beat", "args": {}, "id": "t1"}]),
        AIMessage(content="The winners went Right on beat 1."),
    ]))
    at = open_view("overview")
    assert not at.exception, at.exception
    assert any(s.value == "Ask the strategist" for s in at.subheader)
    at.chat_input[0].set_value("What did the winners do?").run()
    assert not at.exception, at.exception
    assert [m.name for m in at.chat_message] == ["user", "assistant"]
    assert "went Right on beat 1" in at.chat_message[1].markdown[-1].value
    assert at.session_state["ai_chat"][-1] == ("assistant", "The winners went Right on beat 1.")


def test_a_failing_model_shows_the_error_and_keeps_the_page():
    class Boom(ScriptedChatModel):
        def _generate(self, *a, **k):
            raise RuntimeError("401 invalid x-api-key")

    models.set_model_override(Boom(script=[AIMessage(content="x")]))
    at = open_view("overview")
    at.chat_input[0].set_value("hello").run()
    assert not at.exception
    assert any("invalid x-api-key" in e.value for e in at.error)
    assert at.session_state["ai_chat"] == []  # a failed turn is not recorded as an answer


def test_without_configuration_the_panels_say_what_to_fix_and_the_page_still_works(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-5.5")
    at = open_view("overview")
    assert not at.exception
    assert any("AI unavailable" in c.value and "claude-haiku-5-5" in c.value for c in at.caption)
    assert not at.chat_input


def test_coach_brief_page_has_the_ai_briefing_button():
    models.set_model_override(ScriptedChatModel(script=[AIMessage(content="Favour the right.")]))
    at = open_view("coach_brief")
    assert not at.exception, at.exception
    assert any(s.value == "AI briefing" for s in at.subheader)
    button = next(b for b in at.button if b.label == "Generate AI briefing")
    button.click().run()
    assert not at.exception, at.exception
    assert any(m.value == "Favour the right." for m in at.markdown)
    assert any("Documents:" in c.value for c in at.caption)


def test_strategy_page_builds_a_plan_through_the_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOCATION_AGENT_RUNS_DIR", tmp_path)
    pack = json.loads((paths.LOCATION_AGENT_OUTPUT_DIR / "2026-07-19_port_la_course" / "briefing_pack.json").read_text())
    answer = providers._mock({}, pack)[0]
    models.set_model_override(ScriptedChatModel(script=[
        AIMessage(content="Favour the right [TS-10]."),  # the RAG step
        AIMessage(content=json.dumps(answer), response_metadata={"stop_reason": "end_turn", "model_name": "scripted"}),
    ]))
    at = open_view("overview")
    assert not at.exception, at.exception
    assert any(s.value == "Strategy plan" for s in at.subheader)
    next(b for b in at.button if b.label == "Build strategy plan").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    result = at.session_state["ai_plan_result"]
    assert result.rag_docs and result.evaluation["races"] and (paths.ROOT / result.run_dir).parent == tmp_path
    assert any("Race-day briefing" in m.value for m in at.markdown)
