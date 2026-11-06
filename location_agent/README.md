# Location Agent: data → briefing pack → AI strategy

This produces the coach's 08:00 race-day briefing for LA28 sailing. Python computes the numbers, organised as the brief's **9 strategic building blocks**. An AI model (Claude, or an open model behind ngrok) then reads them and answers the coach's **four pre-start questions**.

```
src/conditions_July (+ June pack, geo_data, GPS analysis)
   │  python -m location_agent.ingest        1. standardise  -> data/conditions_july.parquet
   │  python -m location_agent.features      2. features     -> output/<date>_<area>/briefing_pack.json
   │  python -m location_agent.strategist    3. AI strategy  -> strategy_<provider>_<model>.json + briefing_*.md
   │                                          4. checks (schema + every cited number traced to the pack)
   │  python -m location_agent.evaluate      5. evaluate  -> evaluation.md/json + sim/ tracks + output/iterations.md
   ▼     (simulate.py: action_plan + replayed real boats, sailed in the reconstructed race-day wind)
```

**What the strategist may read vs what only the evaluator reads**

| Strategist (race morning) | Evaluator only (after the race) |
|---|---|
| July history 2021–25; the day-ahead forecast (wind, temperature, cloud); measurements up to 11:00; tides; currents; terrain; depth | The real wind of the day (from all boats' tacking angles + HRRR) |
| `course/<date>.json`: **buoy and line coordinates only** | All 44 SailSync tracks: routes, tacks, rounding times |
| `inputs/<date>_rag_insights.txt`: the RAG's text insights from the user's inputs, used as an input the strategy builds on | |
| Fixed ILCA class rule-of-thumb numbers (`settings.yaml`) | |

| File | Role |
|---|---|
| `ingest.py` | All July sources → one standard table: UTC, knots, degrees-from, °C, m; source and quality per value |
| `features.py` | The 9 building blocks; numbers and venue percentiles only. Backtest vs hindsight mode. |
| `FEATURES.md` | Every feature: data, computation, 19 July values |
| `prompt.py` | System prompt (the brief's definitions, rules of thumb, the four questions) and the answer JSON schema |
| `providers.py` | Swappable models: `anthropic` (Claude SDK), `openai_compatible` (any `/v1/chat/completions` server, e.g. via ngrok), `mock` (offline test) |
| `checks.py` | Schema validation; number tracing (each cited number must exist at its pack path) |
| `strategist.py` | CLI tying it together; writes the strategy JSON and the printable briefing card (with the action plan) |
| `course/<date>.json` | Course per race, **coordinates only**: start-line ends, mark 1, mark 2, leeward gate, finish area. Each has a boat count and spread; `uncertain` = fewer than 5 boats. Today derived from all 44 tracks by `strategy/gps_analysis/derive_course.py` (until official SailSync / race-committee data arrives) |
| `inputs/` | `<date>_rag_insights.txt`: the RAG's text insights (built from the user's inputs). Attached at call time, never stored in the feature pack. See `inputs/README.md`. |
| `simulate.py` | Full-race simulator: sails the `action_plan` over every leg of the course (beats, runs, the reach to the finish) and writes our boat's positions at the race winner's timestamps (SailSync CSV format) |
| `evaluate.py` | Scores a strategy: first-beat decisions against the real fleet; our full race against the 4 winners' real tracks (time at each mark, finish, indicative rank) |
| `.env.example` | Model configuration template |

## Setup
```bash
pip install -r location_agent/requirements.txt
```
```bash
copy location_agent\.env.example location_agent\.env
```
Edit `location_agent/.env`:
- **Claude:** `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5-5` (or `claude-opus-5-5`), `LLM_API_KEY=<your key>`.
- **OpenRouter (free-tier models):** `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free`, `LLM_API_KEY=<sk-or-...>`.
  - Optional `LLM_EXTRA_BODY={"reasoning": {"enabled": true}, "provider": {"only": ["nvidia"], "allow_fallbacks": false}}`.
  - Use `LLM_MAX_TOKENS=16000`, because reasoning tokens count toward the cap.
  - Free models have daily and per-minute rate limits. A limit hit shows as "Endpoint error … rate limit".
- **Open model via ngrok:** `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://<id>.ngrok-free.app/v1`, `LLM_MODEL=<served model name>`, plus `LLM_API_KEY` if the endpoint needs one.
- **For any OpenAI-compatible endpoint:**
  - `LLM_EXTRA_BODY` merges extra JSON fields into the request.
  - `LLM_JSON_MODE=false` stops sending `response_format`. The code also retries once without it automatically if the endpoint rejects it.

`.env` is git-ignored. **Never put a key in `.env.example`**, because that file is committed.

## What is stored vs what changes per run
| Layer | File | Rebuilt |
|---|---|---|
| Raw downloads | `src/conditions_July/data/raw/` | only when you run `fetch_july.py` by hand (the only data-API script) |
| Standard table | `data/conditions_july.parquet` | only when you run `ingest` |
| **Feature pack** (the 9 blocks) | `output/<date>_<area>[_hindsight]/briefing_pack.json` | built once. After that, only with `--rebuild` (or by running `features`), and **only if its inputs changed** |
| **RAG insights** (text) | `inputs/<date>_rag_insights.txt` | read on every run and attached just before the AI call |

- **Fingerprint:** `context.fingerprint` is a short hash of everything the features depend on:
  - the parquet file (size and time)
  - the terrain and depth rasters
  - `settings.yaml`
  - the course file
  - the `features.py` code
  - the run parameters (date, area, window, cutoff, mode)
- **Without a flag**, the stored pack is always used. If its inputs have changed, you get a warning.
- **With `--rebuild`**, the fingerprints are compared and the pack is rebuilt only if they differ.
- The RAG insights file is not part of the fingerprint, so changing it never triggers a rebuild.
- Prepare the demo once with `python -m location_agent.features --date 2026-07-19 --all`. That builds both areas in backtest and hindsight mode, about 40 s. After that, a strategist run takes about 2 s plus the AI call.
- **No data API is called at run time:** the strategist runs with all network sockets blocked when using `--provider mock`. Only `providers.py` makes network calls, to the LLM.

## Run (from the repo root)
```bash
python -m location_agent.strategist --date 2026-07-19 --area port_la_course
```
```bash
python -m location_agent.strategist --date 2026-07-19 --provider mock
```
```bash
python -m location_agent.strategist --date 2026-07-19 --provider openai_compatible --model qwen2.5:72b
```
- The first command is the **backtest**: race-morning information only.
- `--provider mock` runs the whole pipeline offline, with no API call.
- `--provider` and `--model` override `.env` for one run.
- Add `--no-backtest` for a hindsight pack.

### Evaluate and iterate (manual)
```bash
python -m location_agent.evaluate --date 2026-07-19
```
```bash
python -m location_agent.evaluate --date 2026-07-19 --rerun --note "what I changed"
```
- The first command scores the newest strategy file. `--rerun` runs the strategist first; add `--provider mock` to test offline.
- **Race 1 only by default** (`--races 1,2,3` for the others). The course is beat → mark 1, run → gate, beat → mark 2, run → gate, reach → finish, derived from the 44 tracks (`course/2026-07-19.json`).
- **Outputs** in `output/<date>_<area>/sim/`:
  - `race1_agent.csv`: our boat's lat/lon at **exactly the timestamps of the race-1 winner's real track** (Matt Wearn), from the gun to his finish (192 rows), in the SailSync format
  - `race1_agent_full.csv`: our boat's full 2 s track
  - `race1_course.json`: the marks in sailing order
  - `race1_legs.csv`: time at each mark and tacks/gybes per leg, for our boat and the 4 winners
- **Iteration is manual:** read `evaluation.md`, change general things only (prompt rules, features, settings; never race-specific facts), then re-run with `--note`. Each run adds one line to `output/iterations.md`.
- **Simulator limits:**
  - The wind is the same everywhere on the course; the data can't resolve left/right pressure differences.
  - Speeds are the fleet's medians for each leg type; no current, no boat-on-boat interaction, no mark-rounding loss.
  - Tracker gaps hide most roundings of mark 1 and mark 2. Mark 2 is therefore estimated **from timing** (32 boats' real gate-to-gate time with the fleet's measured speeds), and is flagged uncertain.
  - The winners' times are real and ours are simulated, so time gaps include these simplifications.

## Notes on the Claude call
- **Model:** `claude-opus-5-5` by default, with effort `medium` (`LLM_EFFORT`; higher effort = more thinking = more cost). `LLM_MAX_TOKENS=8000` is a ceiling, not a charge.
- **Answer format:** returned as **structured JSON** that matches the schema in `prompt.py`.
- **Refusal fallback:** the server-side option (`fallbacks: "default"`) is switched on. If the model declines a request, the API re-runs it on Anthropic's recommended fallback model within the same call. `served_by` in the output shows which model answered.

## Checks in every output
- `checks.schema_errors`: should be empty.
- `checks.number_trace`: each cited number is labelled
  - `verified_at_path`: correct value at the stated location
  - `in_pack_wrong_path`: the value exists, but the model cited the wrong location
  - `NOT_IN_PACK`: an invented number
