# Location Agent: features = the brief's 9 strategic building blocks

The briefing pack is organised exactly as the **strategic building blocks** in `Boat brief and strategy.docx` §2, the things a coach "reads". It contains **numbers only**: no labels, verdicts, thresholds or advice. The brief's definitions and rules of thumb will be given to the AI in the next step (system prompt), and the AI weighs these numbers against them.

```bash
python -m location_agent.ingest
python -m location_agent.features --date 2026-07-19 --area port_la_course
python -m location_agent.features --date 2026-07-19 --area port_la_course --no-backtest
python -m location_agent.features --date 2026-07-19 --area belmont_course
```
- **`ingest`** builds the standard table (~5 s).
- **`features`** builds the pack (~30 s). By default it's a **backtest**; `--no-backtest` gives hindsight, including that day's GPS lessons.

Output: `location_agent/output/<date>_<area>/briefing_pack.json`, about 10 KB (~2,600 tokens).

**Every block has the same shape:**
```json
{"evidence": {...numbers with units...},
 "venue_percentiles": {...},
 "data_sources": [...],
 "data_quality": "..."}
```
- **Venue percentile** = the % of July days in the climatology with a value ≤ the race-day value. It says how typical or unusual a number is **at this venue**, without inventing a cut-off.
- **Backtest** = only race-morning knowledge:
  - climatology leaves out the race year
  - measured race-day data stops at 11:00
  - reports published on or after the race day are excluded
  - **race-day wind = the HRRR forecast issued ~24 h before** (Open-Meteo previous runs, hourly; available from 2024)
- **Hindsight** (`--no-backtest`): race-day wind = near-real-time HRRR (15-min), all data included.
- The pack states which one it used in `context.race_day_wind_source`. Race-day numbers sit under `race_day` keys. The word "forecast" isn't used for model output any more.

---

## Step 1: Standardisation (`ingest.py`)
One long table, `location_agent/data/conditions_july.parquet`: **422,542 rows**, 1.6 MB.

| Column | Meaning |
|---|---|
| `time_utc` | UTC |
| `site` | e.g. `port_la_course`, `angels_gate`, `buoy_46222`, `tide_los_angeles`, `current_port_la_course` (positions in `data/sites.json`) |
| `variable` / `value` / `unit` | wind_speed **kn**, wind_gust kn, wind_dir_from **deg (from)**, air_temp / water_temp °C, wave_height m, wave_period s, tide_height / tide_high / tide_low **m above MLLW**, current_speed **kn**, current_dir_to **deg (towards)** |
| `source` / `quality` | hrrr / coops / ndbc / open_meteo / gps · model / measured / predicted / gps_derived |

| Source | Sites | Years (July) |
|---|---|---|
| HRRR model, 15 min | Port of LA course, Belmont course (sea cells), inland Lakewood (land cell) | 2021–2026 |
| NOAA CO-OPS measured, hourly | Angels Gate, Pier 400, Pier J (wind); Angels Gate (air temperature) | 2021–2026 (gaps 2021–24) |
| **NOAA CO-OPS tide predictions** | Los Angeles 9410660 (hourly + high/low) | 2021–2026 |
| **Open-Meteo marine current (model), hourly** | cells nearest the Port of LA and Belmont courses | 2022–2026 |
| NDBC buoys | 46222 San Pedro (waves, sea temperature), 46025 Santa Monica Basin (wind, waves) | 2021–2025 |
| GPS-derived | course wind direction, 19 Jul 2026 | 2026 |

---

## Step 2: The 9 building blocks (`features.py`)
For each block: **the brief's meaning and rule** (shown here for the reader; the AI gets it in its prompt) → **data** → **computation** → **19 Jul 2026 values** (Port of LA, 13:00–17:00).

**Which 19 Jul values below:** race-day numbers in the block sections are the **hindsight** values (near-real-time HRRR). The **backtest** pack, which is what the AI gets in a fair test, uses the day-ahead forecast instead:

