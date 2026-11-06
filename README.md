# Location Agent: venue intelligence for Olympic sailing

**Team Sailor** · EY hackathon · November 2026

Location Agent helps a sailing coach prepare for a race venue the team does not know well. It brings the coach's own files together with years of wind and tide data for the venue, and turns them into briefs the coach and sailors can use before, during and after a race. The first venue is the **LA 2028 Olympic sailing venue** (Long Beach and the Port of Los Angeles).

This repository is the record of what we built in the hackathon. The pitch is over; the code is kept as a working prototype.

## Background

The case came from an Olympic sailing team. Their problem:

- **Venue knowledge is scattered.** Every venue has its own wind, current, wave and terrain behaviour. Today that knowledge sits in notebooks, spreadsheets, GPS tracks and weather files, in a dozen formats with no common model.
- **It is rebuilt for every event.** The team races and trains at 12+ venues a year, and coaches spend days rebuilding venue knowledge before each one instead of coaching.
- **It leaves with the people.** When a coach leaves, so does what they knew about a venue.

The goal set for the hackathon was an MVP in four steps:

1. **Ingest** a few real coach file formats into one data model.
2. **Load** historical wind data for one or two venues.
3. **Visualise** wind patterns, plus one terrain effect, on an interactive map.
4. **Brief**: generate a one-page venue briefing.

The test of success: a coach uploads their files, picks a venue and a wind direction, and within **minutes, not days** sees where the pressure and the shifts usually are, and why.

## What we built

The dashboard follows a coach's race day.

**Before the race**
- **Coach file:** upload notes, PDFs, transcripts, photos of whiteboards and voice memos. Each file is read and tagged by topic (see [backend/README.md](backend/README.md)).
  - Photos are read with Claude vision (Tesseract as fallback).
  - Voice memos are transcribed on the laptop with Whisper (mlx-whisper on Apple Silicon, faster-whisper elsewhere).
- **Venue map and rules:** a regional marine map (wind, waves, currents), the candidate race areas with water depth and terrain, and the sailing instructions.
- **Coach and sailor brief:** answers to the four pre-start questions (favoured side, expected shifts, when the breeze arrives, risks), worked out from similar days in five summers of history.
  - A **Challenger** lists why the brief could be wrong.
- **Strategy:** what-if toggles (wind, strength, sea breeze, risk appetite) and a scenario × appetite table.

**During the race**
- **Live check:** the wind each hour is compared with the morning brief. The app warns when conditions leave the plan, and when they are about to in the next two hours.
- **Camera check:** a snapshot from a live harbour camera (or an uploaded photo or video) is read by Claude vision and OpenCV and checked against the reported wind and waves.
  - This check is **display-only**: by team decision it does not feed the brief.

**After the race**
- **Debriefs** are transcribed and added to the coach file.
- **What the winners did:** the winners' GPS tracks on the first beat are compared with the side the brief chose.

### How a brief is made

```
Coach files ──► readers (text, Claude vision, Whisper) ──► tagged coach file ─┐
History 2021–2025 ─► similar days (same wind sector, same hour) ─► strategy engine ─┼─► coach brief / sailor brief
Live wind & waves ──► live check against the brief ──► alerts ─────────────────┘
```

A RAG step was designed on top of this: the team's strategy playbook (11 pages, e.g. strong wind, light wind, tide, sea breeze) is picked by rules from the conditions or found by meaning for free questions, and Claude writes the brief citing the page it used. It lives on the `pelle-laptop-clean` branch and is **not merged into `main`**.

## Brief vs. what we delivered

