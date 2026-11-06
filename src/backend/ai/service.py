"""What the dashboard calls. The UI imports this module and nothing else from ``backend.ai``.

``chat`` runs one tool-calling agent and yields plain events, so the page can show tool calls as they happen
and stream the text, without ever seeing a LangChain type. ``brief`` is the fixed briefing pipeline.

Failure is loud and bounded: no key or a bad model id raises ``AIUnavailableError`` with the fix; an empty answer
raises; a run that keeps calling tools is stopped after ``MAX_TOOL_CALLS`` rounds and says so.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from backend.ai import tools as ai_tools
from backend.ai.brief import ai_brief, usage_of
from backend.ai.models import AIUnavailableError, availability, chat_model, require_text, text_of
from backend.ai.verify import untraced_numbers
from backend.rag.generate import Briefing, Usage

MAX_TOOL_CALLS = 6  # rounds of tool use per question (plan R8, proposed value)
MAX_TOKENS = 4000

SYSTEM_PROMPT = """You are the strategy assistant of an Olympic sailing team's coach (LA28, Los Angeles).
Answer from the tools, not from memory. Rules:
- Every number you state must come from a tool result or from the user's message. Never calculate or estimate one.
- When the user asks for a new plan, call build_strategy_plan once and report what it returns, including which
  simulation (real race or forecast world) the times come from.
- If a tool says unavailable, tell the user what is missing; do not fill the gap with general sailing knowledge.
- Say how much data a result rests on (for example one day, four winners) when you use it.
- Cite strategy documents as [DOC-ID section]. The strategy documents are synthetic hackathon data.
- Be short and concrete: a coach reads this on the water."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class ToolResult:
    name: str
    summary: str  # first characters of the tool output, for display
    unavailable: bool


@dataclass(frozen=True)
class Token:
    text: str


@dataclass(frozen=True)
class Final:
    text: str
    usage: Usage
    tool_calls: int
    untraced: list[float] = field(default_factory=list)  # numbers in the answer that no tool or user text contains
    capped: bool = False  # stopped at MAX_TOOL_CALLS


Event = ToolCall | ToolResult | Token | Final


@dataclass(frozen=True)
class PlanStep:
    name: str  # a node of the plan graph
    detail: str


@dataclass(frozen=True)
class PlanDone:
    run_dir: str
    files: list[str]
    answer: dict
    meta: dict
    checks: dict
    evaluation: dict | None
    rag_text: str
    rag_docs: list[str]
    rag_hits: list[str]
    rag_note: str
    briefing: str  # the printable coach card (markdown); empty when the answer failed the schema check


def is_available() -> tuple[bool, str]:
    return availability()


def plan_targets() -> list[tuple[str, str]]:
    """(race_day, area) pairs a plan can be built for: the stored briefing packs."""
    from backend.ai.plan_graph import stored_packs  # noqa: PLC0415 - imports the simulator stack

    return stored_packs()


def brief(conditions, *, model: BaseChatModel | None = None) -> Briefing:
    return ai_brief(conditions, model=model)


def _step_detail(name: str, update: dict) -> str:  # noqa: PLR0911 - one line per graph node
    if name == "load_pack":
        c = update["pack"]["context"]
        return f"{c['race_day']} {c['venue']} (features fingerprint {c.get('fingerprint')})"
    if name == "rag_insights":
        found = f"{len(update['rag_hits'])} vector passages" if update["rag_hits"] else "NO vector passages"
        return (f"{len(update['rag_text'])} characters: briefing from documents {', '.join(update['rag_docs'])} + {found}"
                + (f" - {update['rag_note']}" if update["rag_note"] else ""))
    if name == "strategist":
        a, m = update["answer"], update["meta"]
        q1 = a.get("q1_favoured_side") or {}  # an answer that breaks the schema must still be reported, not crash here
        return (f"side {q1.get('side', '?')} ({q1.get('confidence', '?')}), "
                f"{m.get('served_by')}, {m.get('seconds')} s, {m.get('input_tokens')} in / {m.get('output_tokens')} out")
    if name == "verify":
        t = update["checks"]["number_trace"]
        return f"schema errors {len(update['checks']['schema_errors'])}; cited numbers {t['cited_numbers']} {t['by_status']}"
    if name == "evaluate" and update["evaluation"].get("kind") == "forecast_world":
        e = update["evaluation"]
        return (f"forecast world: plan {e['plan']['time']} to the windward mark, "
                + ", ".join(f"{s} {r['time']}" for s, r in e["alternatives"].items())
                + (" - WARNING: the placeholder mark is a close reach in this wind, not a beat" if e["mark_fetchable_without_tacking"] else ""))
    if name == "evaluate":
        return "finish " + ", ".join(f"race {r['race']}: {r['full_race']['agent']['finish']}" for r in update["evaluation"]["races"])
    return ", ".join(update.get("files", []))


