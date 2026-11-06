# Location Agent: data → briefing pack → AI strategy

This produces the coach's 08:00 race-day briefing for LA28 sailing. Python computes the numbers, organised as the brief's **9 strategic building blocks**. An AI model (Claude, or an open model behind ngrok) then reads them and answers the coach's **four pre-start questions**.

```
data/weather/raw (+ July pack, data/geo, GPS analysis)          (commands: PYTHONPATH=src python -m ...)
   │  backend.location_agent.ingest        1. standardise  -> data/location_agent/conditions_july.parquet
   │  backend.location_agent.features      2. features     -> data/location_agent/output/<date>_<area>/briefing_pack.json
   │  backend.location_agent.strategist    3. AI strategy  -> strategy_<provider>_<model>.json + briefing_*.md
   │                                          4. checks (schema + every cited number traced to the pack)
   │  backend.location_agent.evaluate      5. evaluate  -> evaluation.md/json + sim/ tracks + output/iterations.md
   ▼     (simulate.py: action_plan + replayed real boats, sailed in the reconstructed race-day wind)
```

**What the strategist may read vs what only the evaluator reads**

| Strategist (race morning) | Evaluator only (after the race) |
|---|---|
| July history 2021–25; the day-ahead forecast (wind, temperature, cloud); measurements up to 11:00; tides; currents; terrain; depth | The real wind of the day (from all boats' tacking angles + HRRR) |
| `data/location_agent/course/<date>.json`: **buoy and line coordinates only** | All 44 SailSync tracks: routes, tacks, rounding times |
| `data/location_agent/inputs/<date>_rag_insights.txt`: the RAG's text insights from the user's inputs, used as an input the strategy builds on | |
| Fixed ILCA class rule-of-thumb numbers (`src/backend/location_agent/settings.yaml`) | |

Code is in `src/backend/location_agent/`, data in `data/location_agent/` (locations are in `src/backend/paths.py`).

| File | Role |
|---|---|
| `ingest.py` | All July sources → one standard table: UTC, knots, degrees-from, °C, m; source and quality per value |
| `features.py` | The 9 building blocks; numbers and venue percentiles only. Backtest vs hindsight mode. |
| [location_agent_features.md](location_agent_features.md) | Every feature: data, computation, 19 July values |
| `prompt.py` | System prompt (the brief's definitions, rules of thumb, the four questions) and the answer JSON schema |
| `providers.py` | Swappable models: `anthropic` (Claude SDK), `openai_compatible` (any `/v1/chat/completions` server, e.g. via ngrok), `mock` (offline test) |
| `checks.py` | Schema validation; number tracing (each cited number must exist at its pack path) |
| `strategist.py` | CLI tying it together; writes the strategy JSON and the printable briefing card (with the action plan) |
| `data/location_agent/course/<date>.json` | Course per race, **coordinates only**: start-line ends, mark 1, mark 2, leeward gate, finish area. Each has a boat count and spread; `uncertain` = fewer than 5 boats. Today derived from all 44 tracks by `src/backend/gps_analysis/derive_course.py` (until official SailSync / race-committee data arrives) |
| `data/location_agent/inputs/` | `<date>_rag_insights.txt`: the RAG's text insights (built from the user's inputs). Attached at call time, never stored in the feature pack. |
| `fetch_july.py` | The only data-API script: July wind, tide and current downloads into `data/location_agent/raw/` |
| `../gps_analysis/analyse_tracks.py`, `derive_course.py` | Wind and legs from the winners' GPS (`data/location_agent/gps_results/`); the course file ([gps_analysis.md](gps_analysis.md)) |
| `settings.yaml` | Fixed ILCA rule-of-thumb numbers the features use |
| `simulate.py` | Full-race simulator: sails the `action_plan` over every leg of the course (beats, runs, the reach to the finish) and writes our boat's positions at the race winner's timestamps (SailSync CSV format) |
| `evaluate.py` | Scores a strategy: first-beat decisions against the real fleet; our full race against the 4 winners' real tracks (time at each mark, finish, indicative rank) |
| `.env.example` (repo root) | Model configuration template |

## Setup
```bash
uv sync
```
Copy `.env.example` (repo root) into the repo-root `.env`, the same file as the other keys (`providers.py` reads `paths.ROOT / ".env"`), and edit:
- **Claude:** `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5-5` (or `claude-opus-5-5`), `LLM_API_KEY=<your key>`.
- **OpenRouter (free-tier models):** `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free`, `LLM_API_KEY=<sk-or-...>`.
  - Optional `LLM_EXTRA_BODY={"reasoning": {"enabled": true}, "provider": {"only": ["nvidia"], "allow_fallbacks": false}}`.
  - Use `LLM_MAX_TOKENS=16000`, because reasoning tokens count toward the cap.
  - Free models have daily and per-minute rate limits. A limit hit shows as "Endpoint error … rate limit".
- **Open model via ngrok:** `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://<id>.ngrok-free.app/v1`, `LLM_MODEL=<served model name>`, plus `LLM_API_KEY` if the endpoint needs one.
- **For any OpenAI-compatible endpoint:**
  - `LLM_EXTRA_BODY` merges extra JSON fields into the request.
  - `LLM_JSON_MODE=false` stops sending `response_format`. The code also retries once without it automatically if the endpoint rejects it.

`.env` is git-ignored. **Never put a key in a file that is committed.**

## What is stored vs what changes per run
| Layer | File | Rebuilt |
|---|---|---|
| Raw downloads | `data/location_agent/raw/` (HRRR, CO-OPS, marine currents; see [location_agent_july_data.md](location_agent_july_data.md)) | only when you run `fetch_july.py` by hand (the only data-API script) |
| Standard table | `data/location_agent/conditions_july.parquet` | only when you run `ingest` |
| **Feature pack** (the 9 blocks) | `data/location_agent/output/<date>_<area>[_hindsight]/briefing_pack.json` | built once. After that, only with `--rebuild` (or by running `features`), and **only if its inputs changed** |
| **RAG insights** (text) | `data/location_agent/inputs/<date>_rag_insights.txt` | read on every run and attached just before the AI call |

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
- Prepare the demo once with `PYTHONPATH=src python -m backend.location_agent.features --date 2026-07-19 --all`. That builds both areas in backtest and hindsight mode, about 40 s. After that, a strategist run takes about 2 s plus the AI call.
- **No data API is called at run time:** the strategist runs with all network sockets blocked when using `--provider mock`. Only `providers.py` makes network calls, to the LLM.

## Run (from the repo root, with `export PYTHONPATH=src`)
```bash
python -m backend.location_agent.strategist --date 2026-07-19 --area port_la_course
```
```bash
python -m backend.location_agent.strategist --date 2026-07-19 --provider mock
```
```bash
python -m backend.location_agent.strategist --date 2026-07-19 --provider openai_compatible --model qwen2.5:72b
```
- The first command is the **backtest**: race-morning information only.
- `--provider mock` runs the whole pipeline offline, with no API call.
- `--provider` and `--model` override `.env` for one run.
- Add `--no-backtest` for a hindsight pack.

### Evaluate and iterate (manual)
```bash
python -m backend.location_agent.evaluate --date 2026-07-19
```
```bash
python -m backend.location_agent.evaluate --date 2026-07-19 --rerun --note "what I changed"
```
- The first command scores the newest strategy file. `--rerun` runs the strategist first; add `--provider mock` to test offline.
- **Race 1 only by default** (`--races 1,2,3` for the others). The course is beat → mark 1, run → gate, beat → mark 2, run → gate, reach → finish, derived from the 44 tracks (`data/location_agent/course/2026-07-19.json`).
- **Outputs** in `data/location_agent/output/<date>_<area>/sim/`:
  - `race1_agent.csv`: our boat's lat/lon at **exactly the timestamps of the race-1 winner's real track** (Matt Wearn), from the gun to his finish (192 rows), in the SailSync format
  - `race1_agent_full.csv`: our boat's full 2 s track
  - `race1_course.json`: the marks in sailing order
  - `race1_legs.csv`: time at each mark and tacks/gybes per leg, for our boat and the 4 winners
- **Iteration is manual:** read `evaluation.md`, change general things only (prompt rules, features, settings; never race-specific facts), then re-run with `--note`. Each run adds one line to `data/location_agent/output/iterations.md`.
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

## Testing the RAG + strategist chain

**One command (LangGraph):** `PYTHONPATH=src uv run python -m backend.ai.plan --date 2026-07-19 --area port_la_course` runs RAG text,
strategist, checks and simulator as one workflow (add `--no-rag` for the A side, `--repeat 3` for several samples); the dashboard's
Strategy page has the same thing as **Strategy plan**. See [ai.md](ai.md). The manual steps below do the same by hand.

The RAG and the strategist meet in one plain-text file, `data/location_agent/inputs/<date>_rag_insights.txt`. Nothing
writes it for you: you save the RAG's text there, and the strategist attaches it to its request (it cites it as
`rag_insights`). Checked live on 2026-11-06 with `claude-sonnet-5-5`.

