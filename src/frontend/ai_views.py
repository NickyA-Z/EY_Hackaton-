"""AI panels for the dashboard: an AI briefing on the Coach brief page and "Ask the strategist" on Strategy.

Talks to ``backend.ai.service`` only (plain events, no LangChain types). If the AI is not configured the
panel says what to fix and the rest of the page, which never depends on it, works as before.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.ai import service  # noqa: E402

HISTORY_TURNS = 10  # previous messages sent back to the model


def _unavailable(reason):
    st.caption(f"AI unavailable: {reason}")


def render_ai_brief(conditions, day_label):
    """Button + result. ``conditions`` is a ``backend.rag.triggers.Conditions`` built from the dashboard."""
    st.subheader("AI briefing")
    ok, reason = service.is_available()
    if not ok:
        return _unavailable(reason)
    st.caption("Written from the strategy documents that the conditions trigger. Only wind and gust are known to "
               "the dashboard; the rest is sent as not provided.")
    key = f"ai_brief_{day_label}_{conditions.wind_mean_kt}_{conditions.gust_kt}"
    if st.button("Generate AI briefing", key=f"{key}_go"):
        try:
            with st.spinner("Writing the briefing…"):
                st.session_state[key] = service.brief(conditions)
        except Exception as error:  # noqa: BLE001 - show every failure; a blank panel would look like success
            st.session_state.pop(key, None)
            st.error(f"The briefing failed: {type(error).__name__}: {error}")
    result = st.session_state.get(key)
    if result:
        st.markdown(result.text)
        u = result.usage
        st.caption(f"Documents: {', '.join(result.selection.doc_ids) or 'none'} · tokens in {u.input_tokens} "
                   f"(cache read {u.cache_read_tokens}) out {u.output_tokens}")


def render_chat(context):
    """Chat with the tool-calling agent. ``context`` is the dashboard selection as text."""
    st.subheader("Ask the strategist")
    ok, reason = service.is_available()
    if not ok:
        return _unavailable(reason)
    history = st.session_state.setdefault("ai_chat", [])
    for role, text in history:
        with st.chat_message(role):
            st.markdown(text)
    if history and st.button("Clear conversation", key="ai_chat_clear"):
        st.session_state["ai_chat"] = []
        st.rerun()
    question = st.chat_input("Ask about the winners, the weather or the strategy documents")
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        status = st.status("Thinking…", expanded=True)
        box = st.empty()
        streamed = ""
        try:
            for event in service.chat(question, history=history[-HISTORY_TURNS:], context=context):
                if isinstance(event, service.ToolCall):
                    status.write(f"Calling `{event.name}` {event.args or ''}")
                elif isinstance(event, service.ToolResult):
                    status.write(f"↳ unavailable: {event.summary}" if event.unavailable else f"↳ got data from `{event.name}`")
                elif isinstance(event, service.Token):
                    streamed += event.text
                    box.markdown(streamed)
                else:
                    final = event
        except Exception as error:  # noqa: BLE001 - show every failure, including a rejected key
            status.update(label="Failed", state="error")
            st.error(f"{type(error).__name__}: {error}")
            return
        status.update(label=f"Done · {final.tool_calls} tool call(s)", state="complete", expanded=False)
        box.markdown(final.text)
        if final.capped:
            st.warning("Stopped at the tool-call limit; this answer is incomplete.")
        if final.untraced:
            st.warning("Numbers in this answer that no tool result or message contains (check before use): "
                       + ", ".join(f"{n:g}" for n in final.untraced))
    history += [("user", question), ("assistant", final.text)]


def render_plan():
    """Build the strategy plan with the LangGraph workflow: RAG text -> strategist -> checks -> simulator."""
    st.subheader("Strategy plan")
    ok, reason = service.is_available()
    if not ok:
        return _unavailable(reason)
    targets = sorted(service.plan_targets(), key=lambda t: (t[1] != "port_la_course", t))  # the simulable course first
    if not targets:
        st.caption("No stored briefing packs to plan from.")
        return
    st.caption("Runs the Location Agent as one LangGraph workflow on a stored briefing pack (features computed from the "
               "weather data available on the race morning). Takes about a minute and one model call per step that needs one.")
    left, right = st.columns([2, 3])
    day, area = left.selectbox("Briefing pack", targets, format_func=lambda t: f"{t[0]} · {t[1].replace('_', ' ')}",
                               key="ai_plan_target")
    use_rag = right.checkbox("Use RAG insights from the strategy documents", value=True, key="ai_plan_rag")
    real_race = area == "port_la_course"
    simulate = right.checkbox("Sail the plan in the simulator" + (" against the real race" if real_race else
                                                                   " (forecast wind, placeholder course; no real race exists here)"),
                              value=True, key="ai_plan_sim")
    if st.button("Build strategy plan", type="primary", key="ai_plan_go"):
        status = st.status("Building the plan…", expanded=True)
        try:
            for event in service.plan(day, area, use_rag=use_rag, run_evaluation=simulate):
                if isinstance(event, service.PlanStep):
                    status.write(f"**{event.name}** — {event.detail}")
                else:
                    st.session_state["ai_plan_result"] = event
            status.update(label="Plan ready", state="complete", expanded=False)
        except Exception as error:  # noqa: BLE001 - show every failure; a blank panel would look like success
            st.session_state.pop("ai_plan_result", None)
            status.update(label="Plan failed", state="error")
            st.error(f"{type(error).__name__}: {error}")
    result = st.session_state.get("ai_plan_result")
    if result:
        _show_plan(result)


def _show_plan(result):
    problems = result.checks["schema_errors"]
    trace = result.checks["number_trace"]
    if problems:
        st.error("The model's answer broke the output schema, so no briefing card was made: " + "; ".join(problems[:3]))
    else:
        st.markdown(result.briefing)
    bad = trace["problems"]
    st.caption(f"Model {result.meta.get('served_by')} · {result.meta.get('seconds')} s · cited numbers {trace['cited_numbers']} "
               f"{trace['by_status']}" + (f" · {len(bad)} not verified at their path" if bad else "")
               + (f" · RAG documents {', '.join(result.rag_docs)}" if result.rag_docs else " · without RAG insights"))
    if result.rag_note:
        st.warning(result.rag_note)
    forecast = bool(result.evaluation) and result.evaluation.get("kind") == "forecast_world"
    if forecast:
        e = result.evaluation
        rows = [{"Option": "The plan (" + e["plan_side"] + ", with its triggers)", "Time to windward mark": e["plan"]["time"] or "not reached",
                 "Tacks": e["plan"]["tacks"]}]
        rows += [{"Option": f"Pure {s}, no switch", "Time to windward mark": r["time"] or "not reached", "Tacks": r["tacks"]}
                 for s, r in e["alternatives"].items()]
        st.markdown("**Simulated in the forecast wind** (not a comparison with a real race: Belmont has none)")
        st.dataframe(rows, hide_index=True, width="stretch")
        if e["mark_fetchable_without_tacking"]:
            st.warning(f"The placeholder mark is {e['mark_off_wind_deg']}° off the forecast wind, so it is a close reach, not a "
                       "beat: the side choice barely matters in this simulation.")
        with st.expander("Assumptions of this simulation"):
            st.markdown("\n".join(f"- {a}" for a in e["assumptions"]))
    elif result.evaluation:
        rows = []
        for race in result.evaluation["races"]:
            full = race["full_race"]
            rows.append({"Race": race["race"], "Plan finish (simulated)": full["agent"]["finish"],
                         "Race winner (real)": (full["race_winner"] or {}).get("finish") or "–",
                         "Rank vs real finishers": full["agent"]["indicative_rank_vs_real_finishers"],
                         "Side called": ("✅" if race["match"]["side"] else "❌") + f" {race['strategy']['q1_side']} vs {race['real_fleet_first_beat']['side_paid']}"})
        st.markdown("**Against the real race** (simplified simulator: uniform wind, constant speeds, no other boats)")
        st.dataframe(rows, hide_index=True, width="stretch")
    if result.rag_text:
        with st.expander("RAG insights given to the strategist" + (f" ({len(result.rag_hits)} vector passages)" if result.rag_hits else "")):
            st.markdown(result.rag_text)
    st.caption(f"Saved in {result.run_dir.split('/data/')[-1] if '/data/' in result.run_dir else result.run_dir}")
