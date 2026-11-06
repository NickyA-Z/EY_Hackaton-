"""The checks that need a working key. Run after fixing ``.env``:

    PYTHONPATH=src uv run python -m backend.ai.live_check

Prints PASS / FAIL / ERROR per check and exits non-zero unless all pass. It never prints a key. Costs a few
cents: three short model calls and one embedding.

1. brief:  two identical briefings; the second must read from the prompt cache (cache_read_tokens > 0), and both
           must return text (thinking must not use the whole token budget).
2. embed:  one live embedding with the configured OpenAI key.
3. chat:   a real tool-calling turn that uses ``winners_first_beat``; the answer must have text.
"""

from __future__ import annotations

import sys

from backend.ai import service
from backend.ai.models import availability
from backend.rag.triggers import Conditions


def check_brief() -> str:
    conditions = Conditions(wind_mean_kt=22.0, gust_kt=27.0, current_kt=1.0)
    first, second = service.brief(conditions), service.brief(conditions)
    ok = bool(first.text and second.text) and second.usage.cache_read_tokens > 0
    return f"{'PASS' if ok else 'FAIL'} brief: cache_read on 2nd call = {second.usage.cache_read_tokens}, " \
           f"text lengths {len(first.text)}/{len(second.text)}"


def check_embed() -> str:
    from backend.rag.config import load_settings  # noqa: PLC0415
    from backend.rag.store import OpenAIEmbedder  # noqa: PLC0415

    vector = OpenAIEmbedder(load_settings().embedding_model)(["favoured side with an offshore breeze"])[0]
    return f"{'PASS' if len(vector) > 100 else 'FAIL'} embed: dimension {len(vector)}"


def check_chat() -> str:
    events = list(service.chat("Which side did the winners take on the first beat? Use the tool."))
    final = events[-1]
    ok = bool(final.text) and final.tool_calls >= 1
    return f"{'PASS' if ok else 'FAIL'} chat: {final.tool_calls} tool call(s), {len(final.text)} chars, " \
           f"untraced numbers {final.untraced}"


def main() -> int:
    ok, reason = availability()
    print(f"config: {'ok' if ok else 'NOT OK'} ({reason})")
    if not ok:
        return 2
    failed = 0
    for check in (check_brief, check_embed, check_chat):
        try:
            line = check()
        except Exception as error:  # noqa: BLE001 - the point is to report every failure
            line = f"ERROR {check.__name__}: {type(error).__name__}: {str(error)[:160]}"
        failed += not line.startswith("PASS")
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