```bash
# 1. RAG text for the race-morning conditions (wind and gust from the pack's forecast; needs the index, see rag.md)
PYTHONPATH=src uv run python -m backend.rag brief --wind 16.3 --gust 17.4
#    save the "Daily Strategy Briefing" part (not the document list or the token line) to
#    data/location_agent/inputs/2026-07-19_rag_insights.txt

# 2. strategy from the stored features + that text. LLM_MODEL must use hyphens (claude-sonnet-5-5).
#    Use a copy of the pack so the committed strategy_*.json is not overwritten (same file name per model):
mkdir /tmp/run && cp data/location_agent/output/2026-07-19_port_la_course/briefing_pack.json /tmp/run/
LLM_MODEL=claude-sonnet-5-5 PYTHONPATH=src uv run python -m backend.location_agent.strategist --pack /tmp/run/briefing_pack.json

# 3. sail the plan in the simulator against the real fleet (writes evaluation.md next to the strategy folder in data/;
#    it overwrites the committed evaluation, so run `git checkout data/location_agent/output` afterwards if unwanted)
PYTHONPATH=src uv run python -m backend.location_agent.evaluate --date 2026-07-19 --races 1,2,3 --strategy /tmp/run/strategy_anthropic_claude-sonnet-5-5.json
```

For an A/B test, run step 2 once without the insights file and once with it, and compare the `action_plan` and the
evaluation tables. One model run is one sample: the same input can give a different plan next time.

