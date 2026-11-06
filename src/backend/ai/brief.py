"""The AI briefing: select the documents the conditions trigger, send them to the model, return the text.

A fixed pipeline, not an agent, so a given set of conditions always sends the same documents. The prompt is
the one ``backend.rag.generate`` already builds (``build_brief_prompt``, pure and tested); only the model call
differs: it goes through the LangChain chat model from ``models.py``.

``backend.rag.generate.brief`` is left in place and still works. It sends ``thinking={"type": "disabled"}``,
which langchain-anthropic refuses for ``claude-sonnet-5-5`` (the raw API was not tested: no working key).
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend import paths
from backend.ai.models import chat_model, require_text, text_of
from backend.rag.corpus import Document, load_documents
from backend.rag.generate import Briefing, Usage, build_brief_prompt
from backend.rag.triggers import Conditions, select_documents

# Thinking tokens count against max_tokens (rag.generate used 1500 with thinking off).
MAX_TOKENS = 4000


def usage_of(message: AIMessage) -> Usage:
    meta = message.usage_metadata or {}
    details = meta.get("input_token_details") or {}
    return Usage(
        input_tokens=meta.get("input_tokens", 0),
        output_tokens=meta.get("output_tokens", 0),
        cache_write_tokens=details.get("cache_creation", 0) or 0,
        cache_read_tokens=details.get("cache_read", 0) or 0,
    )


def ai_brief(conditions: Conditions, *, model: BaseChatModel | None = None,
             docs: dict[str, Document] | None = None) -> Briefing:
    docs = docs if docs is not None else load_documents(paths.STRATEGY_CORPUS_DIR)
    selection = select_documents(conditions)
    system, user = build_brief_prompt(docs, conditions, selection)
    model = model or chat_model(max_tokens=MAX_TOKENS)
    reply = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = require_text(text_of(reply.content), what="briefing")
    return Briefing(text=text, selection=selection, usage=usage_of(reply))
