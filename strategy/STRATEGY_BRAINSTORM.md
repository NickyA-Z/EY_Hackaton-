# Location Agent: strategy brainstorm (LA28 sailing)

This document covers how the data we have can be turned into a race strategy the coach can act on, and how we could later prove that strategy works with a simulated AI agent.

The guide is `Boat brief and strategy.docx` (repo root). It says the product, the **Location Agent**, works **ashore**, before the race and between races. Olympic support-team rules ban devices, historical-data overlays and modelled forecasts on coach boats. So everything it produces must fit into the **08:00 briefing** and be memorisable by the sailors.

The agent's job, in the brief's words: show "where pressure and shifts usually are, and why" for a given wind direction and time of day. It also answers the **four pre-start questions**:

1. **Which side pays, and why?**
2. **Are the shifts oscillating or persistent, and on what cycle?**
3. **Which end of the start line is favoured?**
4. **What changes if the forecast is wrong?**

The POC venue is the **LA harbour**: the Port of LA boat course, "Hurricane Gulch", 16–28 July 2028.

---

## 1. Data we have

| Dataset | Folder | What it holds | Time dimension | Gaps |
|---|---|---|---|---|
| **Bathymetry** | `geo_data/data/la28/json/bathymetry.json` | ~10 m depth grid around 3 candidate race areas (NOAA coastal model, 2015) | Static | Not tide-corrected; no harbour-scale current |
| **Terrain** | `geo_data/data/la28/json/terrain.json` | ~30 m land heights, race areas + 10 km (Copernicus). Palos Verdes Hills 456 m, west of the Port of LA | Static | Surface model (includes buildings) |
| **Weather sample** | `src/weather_meteo_com/belmont_hourly.json` | Open-Meteo 15-min wind speed and direction (10 m), air temperature, humidity, rain at Belmont | **One day** (6 Nov 2025): a sample, not a climatology | Needs June–July history across years |
| **Marine data** | `sea_dashboard/marine_api.py` (Open-Meteo Marine API, called live) | Hourly gridded current speed and direction, sea level, sea temperature, waves, wind waves, swell | Historical and forecast, by date | Coarse grid (several km): harbour-scale current is model-level only |
| **Race GPS tracks** | `sailsync_api_results/winners/*.csv` | `time_epoch, lat, lng` every ~1.7 s for 4 ILCA 7 winners (Wearn AUS, Hanson GBR, Bos NED, Chiavarini ITA) | **19 July 2026, 14:05–17:16 PDT**, the San Pedro test regatta, probably 2–3 races | One fleet, one day |
| **June conditions pack** | `src/conditions_June_2026/` (+ `fetch_long_beach_data.py`) | June 2021–2026 around Belmont: CO-OPS measured wind (Long Beach Piers J/F/S), air temperature, LA tide predictions; METAR at Long Beach Airport (LGB); NDBC buoys 46025 (offshore wind, waves, water temperature) and 46222 (San Pedro waves); Open-Meteo archive at 5 points | Hourly, 6 Junes (the NDBC yearly files also include **July**) | Its Open-Meteo points snap to coarse **land** cells, so wind is underestimated: treat as low-confidence |
| **July conditions** | `src/conditions_July/` (+ `fetch_july.py`) | July 2021–2026: **HRRR model** (~3 km, 15-min, sea cells) at the Port of LA course, the Belmont course and inland Lakewood; **CO-OPS measured** hourly wind at Angels Gate, Pier 400 and Pier J, plus Angels Gate air temperature | 15-min (model) and hourly (measured), 6 Julys | Water temperature isn't offered at these stations (use NDBC buoys); HRRR direction is biased (see below) |

