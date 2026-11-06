# Documentation

LA28 Olympic Sailing "Location Agent": a Streamlit dashboard (`src/frontend`) on top of data and logic
(`src/backend`) that turns venue, weather and past-race data into a briefing for the coach and sailor.

## Repository layout

```
data/      everything the system reads: strategy corpus (RAG), old race trajectories, weather, geodata
src/       all Python
  backend/   logic, data access, RAG, ingest, geodata pipeline, tests      (no Streamlit)
  frontend/  the Streamlit dashboard and the inbox app                      (no data logic)
docs/      this folder
```

Where each dataset lives is defined in one file, [`src/backend/paths.py`](../src/backend/paths.py). A test
(`src/backend/tests/test_paths.py`) fails if a module builds a data path by hand or if a folder is missing.

## Documents

| Read this | For |
| --- | --- |
| [data.md](data.md) | What is in `data/`, where each dataset came from, which code reads it |
| [frontend.md](frontend.md) | How the dashboard works: tabs, the 3D Previous strategy view, controls, code structure |
| [backend.md](backend.md) | The backend modules, and how coach uploads (text, photos, transcripts) are read and tagged |
| [rag.md](rag.md) | How the strategy RAG works: trigger rules, retrieval, briefs, CLI |
| [PLAN-AI-architecture.md](PLAN-AI-architecture.md) | Spec for the AI layer: routing, LangChain agents and tools, Sonnet 5.5 configuration, phases |
| [data_model.md](data_model.md) | The common weather / tide / track tables produced by the ingest layer, and the inbox app |
| [race_model.md](race_model.md) | The model that compares how boats sailed each leg with the time they gained |
| [geodata.md](geodata.md) | The bathymetry and terrain pipeline for the race venue |
| [location_agent.md](location_agent.md) | The AI strategist: briefing pack → model → strategy → evaluation by simulation |
| [location_agent_july_data.md](location_agent_july_data.md) | The July 2021–2026 wind, tide and current downloads the strategist is built on |
| [gps_analysis.md](gps_analysis.md) | What the winners' GPS tracks say: course, marks, wind, side of the course per beat |
| [strategy_design.md](strategy_design.md), [strategy_brainstorm.md](strategy_brainstorm.md) | Design notes for the AI strategy: data inventory, build order, ideas (written before the code; paths updated, content not) |
| [location_agent_features.md](location_agent_features.md) | The 9 feature blocks of the briefing pack and their 19 July values |

## Running things

Run from the repo root. `backend` and `frontend` live in `src/`, so scripts need it on the import path
(`pytest` is configured to do this by itself):

```bash
export PYTHONPATH=src

uv run pytest -q                                   # all tests
./src/frontend/run_local.sh                        # the dashboard, http://127.0.0.1:8503
uv run python -m backend.rag select --wind 22 --gust 27 --current 1.0   # which strategy documents apply
uv run python -m backend.ingest.run                # rebuild the weather tables in data/weather/processed
uv run python -m backend.race_model.model          # the race model
```

Secrets (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SAILSYNC_API_TOKEN`) are read from the environment or a
`.env` file in the repo root. Nothing in this repository stores a key.