| Race-day number | Backtest (forecast issued ~24 h ahead) | Hindsight (near-real-time) |
|---|---|---|
| Swing size | 2.3° (72nd pct) | 2.5° |
| Veer 12:00–17:00 | **+2.6°/h** (50th pct) | +3.7°/h |
| Direction, window start → end | 257° → 261° | 259° → 268° |
| Race-window speed | 16.3 kt (14.4–17.9), 79th pct | 15.8 kt (12.6–18.6) |
| Sea-breeze onset / peak | **12:00** / 17.9 kt | 10:45 / 18.6 kt |
| Inland 14:00 temperature / land–sea ΔT | 30.1 °C / **10.0 °C** (71st pct) | 33.0 °C / 12.9 °C |
| Start line | south end 67 m upwind (−13°) | south end 56 m (−11°) |
| Course vs Belmont direction | +26° | +29° |

The honest backtest gives a **weaker right-veer and sea-breeze signal** than hindsight, which is a fairer test for the AI.

### 1. Oscillating shifts
- **Brief:** the wind swings back and forth around a mean direction. Rule: tack on headers, stay near the middle; this is the default pattern.
- **Data:** HRRR 15-min direction at the course; Angels Gate hourly direction (measured).
- **Computation:**
  - Fit a straight line (the trend) through the race-window direction.
  - The **swing size** is the standard deviation of what's left around it.
  - The **swing period** is 2 × the first lag where those leftovers stop being correlated (autocorrelation).
  - Done for the race-day forecast and for every July climatology day.
- **19 Jul:**
  - swing size **2.5°** (July median 2.5°, 25–75%: 1.9–3.9°), the **49th percentile**
  - period **60 min** (July median 90 min)
  - station swing size 3.7°
- **Caveat:** HRRR smooths short swings, so this only describes slow swings (≥ ~30 min).

### 2. Persistent shift
- **Brief:** the wind turns steadily one way (fronts, building sea breeze). Rule: sail toward the shift first ("bite the bullet").
- **Data:** HRRR at the course; Angels Gate measured.
- **Computation:**
  - **Veer rate** = slope of direction against time, in °/h; positive = clockwise = right shift.
  - Measured over 12:00–17:00 and over the race window.
  - Also the direction at the start and end of the window, the total turn, July spread, % of days veering, and July mean direction by hour.
- **19 Jul:**
  - forecast **+3.7°/h** (12:00–17:00), **61st percentile**; +3.0°/h in the window
  - **259° → 268°** (+9°) over the window
  - July: median +2.5°/h, **90% of days veer**
  - Angels Gate measured: +7.2°/h, 92% of days veer

### 3. Geographic shift / wind bend
- **Brief:** wind direction varies by location (shorelines, headlands). Rule: sail to the inside of the bend; wind tends to blow perpendicular off the shore.
- **Data:** HRRR (course, Belmont), Angels Gate and offshore buoy 46025 (measured), bathymetry land mask.
- **Computation:**
  - For each race-window hour in July: the course direction minus each other site's direction, then the median. Positive = the course wind is veered (more from the right) relative to that site.
  - Shoreline geometry: the nearest land (bearing and distance) and the main axis of the land within 3 km (from the land mask).
  - The median distance to land of the left and right lanes (300 m either side of the rhumb line).
- **19 Jul:**
  - course vs Angels Gate **+23°**, vs Belmont inshore **+32°** (race-day forecast +29°), vs offshore buoy **−6°**. The wind is more **backed toward the shore** and slightly more veered offshore.
  - nearest land bearing **18°** (NNE), **1.7 km** away, along a land axis of **89°** (the E–W San Pedro breakwater)
  - **right lane 1.4 km from land, left lane 2.0 km**

