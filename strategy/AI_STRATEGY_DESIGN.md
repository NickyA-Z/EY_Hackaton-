# Location Agent: from data to an AI-written race strategy

This covers what we have so far, a review of the "feed the data to an AI" idea, and the proposed design. Related docs:
- `STRATEGY_BRAINSTORM.md`: the coach's decisions and how each maps to data
- `gps_analysis/FINDINGS.md`: what the 2026 test-event tracks showed

---

## 1. What we have so far

| # | Piece | Folder | Size | What it is | Owner |
|---|---|---|---|---|---|
| 1 | **Bathymetry + terrain** | `geo_data/` | 29 MB, 6 files | NOAA depth grid (~10 m) and Copernicus land heights (~30 m) around the LA28 courses, as GeoTIFF and standardized grid JSON. Pipeline: `python -m geodata.run`. | geo workstream |
| 2 | **June conditions pack** | `src/conditions_June_2026/` | 7.8 MB, 79 files | June 2021–2026 around Belmont: measured pier wind/temperature, tide predictions, Long Beach airport reports (METAR), NDBC buoys (waves, sea temperature; yearly files also include July), coarse Open-Meteo | teammate |
| 3 | **July conditions** | `src/conditions_July/` | 2.6 MB, 43 files | July 2021–2026: HRRR model wind (~3 km, 15-min) at the real Port of LA course, Belmont and inland; measured wind at Angels Gate, Pier 400 and Pier J | geo workstream |
| 4 | **Race GPS tracks** | `sailsync_api_results/winners/` | 428 KB, 4 files | 4 ILCA 7 winners, 19 July 2026, 3 races, one point every ~1.7 s | teammate |
| 5 | **GPS analysis** | `strategy/gps_analysis/` | script + results | Races, course and marks, GPS-derived wind, side of course per beat, boat speeds | geo workstream |
| 6 | **Strategy brainstorm** | `strategy/STRATEGY_BRAINSTORM.md` | doc | Brief → decisions → data mapping; rule-engine and simulator ideas | geo workstream |
| 7 | **Marine dashboard** | `sea_dashboard/` | Streamlit app | Live Open-Meteo currents, waves and sea temperature on a map | teammate |
| 8 | **Brief** | `Boat brief and strategy.docx` | | What the coach needs: the four pre-start questions, an ashore-only tool, a printable 08:00 briefing | input |

**What we've learned:**
- **Course:** outside the San Pedro breakwater. The start line runs N–S on the east side; the windward mark is ~1.25 km west at 33.6898 N, −118.2816 W.
- **Race-day wind (19 July 2026):** a steady westerly, 266–274°, 12–17 kt, with **right shifts of 8–10° within races** and very small oscillations. **Right paid** in race 1.
- **Wind sources:**
  - **HRRR** matches the course wind (direction and strength)
  - the **Angels Gate** station reads 25–40° too far left (a local bend), so use it for timing and trend only
- **ILCA 7 speeds:** 4.9 kn upwind (VMG 3.5), 7.4 kn downwind (VMG 5.9), ~2 tacks per beat.

---

## 2. Review of the idea: "standardise the data, feed it to an AI, get a strategy"

**It's sound, and it's what the brief calls the Location Agent.** One change is essential: **don't feed raw data to the AI. Feed it a small, computed "briefing pack".**

| Concern | Why it matters | Fix |
|---|---|---|
| **Raw data is too big** | The bathymetry JSON alone is 15.5 MB, roughly 5 million tokens. One July of HRRR is ~3,000 rows per point. That's far beyond any model's context window, and slow and costly. | Python computes the facts first. The AI gets **~3–8 KB** (~2–4k tokens). |
| **LLMs are weak at arithmetic over big tables** | They can misread trends or invent numbers | All numbers are computed **deterministically** in code. The AI **reasons and explains**; it doesn't calculate. |
| **Hallucination** | A coach can't act on made-up facts | Instruct "use only the facts in the pack and cite them". The output is **structured JSON**, schema-checked. Use low temperature. |
| **Fair model comparison** | Claude vs an open model must get identical inputs | The same prompt and pack; only the provider config changes |
| **Trust** | "Is the AI's strategy right?" | **Backtest on 19 July 2026** with only pre-race information, and compare with what happened. A simple **rule-based baseline** gives a cross-check. |
| **Olympic rules** | Devices and modelled data are banned on coach boats | The output is an **ashore** 08:00 briefing (printable), which fits the brief exactly |
| **Secrets** | API keys and the ngrok URL must not reach GitHub | A `.env` file that is git-ignored, plus a committed `.env.example` |

**What "standardise" means here** is a common data model, not ML-style scaling:
- **Units:** knots, degrees the wind comes **from**, metres, °C.
- **Time:** UTC, plus local PDT for the coach.
- **Positions:** WGS84 lat/lon.
- **Every value** carries its **source** and a **quality flag** (model / measured / GPS-derived).

This extends the June pack's "any format → one data model" idea to all sources.

---

## 3. Proposed design

```
raw data (geo_data, conditions_June/July, GPS tracks)
   │  1. ingest + standardise        (Python, deterministic)
   ▼
conditions table (one data model: time, place, variable, value, unit, source, quality)
   │  2. feature extraction          (Python, deterministic)
   ▼
briefing pack JSON (~3-8 KB)
   │  3. AI strategist               (LLM via a swappable provider, low temperature)
   ▼
strategy JSON (schema) + printable briefing card
   │  4. checks                      (schema, numbers traceable to the pack, rule baseline, backtest)
   ▼
coach briefing  ──►  later: a simulator agent executes the strategy JSON
```

### 3.1 Ingest + standardise
One loader per source, all writing the same long-format table (CSV or Parquet):