### What the new data tells us already
- **The real Port of LA course** (from the GPS tracks) is **outside the San Pedro breakwater**, around 33.687 N, −118.271 W, in a ~2 × 2.3 km area. That's ~2.8 km south of our `la_outer_harbor` candidate. The geo data already covers it.
- **Model vs measured on race day** (19 July 2026, HRRR at the course vs Angels Gate station):

  | PDT | HRRR | Angels Gate (measured) |
  |---|---|---|
  | 12:00 | 11.7 kt, 252° | 11.3 kt, 226° |
  | 14:00 | 14.8 kt, 259° | 11.7 kt, 231° |
  | 16:00 | 17.6 kt, 267° | 12.2 kt, 245° |
  | 17:00 | 15.2 kt, 268° | 16.7 kt, 250° |

  - **Speed: HRRR is usable**, typically within a few knots.
  - **Direction:** the **GPS tracks** settle it (see `strategy/gps_analysis/FINDINGS.md`). The wind *on the course* was **266–274°**.
    - **HRRR matches it.**
    - **Angels Gate reads 25–40° too far left**, bent locally by the breakwater and Palos Verdes, though its trend (veering) agrees.
  - **Consequence:**
    - **course direction and strength:** HRRR, refined by GPS-derived wind
    - **trend and timing of the sea breeze:** stations
    - the raw station direction must **not** be used as the course wind
- **Land–sea temperature:** inland Lakewood (HRRR land cell) and Angels Gate air temperature, minus buoy water temperature (NDBC), gives the sea-breeze driver.

### Still missing
- **Official course and start-line coordinates.** The GPS tracks give the 2026 test course; LA28 may differ.
- **Compass/heading logs and more fleets' GPS tracks** for broader validation.

---

## 2. From data to the coach's decisions

This maps the decision table in brief §4 to our data.

| Coach decision | Physical driver (brief §2) | Our data | How we'd compute it |
|---|---|---|---|
| **Favoured side of the beat/run** | Geographic shift / wind bend, terrain shadow, pressure | **Terrain** + wind direction | For each wind direction: the upwind obstacle height and distance (shadow = lighter, shiftier wind), and the shoreline orientation, since wind bends toward perpendicular to the shore and you sail to the inside of the bend. In the W–WSW sea breeze, Palos Verdes shelters the left (west) side of the Port of LA course. That fits the race reports: "everyone goes right". |
| **Pressure bands** | Stronger outside the breakwater (2–5 kt, per the race-week brief); acceleration along headlands | Terrain + bathymetry (land, breakwater, open water) + wind | Pressure modifier per course point: shadow lowers it, channelling raises it, long open-water fetch makes it steadier |
| **Oscillating vs persistent** | A building sea breeze veers ~5°/h (persistent right); otherwise the wind oscillates | Wind history (hourly / 15-min) | Split each day's direction series into a **trend** (°/h) and a **residual** (oscillation amplitude and period), by hour of day |
| **Sea-breeze timing and strength** | Land–sea temperature difference | Air temperature (weather) + sea temperature (marine) | Onset hour, build rate and veer rate from the June–July history, grouped by the temperature difference |
| **Start-line bias** | Wind direction vs line bearing; current at the line ends | Wind + course geometry + marine current | Bias angle = wind direction − line perpendicular → favoured end; adjust for the current set at each end |
| **Current strategy** | Seek less adverse current, usually in shallower water | **Bathymetry** + marine current + sea level (tide phase) | Current by tide phase. Shallower water usually means weaker adverse current; breakwater gaps (Angels Gate) concentrate flow. |
| **Laylines** | Shift trend + current set | Wind trend + current | Offset the layline for the current set and the expected veer |
| **Contingencies ("if X then Y")** | Sea breeze early, late or absent | Wind history (analogue days) | Scenario cards, e.g. "no sea breeze by 13:00 → light and shifty: play pressure over shifts" |

---

## 3. Strategy logic: an explainable rule engine

Coaches need to trust and memorise the output, so every recommendation comes with its **reason**.

**Inputs** for a given race day and hour:
- **Wind**: direction and speed, from a forecast or from similar past days.
- **Venue features**, precomputed from terrain and bathymetry for each wind direction and each course point:
  - shelter index (obstacle height ÷ distance)
  - over-water fetch
  - shoreline-bend direction
  - depth
  - inside/outside the breakwater
- **Sea-breeze pattern** from the history: onset, veer rate, oscillation amplitude and period.
- **Current and tide phase** from the marine data.
- **Course**: start line, windward and leeward marks.