### 4. Pressure (puffs/bands)
- **Brief:** areas of stronger wind. Rule: in light air, pressure beats shifts; +3 kt can mean 30–40% more speed in light air vs 5–10% in heavy air.
- **Data:** HRRR (course, Belmont), CO-OPS Angels Gate and Pier 400, buoy 46025.
- **Computation:**
  - race-window speed: mean, min/max, and **gust minus mean** (puffiness)
  - hourly forecast and its difference from the July median
  - July median race-window speed at each site (outside vs inside the breakwater, offshore)
- **19 Jul:**
  - forecast **15.8 kt** (12.6–18.6), **68th percentile**
  - gust excess 0.8 kt (76th percentile)
  - July medians: course 14.5 kt · Angels Gate 12.2 · Belmont 11.1 · **Pier 400 (inside the harbour) 6.8** · offshore buoy 6.8
- **Caveat:** a 3 km model can't resolve left vs right pressure within a 1.2 km beat.

### 5. Sea breeze
- **Brief:** a thermal wind driven by the land–sea temperature difference. Rule: builds from late morning and typically veers while building (~5°/h).
- **Data:** HRRR inland Lakewood temperature and course wind; buoy 46222 sea temperature; Angels Gate measured morning wind; HRRR total cloud cover (inland and course).
- **Computation:**
  - **Onset** = the first hour of ≥ 8 kt from 225–295° held for 1 h. This is a measurement definition, not a decision rule.
  - Peak speed and time.
  - **Land–sea ΔT** = inland temperature at 14:00 minus sea temperature; its correlation with race-window wind and the knots per °C.
  - Measured morning wind compared with the station's own July normal for each hour (cancels the station's bias).
  - **Morning cloud (marine layer)** = mean total cloud 09:00–12:00. **Clears** = the first hour from 07:00 with cloud below 30 %. Both are set in `settings.yaml`.
    - July medians and spreads; % of days it never clears.
    - Correlation and slope of morning cloud vs onset hour and vs race-window speed.
    - Percentiles.
    - Total cloud is used, not low cloud, because the day-ahead forecast has no low-cloud values.
  - 19 Jul cloud (day-ahead):
    - **14 %** inland, clearing **09:00** (21st percentile; July median 37 %, clearing 10:00)
    - history: −0.42 kt in the race window per +10 % morning cloud (correlation −0.44)
- **19 Jul:**
  - forecast onset **10:45** (38th percentile = earlier than usual; July median 11:15)
  - peak **18.6 kt** (89th percentile)
  - ΔT **12.9 °C**, **95th percentile** (July median 8.5 °C; correlation 0.62; +0.71 kt per °C)
  - morning at Angels Gate: 4.5 → 8.0 kt from 09:00 to 11:00 (+0.9 kt vs normal at 11:00)
  - July: 3% of days with no sea breeze

### 6. Current / tide
- **Brief:** water movement shifts the "sailing wind" and the laylines. Rule: seek favourable or less adverse current, usually in shallower water when sailing against it.
- **Data:** CO-OPS tide predictions (Los Angeles 9410660); Open-Meteo modelled surface current; bathymetry.
- **Computation:**
  - race-day high/low times and heights; tide height at the window start and end; tide turns inside the window; daily range
  - modelled current speed and direction (towards) in the window, plus the July median
  - median depth of the left and right lanes
- **19 Jul:**
  - tides: low 07:35 (0.17 m) · **high 14:21 (1.49 m), inside the race window** · low 20:36
  - height 1.37 m at 13:00 → 1.12 m at 17:00; range 1.31 m
  - current **0.26 kt towards 138° (SE)**, 24th percentile (July median 0.40 kt)
  - depth: left −33 m, right −28 m
- **Caveat:** the current model is coarse, and its cell is ~2.5 km from the course.

### 7. Terrain effects
- **Brief:** wind shadows, acceleration and channelling by hills, cliffs, buildings and islands. Rule: offshore winds near land are shifty.
- **Data:** Copernicus terrain (30 m, includes buildings); bathymetry.
- **Computation:**
  - From each lane's midpoint, walk 12 km **upwind** in 30 m steps.
  - Record the open-water fetch and the strongest obstacle, using the **shelter index = height ÷ distance**.
  - Repeat for wind directions 230–340°.
  - Also the location of the highest terrain.
