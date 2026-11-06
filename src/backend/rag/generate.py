"""Claude synthesis: the daily briefing (selection-driven) and free-form questions (retrieval-driven).

Token efficiency:
* Briefing: only the documents whose triggers fired are sent, not the whole corpus.
* The stable part (rules + priority order + TS-01/TS-10/TS-11) is a separate system block marked for prompt
  caching, so repeated briefings read it from cache. ``Usage`` reports cache writes/reads so this is verifiable.
* Questions: only the top-k matching sections are sent, not whole documents.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from backend.rag.corpus import Document
from backend.rag.store import Hit, Store
from backend.rag.triggers import Conditions, Selection, select_documents

# Documents that are part of every briefing for this venue: they go in the cacheable prefix.
STABLE_DOC_IDS = ("TS-10", "TS-01", "TS-11")
SAFETY_SECTIONS = ("Coach actions", "Plan B")
BRIEF_MAX_TOKENS = 1500
ASK_MAX_TOKENS = 900

BRIEF_RULES = """You write the daily strategy briefing for an Olympic sailing team's coach.
Use ONLY the strategy documents and the condition values supplied. The documents are synthetic hackathon data.
Documents are listed in priority order. When two documents disagree, follow the higher-priority one and say so.
Cite document ids in brackets, e.g. [TS-03]. If a condition input was not provided, say what is unknown instead
of guessing. Do not invent numbers that are not in the documents or the conditions.
Answer exactly these four pre-start questions, in this order, in plain short sentences a sailor can memorise:
1. Favoured side and why  2. Shift type  3. Start plan  4. Plan B
If any safety-critical document applies, add a final 'Safety' line. Keep the whole briefing under 250 words."""

ASK_RULES = """You answer questions for an Olympic sailing team's coach from the supplied excerpts only.
The excerpts are synthetic hackathon data. Cite sources as [DOC-ID section]. If the excerpts do not contain the
answer, say so plainly instead of answering from general knowledge. Be concise."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int


@dataclass(frozen=True)
class Briefing:
    text: str
    selection: Selection
    usage: Usage


@dataclass(frozen=True)
class Answer:
    text: str
    hits: list[Hit]
    usage: Usage


def _usage(response: Any) -> Usage:
    u = response.usage
    return Usage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )


def thinking_off(model: str) -> dict:
    """The request value that turns thinking off. Newer models reject "disabled" (checked against the API on
    2026-11-06 with claude-sonnet-5-5: 400, "send between_tools instead"); haiku-5.5 still takes it."""
    newer = model.startswith(("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5"))
    return {"type": "between_tools" if newer else "disabled"}


def _complete(client: Any, model: str, system: list[dict], user: str, max_tokens: int) -> tuple[str, Usage]:
    # Thinking is off: this is synthesis over supplied text. With it on, haiku-5.5 spent the whole 1500-token
    # budget on a thinking block and returned no text at all (measured: 1500 out / 0 text vs 490 out / full answer).
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        thinking=thinking_off(model),
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:  # never return a silent blank
        raise RuntimeError(f"model returned no text (stop_reason={response.stop_reason}, max_tokens={max_tokens})")
    return text, _usage(response)


def _conditions_block(conditions: Conditions, selection: Selection) -> str:
    given = {k: v for k, v in asdict(conditions).items() if v is not None}
    lines = ["Conditions provided:", json.dumps(given, indent=1)]
    if selection.missing:
        lines.append("Not provided (unknown, do not assume): " + ", ".join(selection.missing))
    lines.append("Selected documents, highest priority first:")
    lines += [f"- {d} (tier {selection.tiers[d]}): {selection.reasons[d]}" for d in selection.doc_ids]
    return "\n".join(lines)


def build_brief_prompt(
    docs: dict[str, Document], conditions: Conditions, selection: Selection
) -> tuple[list[dict], str]:
    """Return (system blocks, user message). Pure function: no network, easy to test."""
    priority_text = docs["TS-00"].section("Priority order") if "TS-00" in docs else None
    stable_ids = [d for d in STABLE_DOC_IDS if d in selection.doc_ids]
    prefix = [BRIEF_RULES]
    if priority_text:
        prefix.append("Priority order from the corpus index:\n" + priority_text)
    prefix += [docs[d].text() for d in stable_ids]
    system = [{"type": "text", "text": "\n\n".join(prefix), "cache_control": {"type": "ephemeral"}}]

    variable_ids = [d for d in selection.doc_ids if d not in stable_ids]
    user = "\n\n".join(
        [_conditions_block(conditions, selection)]
        + [docs[d].text() for d in variable_ids]
        + ["Write the briefing now."]
    )
    return system, user


def brief(client: Any, model: str, docs: dict[str, Document], conditions: Conditions) -> Briefing:
    selection = select_documents(conditions)
    system, user = build_brief_prompt(docs, conditions, selection)
    text, usage = _complete(client, model, system, user, BRIEF_MAX_TOKENS)
    return Briefing(text=text, selection=selection, usage=usage)


def _format_hits(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{h.doc_id} {h.section}]\n{h.body}" for h in hits)


def ask(
    client: Any,
    model: str,
    store: Store,
    docs: dict[str, Document],
    question: str,
    *,
    conditions: Conditions | None = None,
    k: int = 6,
) -> Answer:
    doc_ids: list[str] | None = None
    forced: list[Hit] = []
    if conditions is not None:
        selection = select_documents(conditions)
        doc_ids = list(selection.doc_ids)
        safety = [d for d in selection.doc_ids if docs[d].safety_critical]
        forced = store.fetch(safety, SAFETY_SECTIONS)  # safety rules are never left to similarity ranking
    hits = store.search(question, k=k, doc_ids=doc_ids)
    seen = {h.id for h in hits}
    all_hits = hits + [h for h in forced if h.id not in seen]
    user = f"Excerpts:\n\n{_format_hits(all_hits)}\n\nQuestion: {question}"
    system = [{"type": "text", "text": ASK_RULES}]  # far below the cache minimum, so no cache marker
    text, usage = _complete(client, model, system, user, ASK_MAX_TOKENS)
    return Answer(text=text, hits=all_hits, usage=usage)
