"""After-the-fact check that the numbers in an answer came from somewhere.

The model is told to state only numbers a tool returned (or the user gave). It can still invent one, so
every number in the final answer is looked up in the tool results and in the text the user supplied. What
is not found is returned and shown to the user as a warning.

This is a flag, not a guarantee:
- A number matches a source value if they agree to the precision the answer wrote: "153" matches 152.64,
  "152.6" matches 152.64, "152.7" does not. Signs are ignored (the answer may say "76 m left" for -76.3).
- A coincidental match passes; the check cannot see a wrong claim that contains no number.
- Whole numbers below 10 (list numbering, "2 of 3 races") are not checked.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from backend.location_agent.checks import _numbers_in

_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_NOISE = [
    re.compile(r"\[[^\]]*\]"),  # citations like [TS-03 Plan B]
    re.compile(r"\b[A-Z]{2,}-\d+\b"),  # document ids
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # clock times
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO dates
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}(?:\s+\d{{4}})?\b"),  # 19 July 2026
    re.compile(rf"\b{_MONTHS}\s+\d{{1,2}}(?:,?\s+\d{{4}})?\b"),  # July 19, 2026
]
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers_in_answer(text: str) -> list[tuple[float, int]]:
    """(value, decimals written) for each checkable number. Signs are dropped on purpose."""
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    found = []
    for raw in _NUMBER.findall(text):
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw)
        if decimals == 0 and value < 10:
            continue
        found.append((value, decimals))
    return found


def _matches(value: float, decimals: int, known: float) -> bool:
    return abs(value - abs(known)) <= 0.5 * 10 ** -decimals + 1e-9


def untraced_numbers(answer: str, sources: Iterable[str]) -> list[float]:
    """Numbers in ``answer`` that appear in none of the ``sources`` (tool outputs, user text)."""
    known: list[float] = []
    for source in sources:
        known += _numbers_in(source)
    return sorted({v for v, d in numbers_in_answer(answer) if not any(_matches(v, d, k) for k in known)})