- **19 Jul:**
  - forecast wind 262°: **fetch over 12 km and shelter index 0 on both sides**
  - Palos Verdes (456 m) is at **315°, 8.9 km** from the start
  - the shelter index only becomes non-zero for winds **300–340°**: at 310° right 0.040 / left 0.023; at 320° left 0.052 / right 0.044

### 8. Start-line bias
- **Brief:** one end of the line is upwind of the other. Rule: measure the wind against the line bearing; start at the favoured end and on the side you want to go.
- **Data:** start line from `course/<date>.json` (19 Jul: N–S, 332 m, derived from all 44 boats at the gun); HRRR forecast direction in the first race hour.
- **Computation:**
  - Project both line ends onto the upwind direction; the difference is the **upwind advantage in metres** (= length × sin(bias)).
  - **Bias angle** = wind direction minus the line perpendicular pointing up the course.
  - Repeated for the wind 5° left and 5° right.
- **19 Jul:**
  - wind 259° vs perpendicular 270° → **−11°**, **south end 56 m upwind** (5° left: 81 m; 5° right: 30 m)
  - forecast veer +3.0°/h
  - south end = left, looking upwind
- **Caveat:** the data doesn't say which end is the committee boat.

### 9. Laylines
- **Brief:** the line from which you can just reach the mark. Rule: avoid reaching them early; shifts and current move them.
- **Data:** course geometry from `course/<date>.json`; HRRR veer; modelled current; ILCA class rule of thumb (tack angle 90°, upwind VMG 3.4 kt). These are deliberately not measured from race-day tracks.
- **Computation:**
  - **beat time** = beat length ÷ VMG
  - **wind turn over the beat** = veer × time
  - **current set** = current × time, split into components along the course (towards the mark) and across it (towards the right)
  - **layline angle to the wind** = tack angle ÷ 2
- **19 Jul:**
  - beat 1,225 m at 274°
  - about **11.3 min**, wind turn over the beat **0.6°**
  - current set **90 m**: **−65 m along** (pushed back) and **−62 m across** (pushed left)
  - layline angle 42.5°

---

## Context and supporting sections (also numbers or quoted facts only)
| Section | Contents |
|---|---|
| `context` | venue, race day, window, class, mode, climatology years, race-day wind source, conventions, **settings used**, course (start-line ends, length, bearing; windward mark; rhumb bearing; beat length) |
| `coach_questions_to_blocks` | which blocks answer each of the brief's four questions: Q1 side → 2, 3, 4, 6, 7 · Q2 shift type → 1, 2, 5 · Q3 start end → 8 · Q4 contingencies → 5, 4, 2 |
| `prior_knowledge` | dated venue quotes from the brief. Backtest keeps only those published before the race (19 Jul: the 1932 report and the June 2026 Race Week briefing). |
| `data_caveats` | race-day wind source, Angels Gate bias, climatology coverage |
| `gps_lessons_same_day` | hindsight mode only: GPS wind per race, side per beat, speeds. Used later to score the AI. |

## Parameters you can change (`location_agent/settings.yaml`)
These are **measurement settings**: they decide *how* a number is computed. They are **not** decision thresholds, and they are **not** given to the AI as rules. Every pack records the values it used under `context.settings`.

To change one, edit its `value` in `settings.yaml` and rebuild the pack. `--window` and `--cutoff` on the command line override the first two for a single run.

