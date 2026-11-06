# Race model data

Downloaded from SailSync by [backend/race_model/fetch_data.py](../../backend/race_model/fetch_data.py) and read by [backend/race_model/model.py](../../backend/race_model/model.py). The `tracks/` files were copied from `data/sailsync_api_results/`.

| Path | What it is |
|---|---|
| `event.json` | San Pedro OCR 2026 event: all days and fleets, with their session and race IDs |
| `2796/` | One **session** = one fleet on one day (ILCA 7, 19 Jul) |
| `2796/analysis.json` | The races in that session, the legs of each race (upwind/downwind) and the boat IDs |
| `2796/6068/` | One **race** (6068 = Race 2; 6067 = Race 1, 6069 = Race 3) |
| `6068/results.json` | Final result per boat: position, finish time, time taken |
| `6068/leg_1.json` | Leg 1 per boat: start time, **mark rounding time** and wind on that leg. The analysis lists only 1 leg per race, so no `leg_2.json` etc. exist |
| `2796/tracks/` | GPS per boat (`time_epoch, lat, lng`, about 1 point every 1.7 s), named by boat ID (`15373.csv`). All 44 boats |
