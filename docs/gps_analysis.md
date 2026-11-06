# GPS-track findings: San Pedro test regatta, 19 July 2026 (ILCA 7)

**Data:** `data/trajectories/sailsync/winners/`: four winners' tracks (Wearn AUS, Hanson GBR, Bos NED, Chiavarini ITA), 14:05–17:16 PDT, one point every ~1.7 s.
**Script:** `analyse_tracks.py` (plain geometry, no AI) → `results/` (`summary.json`, `legs.csv`, `wind_from_gps.csv`, `marks.json`).
**Re-run** from the repo root: `PYTHONPATH=src python -m backend.gps_analysis.analyse_tracks` (needs numpy and pandas; takes ~10 s).

## 1. Races and course
| Race | Start | End | Start line (4 boats at the gun) |
|---|---|---|---|
| 1 | 14:13 | 14:52 | runs N–S, ~300 m long, at ≈ 33.6877–33.6904 N, −118.2684 W |
| 2 | 15:23 | 16:05 | same area, ~25 m further east |
| 3 | 16:29 | 17:16 | same area, slightly further north |

- **Course:** windward/leeward with **the start on the east side and the windward mark ~1.2–1.3 km west**. It sits outside the San Pedro breakwater, west of Angels Gate.
- **Windward marks** (furthest-upwind point of beats that visibly round):
  - **W1** 33.6898 N, −118.2816 W (races 1–2)
  - **W3** 33.6931 N, −118.2808 W (race 3, moved ~400 m north)
- **W2** (33.6831, −118.2763) comes from the later, shorter beats. It's low confidence because of tracker gaps.
- **Data quality:** all four tracks have **common 5–13 min gaps**, mostly around mark roundings. Only 9 of 20 beats are complete to the mark. Beats cut by a gap still count for speed, but not for side-of-course.

## 2. Wind on the course, derived from the boats
Upwind, a boat sails ~45° either side of the wind, so the wind direction is the bisector of the two tack headings. This is GPS-derived wind, as the brief describes.

| PDT | **GPS (on course)** | HRRR model at course | Angels Gate station (measured) |
|---|---|---|---|
| 14:00 | **270°** | 259°, 14.8 kt | 231°, 11.7 kt |
| 15:00 | **266°** | 263°, 14.7 kt | 236°, 11.5 kt |
| 16:00 | **266°** | 267°, 17.6 kt | 245°, 12.2 kt |
| 17:00 | **274°** | 268°, 15.2 kt | 250°, 16.7 kt |

| Race | Wind (GPS) | Shift during race | Oscillation (SD) | Tack angle |
|---|---|---|---|---|
| 1 | 271° → 279° (281° at the 2nd beat) | **right shift ~+10°** | 2.8° | 85° |
| 2 | 268° → 265° | steady | 0.3° | 88° |
| 3 | 266° → 274° | **right shift ~+8°** | 1.5° | 85° |

**Takeaways for the strategy:**
- **The course wind is a steady westerly (~266–281°), with right shifts during races 1 and 3.** Oscillations are tiny (≤ 3°). This is not an "oscillating, tack on every header" day; it's **persistent/trending right**. That matches the brief's sea-breeze veer and World Sailing's "favoured right side" report.
- **The HRRR model gets the course wind direction right** (within ~5–10°).
- **The Angels Gate station reads 25–40° too far left**, probably because the breakwater and Palos Verdes bend the wind locally. Its **trend** (veering ~+6°/h) still agrees in sign.
- **Correction to earlier notes:** use **HRRR (or GPS) for direction on the course**, and Angels Gate only as a trend and timing signal, not as the course wind.

## 3. Side of course on the first beats
"Right" means right of the rhumb line from the start-line centre to the windward mark, looking toward the mark. Only beats that reach the mark without a tracker gap are counted in summaries; all boats are shown below.

| Race | Course skew (mark vs wind) | Wearn | Chiavarini | Hanson | Bos | Who reached the mark first |
|---|---|---|---|---|---|---|
| 1 | +3° (square) | **99 % right** | **83 % right** | 51 % | 25 % | Chiavarini 14:25:50, then Wearn 14:26:20 (both **right**); Bos (left) third |
| 2 | +9° | 87 % right | 41 % | 49 % | 28 % | unclear (gaps); no clear side |
| 3 | **+22°** (mark set to the right) | 4 % | 14 % | 12 % | 100 % right | port-heavy beat (59–77 % on port); a skewed course, not a side bet |

- **Race 1:** right paid. The two boats that went hard right led at the windward mark during a ~10° right shift, which is the textbook "go toward the persistent shift" rule (brief §2).
- **Race 3:** the race committee set the mark ~22° right of the wind, so the fleet spent most of the beat on **port**. This matches "launching off the line on port" in the World Sailing report.
- **Caveat:** 4 boats, one day, and tracker gaps. This is evidence, not proof. More fleets and days from SailSync event 2796 would make it robust.

## 4. Boat performance (ILCA 7, ~12–17 kt)
| | Speed (median) | VMG (median) | Other |
|---|---|---|---|
| Upwind | **4.9 kn** | **3.5 kn** | tack angle 85–88° (COG), ~2 tacks per beat, 63 % of time on port |
| Downwind | **7.4 kn** | **5.9 kn** | |

These numbers calibrate the boat speed table for the simulator (§5 of `../STRATEGY_BRAINSTORM.md`).

## 5. What this means for the Location Agent
1. **Course geometry is known:**
   - start line on the east side
   - windward mark ~1.25 km west
   - all outside the San Pedro breakwater
   Use it as the course in the rule engine and the simulator.
2. **Default afternoon pattern (Port of LA):** a steady westerly 266–274° with **right shifts of ~8–10° within a race**, few tacks, and the right side favoured on a square course. This answers brief questions 1 and 2 for this regime.
3. **Wind sources:**
   - **direction:** trust HRRR and GPS on the course
   - **timing and trend:** use station data
   - **never** use raw Angels Gate direction as the course wind
4. **Benchmark for the AI agent:** replay race 1 with the GPS wind. A strategy agent should choose **right** and arrive at W1 close to Chiavarini and Wearn's times.
