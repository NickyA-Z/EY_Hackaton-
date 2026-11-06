"""Chat-model construction: the one place that knows the model id and what that model refuses.

The id comes from ``CLAUDE_MODEL`` (read through ``backend.rag.config``), so the RAG and the AI layer can
never use two different models. Nothing else in ``backend.ai`` names a model.

What ``claude-sonnet-5-5`` does not allow: ``thinking={"type": "disabled"}`` (the API answers 400 and says to send
``between_tools``; langchain-anthropic 1.7.10 refuses it before sending), a ``temperature`` other than the default,
``top_k`` and a forced ``tool_choice``. So thinking is switched off with ``rag.generate.thinking_off`` and
``AI_EFFORT`` (default ``low``) is sent as well. Thinking tokens would count against ``max_tokens``; the limits in
``brief.py`` and ``service.py`` stay generous and an empty answer raises (``text_of`` + ``require_text``)
instead of being shown as a blank.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from backend.rag.config import load_settings
from backend.rag.generate import thinking_off

# claude-sonnet-5-5, claude-haiku-5-5, claude-opus-4-1-20250805 ... Dots ("5.5") are rejected by the API.
_MODEL_ID = re.compile(r"^claude-[a-z]+-\d+(-\d+)*(-\d{8})?$")

_state: dict[str, BaseChatModel | None] = {"override": None}  # a dict, not a global rebind


class AIUnavailableError(RuntimeError):
    """The AI layer cannot be used (bad config, no key). The message says what to fix."""


def set_model_override(model: BaseChatModel | None) -> None:
    """Tests (and the UI tests) put a scripted model here; ``None`` restores the real one."""
    _state["override"] = model


def current_override() -> BaseChatModel | None:
    return _state["override"]


def model_id() -> str:
    return load_settings().claude_model


def availability() -> tuple[bool, str]:
    """(usable, reason). Checks configuration only; it makes no network call, so it cannot see a rejected key."""
    if _state["override"] is not None:
        return True, "test model"
    mid = model_id()
    if not _MODEL_ID.match(mid):
        hint = f" (did you mean {mid.replace('.', '-')!r}?)" if "." in mid else ""
        return False, f"CLAUDE_MODEL={mid!r} is not a valid model id; ids use hyphens{hint}"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set (repo-root .env)"
    return True, mid


def chat_model(*, max_tokens: int) -> BaseChatModel:
    if _state["override"] is not None:
        return _state["override"]
    ok, reason = availability()
    if not ok:
        raise AIUnavailableError(reason)
    from langchain_anthropic import ChatAnthropic  # noqa: PLC0415 - late: the dashboard starts without a key

    kwargs: dict[str, Any] = {"model": reason, "max_tokens": max_tokens, "thinking": thinking_off(reason)}
    effort = os.environ.get("AI_EFFORT", "low").strip().lower()
    if effort and effort != "none":
        kwargs["reasoning_effort"] = effort
    return ChatAnthropic(**kwargs)


def text_of(content: Any) -> str:
    """Only the answer text of a message: thinking blocks and tool-call blocks are not part of it."""
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def require_text(text: str, *, what: str) -> str:
    text = text.strip()
    if not text:  # never return a silent blank
        raise RuntimeError(f"{what}: the model returned no text (thinking may have used the whole max_tokens)")
    return text
