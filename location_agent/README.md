# Location Agent — front end v0.1

Streamlit front end for the four mockup screens: **1 Upload → 2 Venue map → 3 Briefing → 4 Live**.

```bash
./location_agent/run_local.sh        # then open http://127.0.0.1:8502
```

Data: `src/conditions_June_2026/data/raw` (Open-Meteo hourly wind June 2021–2026, NOAA tides).
Demo story: June 2021–2025 is history, June 2026 is replayed hour by hour as if live.

| Screen | What is real | What is still demo |
| --- | --- | --- |
| Upload | Uploads are mapped to the common model by file type/name | Files are not parsed yet; demo file set shown when empty |
| Venue map | Speed, favoured side, veer rate, sea-breeze onset, tide, day count all computed from history | Map is a schematic; pressure band position follows the favoured side |
| Briefing | 4 answers + Challenger findings + confidence from the same statistics; edit, export | "AI" is a rule engine; no LLM call yet |
| Live | Hourly replay vs briefing window; change suggestions; org warning when the change is ≥ 1 h ahead | Replay, not a live API |

| File | Job |
| --- | --- |
| `engine.py` | Pure logic: loading, statistics, briefing, live check |
| `app.py` | Streamlit screens |
| `test_engine.py` | `uv run --with pandas python test_engine.py` |
