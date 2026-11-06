# backend

Logic behind the Location Agent views in `src/frontend/` (no Streamlit code here). Everything is under `src/backend/`.

| Module | Job | Data |
| --- | --- | --- |
| `paths.py` | **The one place that knows where data lives.** Every module below imports its data folder from here; `tests/test_paths.py` guards it | all of the folders below |
| `previous_strategy.py` | Data for the 3D Previous strategy tab (tracks, weather, depth, triggered strategy documents) | `data/trajectories/sailsync/`, `data/geo/la28/json/`, `data/weather/raw/`, `data/rag/` |
| `strategy.py` | Venue statistics, coach/sailor brief, Challenger findings, live check | `data/weather/raw/` (Open-Meteo wind, NOAA tides) |
| `race_analysis.py` | Which side the winners took on beat 1 | `data/trajectories/sailsync/` (ILCA 7, 19 Jul 2026) |
| `analysis/` | Read and tag coach uploads (see below) | uploads + `data/demo_uploads/` samples |
| `boat_speed.py` | Short-horizon ILCA 7 speed forecast from SailSync tracks | `data/trajectories/sailsync/` |
| `venue_time.py` | Turns source timestamps into Los Angeles wall-clock time | none |
| `race_model/` | Which leg choices gained time (see [race_model.md](race_model.md)) | `data/race_model/` |
| `ai/` | LangChain chat agent and AI briefing used by the dashboard (see [ai.md](ai.md)) | tools read `data/rag/`, `data/location_agent/`, `data/trajectories/` |
| `rag/` | Strategy RAG: trigger rules, retrieval, briefs (see [rag.md](rag.md)) | `data/rag/`, index in `.chroma/` |
| `ingest/` | Any native weather / tide / track file into one data model (see [data_model.md](data_model.md)) | `data/weather/`, `data/trajectories/sailsync/` |
| `geodata/` | Bathymetry and terrain pipeline (see [geodata.md](geodata.md)) | `data/geo/` |
| `retrieval/` | Open-Meteo marine API calls and the local geodata JSON loader | `data/geo/la28/json/` |
| `compute/` | Grid and layer maths for the regional marine map | none |
| `scripts/` | One-off downloads: `python -m backend.scripts.fetch_long_beach_data`, `python -m backend.scripts.get_marine_data` | writes `data/weather/` |
| `tests/` | All tests: `tests/` (backend), `tests/ingest/`, `tests/rag/` | fixtures in `tests/ingest/fixtures/` |

## analysis/ — coach-file capabilities

| Capability | Module | Reads | Needs |
| --- | --- | --- | --- |
| 1. Text reading | `text_reader.py` | TXT, MD, CSV, JSON, DOCX, PDF | Nothing for TXT/MD/DOCX. PDF: `pip install pypdf` |
| 2. Picture of text | `image_text.py` | JPG, PNG, WEBP, GIF (whiteboards, handwriting, scanned pages, course sketches) | Claude vision: `pip install anthropic` + `ANTHROPIC_API_KEY` (or `ant auth login`). Fallback: `brew install tesseract` |
| 3. Transcripts | `transcripts.py` | VTT, SRT, pasted text with `Speaker:` / `[hh:mm]` lines | Nothing. Audio must be transcribed first (e.g. Whisper) |
| Tagging | `tagging.py` | Output of 1–3 | Nothing (keyword rules; swap for an LLM later) |

`analysis/__init__.py` routes each file: name + extension → common-model entity → capability.

## What the coach can upload

| Upload | Formats | Used in | Required |
| --- | --- | --- | --- |
| Notice of Race / Sailing Instructions | PDF, DOCX, TXT or photo | Venue rules | Yes |
| Wind logs (coach boat / own station) | CSV, XLSX | Venue map, Coach brief | No |
| GPS tracks of training or races | GPX, CSV | Strategy overview | No |
| Race results | CSV, XLSX | Strategy overview | No |
| Coach notes & written debriefs | TXT, MD, DOCX, PDF | Coach brief, Strategy overview | No |
| Photos of whiteboards, sketches, handwritten notes | JPG, PNG | Coach brief | No |
| Debrief or meeting transcripts | VTT, SRT, TXT or paste | Coach brief, Sailor brief | No |

Structured uploads (wind logs, tracks, results) are mapped but not parsed yet.

## Tests

```bash
PYTHONPATH=src uv run --python 3.12 --with pandas python -m backend.tests.test_backend   # from the repo root
```
