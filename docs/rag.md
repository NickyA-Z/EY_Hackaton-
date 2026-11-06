# Sailing team-strategy RAG

Gives the coach a daily strategy briefing and answers free-form questions, grounded in the markdown corpus in
[`data/rag/`](../data/rag/). The corpus is **synthetic hackathon data**, so the output demonstrates the
mechanism and is not real sailing advice.

## How it works

```
conditions (wind, gusts, current, waves, ...)
        |
        v
 triggers.py  --- threshold rules, priority order --->  which TS-xx documents apply
        |                                                        |
        |                                                        v
        |                                            generate.brief()  -> Claude -> 4-question briefing
        |
 free-form question
        |
        v
 store.py: OpenAI embedding -> ChromaDB (cosine) -> top-k sections -> generate.ask() -> Claude -> cited answer
```

**Why document choice is code, not vector search.** The corpus triggers are numeric thresholds
(`wind_mean_kt >= 18`, `current_kt >= 0.5`). Embeddings cannot evaluate a threshold, so `triggers.py` does it
deterministically and orders the result by the priority list in `data/rag/00_README_corpus_index.md`
(safety > venue > current > wind-type > defaults). Vectors are used only for free-form questions.

## Setup

Python 3.12 and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync
```

Create a `.env` in the repository root (it is gitignored; never commit it):

| Variable | Needed for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `brief`, `ask` | |
| `OPENAI_API_KEY` | `index`, `search`, `ask` | Standard OpenAI keys start with `sk-`; an Azure key does not (see `OPENAI_ENDPOINT`). |
| `CLAUDE_MODEL` | `brief`, `ask` | Use hyphens, e.g. `claude-haiku-5-5` (a dotted `5.5` is rejected by the API). |
| `EMBEDDING_MODEL` | `index`, `search`, `ask` | Default `text-embedding-3-small`. |
| `OPENAI_ENDPOINT` | optional | Where embeddings go. Empty = api.openai.com. For Azure give the resource URL (`https://<name>.services.ai.azure.com`); `/openai/v1/` is added, and `EMBEDDING_MODEL` is then the Azure *deployment* name. Verified 2026-11-06 with `text-embedding-3-large`. The old name `ENDPOINT` is still read. |

## Usage

```bash
uv run python -m backend.rag index                     # embed new/changed sections into .chroma/
uv run python -m backend.rag select --wind 22 --gust 27 --current 1.0   # which documents apply (no network)
uv run python -m backend.rag search "wind shadow from the hills" --show
uv run python -m backend.rag brief  --wind 22 --gust 27 --current 1.0 --waves 1.3
uv run python -m backend.rag ask    "when do we avoid the left side?" --wind 14
```

Condition flags: `--wind --gust --wind-rise --rain --cloud --cloud-change --current --land-sea-diff --gradient
--terrain --waves --swell-diff` (numbers) and `--squall --tide-change --from-land` (switches). `--venue` defaults to
`port_of_la`. `--conditions file.json` loads the same keys from a file; flags override it. **A flag you omit means
"not provided"**: it is reported to the model as unknown and never treated as 0. Unknown JSON keys are rejected.

## Efficiency

- `index` only embeds sections whose text or embedding model changed (content hash). A second run makes zero API calls.
- Embeddings are sent in batches of 256, and computed before anything is written, so a failed call leaves the index intact.
- One ChromaDB collection per embedding model, so changing `EMBEDDING_MODEL` cannot cause a dimension mismatch.
  Vectors are supplied explicitly, so Chroma's bundled default embedder is never loaded.
- `brief` sends only the triggered documents. The stable part (rules, priority order, TS-01/TS-10/TS-11) is a
  separate prompt-cached block; the CLI prints `cache write` / `cache read` token counts so you can see it work.
- `ask` sends only the top-k sections. Claude thinking is switched off (`generate.thinking_off`): with it on, the model used its
  whole token budget on a thinking block and returned no text. The request value depends on the model: `disabled` for
  haiku-5.5, `between_tools` for sonnet-5-5 / opus-5-5 / fable-5 (the API answers 400 to `disabled` there).

## Files

| File | Role |
|---|---|
| `corpus.py` | Parse markdown + front-matter, split into `##` section chunks |
| `triggers.py` | `Conditions`, per-document trigger rules, priority order |
| `store.py` | ChromaDB store, OpenAI embedder, incremental sync, search |
| `generate.py` | Prompt building and Claude calls (`brief`, `ask`) |
| `cli.py`, `__main__.py` | Command line |
| `config.py` | Paths and model names from `.env` |

Tests are in `src/backend/tests/rag/` (`uv run pytest`) and need no API keys: embeddings are faked.

## Known limitations

- **Verified end to end on 2026-11-06** (Azure `text-embedding-3-large`, `claude-sonnet-5-5`): `index` embedded 88 chunks
  (5823 tokens) and a second run embedded none; `search` and `ask` returned cited answers. Retrieval *quality* was only
  eyeballed on a few questions, not measured.
- Weather inputs are entered by hand. Only waves and current exist in `src/backend/retrieval/marine_api.py`; wind, gusts,
  rain and cloud would need a forecast source.
- Judgement calls where the corpus is silent: TS-02 is applied for 8 up to (not including) 18 kt, because the corpus
  leaves 17-18 kt uncovered; TS-09 sits with the wind-type documents and TS-11 last in the priority order.
- Time of day is not modelled, although the venue playbook (TS-10) describes a morning/afternoon pattern.
- Single venue: `TS-10` applies only when `--venue port_of_la`.