First A/B on 19 July (one run each; re-evaluated after the wind fix below): without insights the plan chose the middle, with
the RAG briefing it chose the right and cited the text four times. Simulated finishes (races 1 / 2 / 3): middle plan
39:16 / 31:30 / 33:36, right plan 39:30 / 31:20 / 33:46: gaps of 10 to 15 s in both directions, i.e. this single sample
cannot tell the plans apart. **An earlier version of this paragraph drew conclusions from numbers that were wrong, see
the next section.**

## Simulator wind bug (fixed 2026-11-06)

`simulate.truth_wind` converted the conditions table's timestamps with `astype("int64") // 10**9`, which assumes
nanoseconds; the table is microseconds. Every lookup then returned the last row, so the **wind speed in the real-race
simulation was a constant 2.3 kn instead of 14.7 to 18.6 kn**. Any `wind_speed_below_kn` trigger fired at the gun: the
committed plan ("below 8 kn: go left") was sailed on the left, not the middle, and the two plans of the first A/B were
both sailed on the right. `simulate.epoch_s` now handles any unit; `test_the_real_race_wind_is_the_forecast_table...` pins it.
The committed `evaluation.json/md` and `sim/` for 2026-07-19 were regenerated (race 1 finish 39:34 to 39:32); the lines in
`output/iterations.md` from before the fix were computed with the wrong wind and were left as history.

## Simulation for Belmont

Belmont has no real race (no tracks, results or surveyed marks; its pack uses a placeholder E-W beat), so there is nothing to
compare with. `location_agent/forecast_sim.py` instead sails the plan on that placeholder beat in the day-ahead wind forecast
with the pack's class priors, and also sails pure left / middle / right variants. It is a plausibility and sensitivity
check. On 19 July the forecast wind (231 deg) is only 39 deg off the placeholder course, so the mark is a close reach and
the result says so; the real course will be laid to the wind.
