# Race model

Compares how boats sailed each leg (side of the course, how far out) with the time they gained, using SailSync data from San Pedro OCR 2026, ILCA 7: 19, 20 and 22 July (8 races).

| File | What it does |
|---|---|
| `fetch_data.py` | **Data.** Downloads results, the time each boat rounds each mark (with the wind on that leg), and the GPS tracks of the top 6 boats per race into `data/race_model/` |
| `model.py` | **Logic.** Mark positions (median boat position at rounding) → a ranking every minute → left/right and aggressive/conservative per leg → seconds gained → a simple model, tested on the race winners |

```bash
# 1. data (token stays in your environment; rerun if the rate limit stops it)
SAILSYNC_API_TOKEN=ssi_... .venv/bin/python -m backend.race_model.fetch_data
# 2. model
.venv/bin/python -m backend.race_model.model
# self-check on a synthetic race
.venv/bin/python -m backend.tests.test_race_model
```

Change the days or the number of boats with `DAYS` and `TOP_N` in `fetch_data.py`, and the aggressive threshold (25% of the leg length) with `AGGRESSIVE` in `model.py`.