**Rules** (from the brief's rules of thumb). Each adds a score to left or right, together with a reason:

| # | Rule | Effect |
|---|---|---|
| 1 | **Persistent veer** (sea breeze building, more than ~4°/h) | + right: "go toward the shift first" |
| 2 | **Geographic bend / shadow** | − the side with more shelter; + the inside of the bend |
| 3 | **Pressure** | + the side with more wind. In light air (< 8 kt) pressure beats shifts, so double its weight. |
| 4 | **Current** | + the side with less adverse (or more favourable) current upwind |
| 5 | **Oscillating** (small trend, large residual) | No side bias: "stay central, tack on headers", with the cycle length |
| 6 | **Start line** | Favoured end = the more upwind end, combined with the side the plan goes to |

**Output:**
- the favoured side (left / right / middle) with a confidence and its top reasons
- answers to all four pre-start questions
- the plan for the first beat

---

## 4. What the coach gets (brief §6)

- **Favoured-side map** for each wind direction (e.g. 225°, 247°, 270°) and hour (11:00–17:00). Course points are coloured by expected pressure and shelter, with arrows for wind bends and a one-line reason.
- **Morning briefing card**, printable and memorisable:
  - the four answers
  - "the plan for beat 1"
  - 2–3 contingency cards
  - the reasons behind each
- **Machine-readable JSON** with the same content, for the dashboard and the agent. It follows the grid-JSON conventions of `geo_data/`.

---

## 5. Future stage: AI agent and simulation

The aim is to show that the strategy wins, and to show it visually.

- **Wind field** W(x, y, t) is built from:
  - the base wind from a forecast or past day
  - the sea-breeze veer trend
  - random oscillations (amplitude and period from the history)
  - terrain modifiers (shadow lowers speed, bends turn direction)
- **Current field** comes from the marine data.
- **Boat model:** a simple speed table ("polar") for each class, giving boat speed by wind angle and wind speed (e.g. ILCA, 49er), plus a time penalty per tack.
- **Agents:**
  - **strategy agent**: follows the briefing card (go to the favoured side, tack on headers above a threshold, respect laylines)
  - **baselines**: always-left, always-right, stay-middle, random
- **Evaluation:** Monte Carlo over many simulated race days with different wind seeds and scenarios. Metrics: time to the windward mark, and the share of races the strategy agent beats each baseline.
- **Real-race benchmark:** replay **19 July 2026** with the measured wind and compare against the four winners' GPS tracks:
  - course and marks from the tracks
  - the ILCA speed table from their speeds
  - which side they took on each beat
  This checks both the strategy (did the agent pick the side the winners picked?) and the simulator (are its boat speeds realistic?).
- **Visual:** animated boat tracks over the bathymetry and terrain map with the wind field. This could plug into the `sea_dashboard` Streamlit app.
- **Later:** replace the rule-based agent with a learned one (e.g. reinforcement learning) and compare.

---

## 6. Proposed MVP order

1. **Wind climatology.** ✅ Pulled: July 2021–2026 (`src/conditions_July/`), HRRR model and measured CO-OPS stations, checked against race day. Next: turn it into the July sea-breeze profile by hour (onset, speed, veer rate, oscillation) at the Port of LA course.
1b. **GPS-track analysis.** ✅ Done (`strategy/gps_analysis/`):
   - 3 races
   - start line on the east side, windward mark ~1.25 km west
   - steady westerly with right shifts of 8–10° in a race
   - right paid in race 1
   - ILCA speeds 4.9 kn upwind / 7.4 kn downwind
2. **Venue features** from terrain and bathymetry for 8–16 wind directions over the candidate course: shelter, fetch, bend, depth.
3. **Rule engine**: four answers, favoured side and reasons for (wind direction, hour).
4. **Briefing card** (Markdown/PDF) + JSON.
5. **Simulator + agents + evaluation**, if time allows.

## Open questions for the team
- July history is pulled (`src/conditions_July/`) and June history is in `src/conditions_June_2026/`. Do we merge them into one data model (the June pack's "any format → one data model" idea)?
- Can we get GPS tracks for more fleets or days of the 2026 test events (SailSync event 2796), and the official LA28 course?
- Which boat class to simulate first? Suggestion: ILCA, single-handed, with the simplest polar.