| Hackathon goal | Status | Where |
|---|---|---|
| Ingest coach files into one model | Done for text, PDF, DOCX, transcripts, photos, voice memos. GPX/CSV wind logs and results are mapped but not parsed | `backend/analysis/` |
| Historical wind for a venue | Done for LA28: 2021–2026, June–July | `src/conditions_June_2026/` |
| Wind patterns on an interactive map | Done | `frontend/frontend/current_map.py` |
| One terrain effect on the map | Terrain and depth are extracted and shown; their effect on the wind is not modelled | `geo_data/` |
| One-page venue briefing | Done (coach brief and sailor brief) | `backend/strategy.py` |
| Compare with a known venue | Not started | |
| Team playbook (RAG) in the brief | Built separately, not merged | branch `pelle-laptop-clean` |

## Benchmark

The brief was built only on 2021–2025 and scored on every day of June–July 2026 at 11:00, 13:00 and 15:00 (183 cases), each time against a simple baseline.

| Measure | Location Agent | Baseline |
|---|---|---|
| Favoured side called correctly | 73% | 74% ("always Right") |
| Average wind-speed error | 2.1 kt | 2.2 kt (median for the hour) |
| Races where the winners took the briefed side | 2 of 3 | ILCA 7, 19 July 2026 (one day only) |

What this shows:
- The brief finds the venue's main pattern from data alone: the sea breeze veers right about three days in four.
- It does not yet tell the unusual days apart.
- 2026 ran about 2 kt lighter than history (median 6.6 vs 9.1 kt), which is why the live check matters.

Scores are against model wind, not on-water measurements. The live-check replay is not a forecast score: in the replay the next two hours are the real data.

## Limits

- **No measurements on the race area itself.** Its wind is estimated from harbour stations, the airport, an offshore buoy and a weather model. The model puts the three race-area points on the same grid cell, so differences across the course are not visible.
- **No current data**, only tide times.
- **Hourly data**, so shifts within a race cannot be analysed.
- **Race tracks from one day only.**
- **One venue only.**

## Next steps

- Model one terrain effect (e.g. wind shadow or funnelling from the Palos Verdes hills).
- Extend history to 2016–2026 and add August, which covers the Olympic dates.
- Add current data (port sensors, HF radar).
- Parse GPX and CSV wind logs from the coach.
- Merge the playbook (RAG) into the brief.
- Add a second venue and the venue-comparison view.
- Calibrate the camera check on a camera that looks at the race area.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12. From the repository root:

```bash
./frontend/run_local.sh            # http://127.0.0.1:8503
PORT=8504 ./frontend/run_local.sh  # another port
```

Claude vision features need an API key. Put it in a `.env` file in the repository root (gitignored, never commit it):

```
ANTHROPIC_API_KEY=...
```

Without a key the app still runs: photos fall back to Tesseract, and the camera check shows the OpenCV estimate only.

Tests:

```bash
uv run --python 3.12 --with pandas python -m backend.tests.test_backend
```

## Repository layout

| Folder | What it holds |
|---|---|
| `frontend/` | Streamlit dashboard (the app) |
| `backend/` | Strategy engine, race analysis, coach-file readers, live camera, data retrieval ([README](backend/README.md)) |
| `src/conditions_June_2026/` | Wind and tide history: download, parsers and the common data model ([DATA_MODEL.md](src/conditions_June_2026/DATA_MODEL.md)) |
| `geo_data/` | Water depth and terrain for the LA28 race areas ([README](geo_data/README.md)) |
| `sailsync_api_results/` | GPS tracks of the ILCA 7 races on 19 July 2026 |
| `sea_dashboard/` | Earlier version of the dashboard |

## Data sources

- **Wind and weather:** Open-Meteo, NOAA NDBC (buoy 46025), METAR (Long Beach airport).
- **Tides and harbour wind:** NOAA CO-OPS (Pier J, Pier F, Pier S).
- **Water depth:** NOAA NCEI coastal DEM.
- **Terrain:** Copernicus GLO-30 DEM.
- **Race tracks:** SailSync.

## Team

Team Sailor. See the [contributors](https://github.com/NickyA-Z/EY_Hackaton-/graphs/contributors) page.