| Setting | Value now | What it does | Blocks affected | Where the value came from |
|---|---|---|---|---|
| `race_window_local` | 13–17 | racing hours whose wind is summarised | all | 2026 races ran 14:13–17:16; Race Week peak 14:00–17:00 |
| `morning_cutoff_hour` | 11 | backtest: last measured race-day hour | 5 | choice ≈ dock-out time; 8 = strict 08:00 briefing |
| `veer_window_local` | 12–17 | hours used to fit the turn rate (°/h) | 2, 9 | brief: sea breeze builds from late morning |
| `climatology_hours_local` | 10–18 | hours shown in typical-day tables | 2, 4 | onset → end of racing |
| `sea_breeze_onset` | ≥ 8 kt from 225–295° for 1 h | defines "established" to *measure* onset time | 5 | choice: steady racing breeze; WSW–WNW sector around the July mean |
| `land_sea_dT_inland_hour` | 14 | inland temperature hour used for the land–sea difference | 5 | brief (temperature drives the sea breeze); ~peak heating |
| `lanes` | 300 m, 9 points, 10–90% of the beat | where "left" and "right" are sampled | 3, 6, 7 | choice: 2026 boats went 150–650 m off the rhumb line |
| `land_definition` | bathymetry ≥ 0 m; terrain > 1 m land, > 2 m obstacle | land vs water | 3, 7 | data datums; small noise margins |
| `upwind_terrain_scan` | 12 km, 30 m steps | upwind obstacle search | 7 | terrain raster extent; raster resolution |
| `shelter_table_dirs_deg` | 230–340° step 10 | the "which wind directions give a shadow" table | 7 | sea-breeze sector + NW |
| `shoreline_radius_m` | 3,000 | land used for nearest-land / shoreline axis | 3 | covers the breakwater 1.4–2 km away |
| `start_line_sensitivity_deg` | 5 | start bias also computed for wind ±this | 8 | choice ≈ typical direction error |
| `boat_class_priors` | ILCA 7, tack angle 90°, upwind VMG 3.4 kt | beat time and layline angle | 9 | generic single-hander rule of thumb, deliberately **not** from the race-day tracks; replace with ILCA 7 polars |
| `morning_cloud_hours_local` | 09–12 | hours averaged for morning cloud | 5 | measurement window before the sea-breeze onset |
| `cloud_clear_pct` | 30 % | cloud below this = "cleared" (burn-off time) | 5 | measurement definition (mostly clear sky) |

Tested: changing `lanes.offset_m` from 300 to 500 changes only blocks 3, 6 and 7. With the defaults, the pack is identical to before the settings file existed.

**Not settings, but methods** (change them in `features.py` if needed):
- **Swing period:** 2 × the first zero-crossing of the autocorrelation.
- **Percentiles:** % of July days with a value ≤ the race-day value.
- **Upwind advantage on the start line:** projection of the line onto the wind direction.

**Rule-of-thumb numbers the AI reads** live as text in `prompt.py` (`SYSTEM_PROMPT`):
- **From the brief:** sea breeze ~5°/h; +3 kt is worth 30–40% in light air; Ullman's ΔT rule.
- **My addition:** shelter strong at ~10× an obstacle's height, moderate at ~30×.

Edit that text to change what the AI is told.

## Known gaps
- **No race-day buoy data:** the sea temperature uses the July median.
- **The current is a coarse model**, from a cell ~2.5 km away.
- **The race-day wind is a real day-ahead forecast only from 2024 onward.** For earlier dates, backtests fall back to near-real-time model output, and the pack says so.
- **Belmont uses a placeholder course.**
- **ILCA class numbers are a generic rule of thumb** (90°, 3.4 kt) until real ILCA 7 polars are available.
- **The course is derived from the boats' roundings.** Per race it gives 5–6 buoys:
  - start ends (2)
  - mark 1: race 1 ±38 m; races 2–3 ±100–140 m
  - mark 2: race 1 estimated from timing (32 boats' gate-to-gate time), uncertain
  - gate: 10–20 boats
  - finish: end of the last run (race 1: 7 boats, ±66 m), a short reach from the gate

  The features use only the start line and mark 1; the simulator (evaluation only) uses the whole course. Replace `course/<date>.json` when official data arrives.
