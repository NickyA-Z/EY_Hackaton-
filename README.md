# EY Hackathon: LA28 Olympic Sailing "Location Agent"

A Streamlit dashboard that turns venue, weather and past-race data into a briefing for the coach and sailor.

```
data/    strategy corpus (RAG), old race trajectories, weather, geodata
src/     backend/ (logic, RAG, ingest, geodata, tests) and frontend/ (the Streamlit app)
docs/    how it works: start at docs/README.md
```

```bash
uv sync
./src/frontend/run_local.sh          # dashboard on http://127.0.0.1:8503
PYTHONPATH=src uv run pytest -q      # tests (pytest sets the path itself; scripts need PYTHONPATH=src)
```

Documentation: [docs/README.md](docs/README.md). Data: [docs/data.md](docs/data.md).
