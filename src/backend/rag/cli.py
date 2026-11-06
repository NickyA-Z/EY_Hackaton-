"""Command line: ``uv run python -m backend.rag <command>``.

Commands: index | select | search | brief | ask
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.rag.config import load_settings
from backend.rag.corpus import indexable_chunks, load_documents
from backend.rag.triggers import Conditions, select_documents

# flag -> (Conditions field, type)
_NUMERIC = {
    "--wind": "wind_mean_kt",
    "--gust": "gust_kt",
    "--wind-rise": "wind_rise_kt_2h",
    "--rain": "precipitation_mm_h",
    "--cloud": "cloud_cover_pct",
    "--cloud-change": "cloud_cover_change_pct_h",
    "--current": "current_kt",
    "--land-sea-diff": "land_sea_temp_diff_c",
    "--gradient": "gradient_wind_kt",
    "--terrain": "terrain_height_m_upwind",
    "--waves": "wave_height_m",
    "--swell-diff": "swell_direction_diff_deg",
}
_BOOLEAN = {
    "--squall": "squall_line_forecast",
    "--tide-change": "tide_change_during_race",
    "--from-land": "wind_from_land",
}


def _add_condition_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("conditions (omit a flag = not provided)")
    g.add_argument("--conditions", type=Path, help="JSON file with condition keys (flags override it)")
    g.add_argument("--venue", help="default: port_of_la")
    for flag, field in _NUMERIC.items():
        g.add_argument(flag, dest=field, type=float, default=None)
    for flag, field in _BOOLEAN.items():
        g.add_argument(flag, dest=field, action="store_true", default=None)


def _conditions_from(args: argparse.Namespace) -> Conditions:
    data: dict = json.loads(args.conditions.read_text(encoding="utf-8")) if args.conditions else {}
    for field in (*_NUMERIC.values(), *_BOOLEAN.values()):
        value = getattr(args, field)
        if value is not None:
            data[field] = value
    if args.venue:
        data["venue"] = args.venue
    return Conditions.from_dict(data)


def _has_conditions(args: argparse.Namespace) -> bool:
    fields = (*_NUMERIC.values(), *_BOOLEAN.values())
    return bool(args.conditions) or any(getattr(args, f) is not None for f in fields)


def _store(settings):
    from backend.rag.store import OpenAIEmbedder, Store  # noqa: PLC0415 - chromadb import is slow; keep `select` instant

    embedder = OpenAIEmbedder(settings.embedding_model)
    return Store(settings.chroma_dir, settings.embedding_model, embedder), embedder


def _anthropic():
    from anthropic import Anthropic  # noqa: PLC0415 - only needed by brief/ask

    return Anthropic(timeout=120.0)  # reads ANTHROPIC_API_KEY from the environment


def _print_selection(sel) -> None:
    print("Selected documents (highest priority first):")
    for doc_id in sel.doc_ids:
        print(f"  {doc_id}  tier {sel.tiers[doc_id]}  {sel.reasons[doc_id]}")
    if sel.missing:
        print("Not provided: " + ", ".join(sel.missing))


def _print_usage(u) -> None:
    print(
        f"\n[tokens: in {u.input_tokens}, out {u.output_tokens}, "
        f"cache write {u.cache_write_tokens}, cache read {u.cache_read_tokens}]"
    )


def _cmd_index(args, settings, docs) -> int:
    store, embedder = _store(settings)
    stats = store.sync(indexable_chunks(docs), force=args.force)
    print(
        f"{stats.total} chunks: embedded {stats.embedded}, unchanged {stats.skipped}, removed {stats.deleted} "
        f"(model {settings.embedding_model}, {embedder.tokens} tokens billed)"
    )
    return 0


def _cmd_select(args, settings, docs) -> int:  # noqa: ARG001
    _print_selection(select_documents(_conditions_from(args)))
    return 0


def _cmd_search(args, settings, docs) -> int:  # noqa: ARG001
    store, _ = _store(settings)
    doc_ids = select_documents(_conditions_from(args)).doc_ids if _has_conditions(args) else None
    for h in store.search(args.query, k=args.k, doc_ids=doc_ids):
        print(f"{h.distance:.3f}  {h.doc_id} / {h.section}")
        if args.show:
            print("      " + h.body.replace("\n", "\n      "))
    return 0


def _cmd_brief(args, settings, docs) -> int:
    from backend.rag.generate import brief  # noqa: PLC0415 - lazy, see _store

    result = brief(_anthropic(), settings.claude_model, docs, _conditions_from(args))
    _print_selection(result.selection)
    print("\n" + result.text)
    _print_usage(result.usage)
    return 0


def _cmd_ask(args, settings, docs) -> int:
    from backend.rag.generate import ask  # noqa: PLC0415 - lazy, see _store

    store, _ = _store(settings)
    conditions = _conditions_from(args) if _has_conditions(args) else None
    result = ask(_anthropic(), settings.claude_model, store, docs, args.question, conditions=conditions, k=args.k)
    print(result.text)
    print("\nSources: " + ", ".join(f"{h.doc_id}/{h.section}" for h in result.hits))
    _print_usage(result.usage)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend.rag", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("index", help="embed new/changed chunks into ChromaDB (no-op if nothing changed)")
    p.add_argument("--force", action="store_true", help="re-embed everything")
    p.set_defaults(func=_cmd_index)

    p = sub.add_parser("select", help="which documents do these conditions trigger? (no network)")
    _add_condition_args(p)
    p.set_defaults(func=_cmd_select)

    p = sub.add_parser("search", help="vector search over sections")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=6)
    p.add_argument("--show", action="store_true", help="print the section text")
    _add_condition_args(p)
    p.set_defaults(func=_cmd_search)

    p = sub.add_parser("brief", help="daily briefing: selected documents -> Claude")
    _add_condition_args(p)
    p.set_defaults(func=_cmd_brief)

    p = sub.add_parser("ask", help="free-form question: vector retrieval -> Claude")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=6)
    _add_condition_args(p)
    p.set_defaults(func=_cmd_ask)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    docs = load_documents(settings.corpus_dir)
    try:
        return args.func(args, settings, docs)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: one readable line
        name = type(exc).__name__
        if getattr(exc, "status_code", None) in (401, 403):
            # Provider messages for 401/403 echo part of the API key; never print them.
            print(
                f"error: {name}: credentials rejected (HTTP {exc.status_code}); provider message hidden",
                file=sys.stderr,
            )
            return 1
        print(f"error: {name}: {exc}", file=sys.stderr)
        if name == "NotFoundError":
            print(
                f"hint: check CLAUDE_MODEL / EMBEDDING_MODEL in .env (CLAUDE_MODEL={settings.claude_model!r})",
                file=sys.stderr,
            )
        return 1