def plan(race_day: str, area: str, *, use_rag: bool = True, run_evaluation: bool = True, races: list[int] | None = None,
         strategist_model: BaseChatModel | None = None, rag_model: BaseChatModel | None = None,
         store_factory: Callable[[], Any] | None = None) -> Iterator[PlanStep | PlanDone]:
    """Build the strategy plan with the LangGraph workflow, yielding one ``PlanStep`` per finished node, then ``PlanDone``."""
    from backend.ai.plan_graph import build_plan_graph  # noqa: PLC0415 - imports the simulator stack
    from backend.location_agent.strategist import briefing_markdown  # noqa: PLC0415

    ok, reason = availability()
    if not ok and strategist_model is None:
        raise AIUnavailableError(reason)
    graph = build_plan_graph(strategist_model=strategist_model, rag_model=rag_model, store_factory=store_factory)
    state: dict = {"race_day": race_day, "area": area, "use_rag": use_rag, "run_evaluation": run_evaluation,
                   "races": races or [1, 2, 3]}
    for chunk in graph.stream(state, stream_mode="updates"):
        for name, update in chunk.items():
            state.update(update)
            yield PlanStep(name, _step_detail(name, update))
    card = "" if state["checks"]["schema_errors"] else briefing_markdown(state["answer"], state["pack"], state["meta"])
    yield PlanDone(state["run_dir"], state["files"], state["answer"], state["meta"], state["checks"],
                   state.get("evaluation"), state.get("rag_text", ""), state.get("rag_docs", []),
                   state.get("rag_hits", []), state.get("rag_note", ""), card)


def _messages(history: Sequence[tuple[str, str]], question: str) -> list[AnyMessage]:
    out: list[AnyMessage] = [(HumanMessage if role == "user" else AIMessage)(content=text) for role, text in history]
    out.append(HumanMessage(content=question))
    return out


def _sum_usage(messages: Sequence[AIMessage]) -> Usage:
    parts = [usage_of(m) for m in messages]
    return Usage(sum(p.input_tokens for p in parts), sum(p.output_tokens for p in parts),
                 sum(p.cache_write_tokens for p in parts), sum(p.cache_read_tokens for p in parts))


def chat(question: str, *, history: Sequence[tuple[str, str]] = (), context: str = "",
         model: BaseChatModel | None = None, tools: list | None = None,
         store_factory: Callable[[], Any] | None = None, plan_runner: Callable[..., Any] | None = None) -> Iterator[Event]:
    """Answer ``question`` with the tool-calling agent. ``history`` is [(role, text)] with role user|assistant."""
    from langchain.agents import create_agent  # noqa: PLC0415 - heavy; only when a question is asked
    from langgraph.errors import GraphRecursionError  # noqa: PLC0415

    model = model or chat_model(max_tokens=MAX_TOKENS)
    tool_list = tools if tools is not None else ai_tools.build_tools(store_factory, plan_runner)
    system = SYSTEM_PROMPT + (f"\n\n{context}" if context else "")
    agent = create_agent(model, tools=tool_list, system_prompt=system)

    outputs: list[str] = []  # every tool result, for the number check
    ai_messages: list[AIMessage] = []
    tool_calls = 0
    last_text = ""
    capped = False
    # one round = model node + tools node; the last model call needs one more step
    config = {"recursion_limit": 2 * MAX_TOOL_CALLS + 2}
    try:
        for mode, chunk in agent.stream({"messages": _messages(history, question)}, config=config,
                                         stream_mode=["messages", "updates"]):
            if mode == "messages":
                piece, meta = chunk
                if piece.type == "AIMessageChunk" and meta.get("langgraph_node") == "model":
                    text = text_of(piece.content)
                    if text:
                        yield Token(text)
                continue
            for node, update in chunk.items():
                for message in (update or {}).get("messages", []):
                    if node == "model" and isinstance(message, AIMessage):
                        ai_messages.append(message)
                        for call in message.tool_calls:
                            tool_calls += 1
                            yield ToolCall(call["name"], call["args"])
                        if not message.tool_calls:
                            last_text = text_of(message.content)
                    elif node == "tools" and isinstance(message, ToolMessage):
                        body = text_of(message.content)
                        outputs.append(body)
                        yield ToolResult(message.name or "tool", body[:300], '"unavailable"' in body[:200])
    except GraphRecursionError:
        capped = True
        last_text = last_text or (f"I stopped after {MAX_TOOL_CALLS} rounds of tool calls without a final answer. "
                                  "Ask a narrower question.")
    text = require_text(last_text, what="chat")
    flagged = untraced_numbers(text, [*outputs, context, question, *(t for _, t in history)])
    yield Final(text, _sum_usage(ai_messages), tool_calls, flagged, capped)


__all__ = ["AIUnavailableError", "Final", "PlanDone", "PlanStep", "Token", "ToolCall", "ToolResult", "brief", "chat",
           "is_available", "plan", "plan_targets"]
