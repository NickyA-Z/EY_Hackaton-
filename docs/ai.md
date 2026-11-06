# AI layer (`src/backend/ai`)

A LangChain chat agent and a briefing pipeline over the tools and data the repo already has, shown in the
dashboard as **AI briefing** (Coach brief page) and **Ask the strategist** (Strategy page). Implements the
first slice of PLAN-AI-architecture.md (a colleague's spec; not committed yet, restore this link once it is); the differences are listed below.

## Status

Checked 2026-11-06 with `claude-sonnet-5-5` (via `python -m backend.ai.live_check` and the dashboard driven by
`streamlit.testing.v1.AppTest`):

| Part | State |
| --- | --- |
| Code, 46 tests with scripted models (offline) | Done. |
| Briefing against the real model | **Works.** Second call read 2683 tokens from the prompt cache (`cache_control` survives LangChain). |
| Chat agent against the real model, in the dashboard | **Works.** Called `winners_first_beat`, answered from its data, no number flagged. |
| Strategy plan workflow (LangGraph), terminal, dashboard and chat | **Works live** for Port LA and Belmont (2026-07-19): RAG text with vector passages, strategist on LangChain, checks, simulation, one run folder. The chat agent triggers it with `build_strategy_plan`. See below. |
| Thinking off | Works on Sonnet 5.5 with `{"type": "between_tools"}`. The API answers 400 to `{"type": "disabled"}` on this model (seen via `rag ask`), so R6 is kept, with a different value. |
| Token-by-token streaming in a browser | Not checked (the headless test sees the finished answer). |
| `search_strategy` and the strategy index | **Works.** `.chroma/` built from the Azure embeddings (88 chunks); a strategy question in the dashboard chat searched and cited the documents. |
| Model setting | `CLAUDE_MODEL` is unset in `.env`, so the default `claude-sonnet-5-5` applies. A dotted id such as `claude-haiku-5.5` is refused with the fix named. The separate `LLM_MODEL=claude-haiku-5.5` in `.env` belongs to the Location Agent strategist (`location_agent/providers.py`), not to this layer. |

## How it fits together

```
dashboard (frontend/agent_views.py)
   └─ frontend/ai_views.py        panels; imports backend.ai.service only
        └─ backend/ai/service.py  chat(question) -> events;  brief(conditions)
             ├─ models.py         the one place that builds the model from CLAUDE_MODEL
             ├─ tools.py          6 tools wrapping existing code; only build_strategy_plan reaches an LLM (through the plan workflow)
             ├─ brief.py          documents the conditions trigger -> model -> text (rag.generate's prompt)
             ├─ verify.py         flags numbers in an answer that no tool result contains
             └─ snapshot.py       dashboard state -> rag Conditions / context text
```

The page never imports a LangChain type: `chat` yields `ToolCall`, `ToolResult`, `Token` and `Final`, which the
panel renders (tool calls in a status box, text streamed, warnings under the answer).

### Tools

| Tool | Wraps | Notes |
| --- | --- | --- |
| `select_strategy_docs` | `rag.triggers.select_documents` | A mistyped condition key returns an error, never "no wind". |
| `search_strategy` | `rag.store.Store.search` | Needs the index (`python -m backend.rag index`) and an OpenAI key; otherwise returns `unavailable`. |
| `get_briefing_pack` | stored `briefing_pack.json` | Never builds a pack. Only 2026-07-19 exists. |
| `winners_first_beat` | `race_analysis.summary` | One day, four winners; the tool result carries that scope. |
| `get_stored_strategy` | stored `strategy_*.json` | Ignores mock runs. |
| `build_strategy_plan` | the plan workflow below (`service.plan`) | Builds a NEW plan: about a minute, one strategist call and one briefing call. Returns the plan, checks, the simulation (labelled real-race or forecast-world), and which documents and vector passages were used. |

### Rules the code enforces

- The model id comes from `CLAUDE_MODEL` only, through `rag.config`. No other module names a model.
- An empty answer raises. A failing key or model shows the error text in the panel; nothing renders blank.
- A question gets at most 6 rounds of tool calls (`service.MAX_TOOL_CALLS`); the answer then says it was cut off.
- Numbers in the final answer are looked up in the tool results and the user's text, to the precision the answer
  wrote (153 matches 152.64; signs and dates are ignored). Unmatched ones are shown as a warning. This is a flag,
  not a proof: whole numbers below 10 are ignored, a coincidental match passes, and a wrong claim without a
  number is not seen. The first live chat flagged 6 numbers that were all rounding or a Unicode minus; fixed.
- With no key or a bad model id the panels show "AI unavailable: <what to fix>" and the rest of the page is unchanged.

## The strategy plan workflow (LangGraph)

`backend/ai/plan_graph.py` is a `langgraph` `StateGraph`; `service.plan` streams its steps to the dashboard and
`python -m backend.ai.plan` runs it from the terminal.

```
load_pack -> [rag_insights] -> strategist -> verify -> [evaluate] -> save
```

| Node | Does | Reuses |
| --- | --- | --- |
| `load_pack` | reads the stored briefing pack (never builds one) | `location_agent.features.pack_path` |
| `rag_insights` | RAG text: the briefing from the documents the pack's race-day wind and gust trigger, plus vector-search passages (one search per coach question, 3 each, limited to those documents). If the index or key is unavailable the plan runs on the briefing alone and says so | `ai.brief`, `snapshot.conditions_from_pack`, `rag.store` |
| `strategist` | the Location Agent's model call, with the RAG text attached as `rag_insights` | `location_agent.providers` (now LangChain `ChatAnthropic`) |
| `verify` | schema check and number trace against the pack the model saw | `location_agent.checks` |
| `evaluate` | Port LA: sails the plan over the real races and compares with the fleet and winners. Belmont (no real race): sails it in the forecast wind on the placeholder beat, with pure left/middle/right variants | `location_agent.evaluate.evaluate_strategy`, `location_agent.forecast_sim` |
| `save` | writes `strategy.json`, `briefing.md`, `rag_insights.txt`, `evaluation.*` | |

Brackets are optional (`--no-rag`, `--no-evaluate`). Each run writes
`data/location_agent/runs/<time>_<day>_<area>_<rag|norag>/` (git-ignored) and never touches the committed outputs.
The model comes from `CLAUDE_MODEL`; `LLM_EFFORT` and `LLM_MAX_TOKENS` still come from `.env`; `LLM_MODEL` is not used here.

The strategist request is the one the raw SDK call sent (strict JSON-schema output, effort, server-side refusal
fallback beta, no `thinking` override): same 11,054 input tokens on the same pack before and after the move.
Remaining non-LangChain code: the `openai_compatible` strategist provider (`requests`), the `mock` provider, and
`rag/store.py` (Chroma and the embeddings client, kept by design: it holds the content-hash index sync).

## Differences from the plan

| Plan | Here | Why |
| --- | --- | --- |
| R6: thinking disabled on every call | Thinking off via `rag.generate.thinking_off` (`between_tools` on Sonnet 5.5), `AI_EFFORT=low` also sent | `disabled` is a 400 on Sonnet 5.5, and langchain-anthropic refuses it too. Token limits stay at 4000 as a margin. **Correction:** an earlier version of this file said thinking cannot be disabled on Sonnet 5.5; that came from LangChain's check, and the API says otherwise. |
| Router + three agents (D3, section 6.4) | One agent with all tools; the page decides between the brief and the chat | The UI already knows the intent. Removes the classifier, its eval set and open questions Q2 and Q5. |
| Brief as an LCEL chain (D5) | A plain function calling the LangChain model | A fixed prompt and one call gain nothing from LCEL. |
| `ConditionSnapshot` (6.2) | `rag.triggers.Conditions`, unchanged | It already has "None = not provided" and key checking. |
| `RaceAnswer.numbers` filled in by the model (R3) | `verify.untraced_numbers` against recorded tool output | The model cannot vouch for itself. |
| Replace `location_agent/providers.py` | Anthropic path done, others kept | `ChatAnthropic` carries the same request (JSON schema, effort, fallback beta). The `openai_compatible` and `mock` providers stay. Live-verified. |
| Tools `forecast_speed`, `leg_gain`, `scenario_matrix`, `live_check` | Not yet wrapped | Next slice. `scenario_matrix` and `live_check` need the cached wind history from the dashboard. |
| Model-specific limits | `claude-sonnet-5-5` also rejects non-default `temperature` and forced `tool_choice` | From the same langchain-anthropic check. For structured output use `method="json_schema"`. |

## Configuration

| Variable | Used for | Default |
| --- | --- | --- |
| `CLAUDE_MODEL` | Every chat and briefing call | `claude-sonnet-5-5` |
| `ANTHROPIC_API_KEY` | Same | none |
| `AI_EFFORT` | Reasoning effort (`low`, `medium`, `high`; `none` omits it) | `low` |
| `OPENAI_API_KEY`, `OPENAI_ENDPOINT`, `EMBEDDING_MODEL` | `search_strategy` only | see [rag.md](rag.md); Azure works |

## Tests

`ScriptedChatModel` (`backend/ai/testing.py`) plays back prepared messages. The tests cover: each tool equals the
direct function call, the tool-call cap, an empty answer, a failing tool, the number check, the request that
`ChatAnthropic` would send (no `thinking: disabled`, `cache_control` kept on the system block), and the real
dashboard run headless with `streamlit.testing.v1.AppTest` (chat turn, error path, unconfigured path, briefing button).