| time_utc | lat | lon | variable | value | unit | source | quality |
|---|---|---|---|---|---|---|---|
| 2026-07-19T21:00Z | 33.6955 | −118.2665 | wind_dir_from | 263 | deg | hrrr | model |
| 2026-07-19T21:00Z | 33.7088 | −118.2558 | wind_speed | 11.5 | kn | coops_9410647 | measured |
| 2026-07-19T21:00Z | 33.69 | −118.27 | wind_dir_from | 266 | deg | gps_tacks | gps_derived |

These parsers can be reused:
- `geo_data/geodata/export_json.py` (grid JSON)
- `strategy/gps_analysis/analyse_tracks.py` (GPS, CO-OPS and HRRR loaders)
- the file formats documented in the June and July READMEs

### 3.2 Briefing pack (what the AI sees)
It's built for one **race day + course area + race window**. Illustrative, using the real 19 July 2026 values:

```json
{
  "venue": "LA28 - Port of LA course (outside San Pedro breakwater)",
  "race_day": "2026-07-19", "race_window_local": "14:00-17:15", "boat_class": "ILCA 7",
  "course": {"start_line": "N-S, ~300 m, 33.688-33.690 N, -118.268 W",
             "windward_mark": [33.6898, -118.2816], "rhumb_bearing_deg": 274, "beat_length_m": 1250},
  "climatology_july": {"sea_breeze_onset_local": "11:00", "speed_kn_by_hour": {"12": 10, "14": 13, "16": 15},
                       "veer_deg_per_h": 5, "oscillation_sd_deg": 3},
  "forecast_day": {"source": "HRRR", "dir_deg_by_hour": {"14": 259, "15": 263, "16": 267, "17": 268},
                   "speed_kn_by_hour": {"14": 14.8, "15": 14.7, "16": 17.6, "17": 15.2}},
  "geography": {"left_side": "towards Palos Verdes (456 m, ~6 km W/NW): shelter, wind bends",
                "right_side": "open water, breakwater ~1 km N", "depth_m": {"left": -15, "right": -20}},
  "tide": {"state_during_racing": "...", "range_m": "..."},
  "lessons_from_2026_test_event": ["steady westerly with +8-10 deg right shifts within races",
                                   "right paid on a square course (race 1)", "~2 tacks per beat"],
  "data_caveats": ["Angels Gate station direction reads 25-40 deg left of course wind"]
}
```

The values marked "..." (and the climatology numbers) are placeholders until the pack is computed from the data.

### 3.3 AI strategist with a swappable provider
`.env` (git-ignored; `.env.example` is committed):
```
LLM_PROVIDER=anthropic             # or: openai_compatible
LLM_MODEL=claude-sonnet-5-5        # or e.g. llama3.1:70b / qwen2.5:72b on the open-model server
LLM_API_KEY=...                    # the key for that provider
LLM_BASE_URL=                      # only for openai_compatible, e.g. https://<id>.ngrok-free.app/v1
LLM_TEMPERATURE=0.2
```

**Two adapters, one interface** (`generate(system, user, schema) -> dict`):
- `anthropic`: the official Anthropic SDK (Claude).
- `openai_compatible`: one HTTP client for any server exposing `/v1/chat/completions`. That covers Ollama, vLLM, LM Studio and TGI behind ngrok.

Switching models means editing `.env` only.

**Prompt =**
- the brief's rules of thumb, the four pre-start questions and the Olympic constraints (system prompt)
- the briefing pack (user message)

**The model must answer in this JSON shape:**
```json
{
  "favoured_side_beat1": {"side": "right", "confidence": "medium", "reasons": ["...", "..."], "facts_used": ["forecast_day.dir_deg_by_hour", "..."]},
  "shift_mode": {"type": "persistent_right", "rate_deg_per_h": 5, "advice": "go toward the shift first"},
  "start": {"favoured_end": "...", "why": "..."},
  "first_beat_plan": "...",
  "contingencies": [{"if": "sea breeze late (<10 kt at 13:00)", "then": "..."}],
  "briefing_card_md": "printable 08:00 card"
}
```

### 3.4 Checks
- **Schema:** the answer must parse and match the shape above, with one retry if not.
- **Traceability:** every number in the answer must appear in the pack. Anything else is flagged.
- **Rule baseline:** a small deterministic scorer (`STRATEGY_BRAINSTORM.md` §3) gives its own side call. If the AI and the rules disagree, the card shows both with reasons.
- **Backtest:** 19 July 2026, using only information available before 14:00. Does the AI say "right" for race 1? This runs the same way for every provider, which gives a fair Claude vs open-model comparison.

### 3.5 Later: simulation
The strategy JSON is executed by a simulator agent: a wind field from the pack, plus an ILCA speed table from the GPS speeds. It races baseline strategies (always-left, always-right, middle) over many simulated days. It can also replay 19 July against the winners' real tracks.

### 3.6 Suggested folder
```
location_agent/
  config.py         reads .env (provider, model, key, URL)
  providers.py      anthropic + openai_compatible adapters
  ingest.py         raw files -> standard conditions table
  features.py       conditions table -> briefing pack JSON
  prompt.py         system prompt + output schema
  checks.py         schema, traceability, rule baseline
  run.py            CLI: --date 2026-07-19 --area port_la_course
  .env.example
  README.md
```

---

## 4. Build order (MVP)
1. **Briefing pack for 19 July 2026, Port of LA course**: ingest + features. This is fully testable without any AI.
2. **Provider adapters + prompt**: first call on Claude, then the same pack on an open model via ngrok.
3. **Checks + backtest**: schema, traceability, rule baseline, "did it say right?".
4. **Printable briefing card** for the coach.
5. Later: the climatology for any July day, plus the simulator agent.
