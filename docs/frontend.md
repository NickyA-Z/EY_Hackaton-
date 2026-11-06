# LA28 Location Agent dashboard

The single-row top navigation holds **Live**, **Venue** (Geoinformation and Rules),
**Briefs** (Coach and Sailor) and **Strategy** (`src/frontend/agent_views.py`, logic in
`src/backend`, see [backend.md](backend.md)). Two icons sit at the right: **upload** opens
the Coach file page (upload, preview and delete files) and **location** opens the
venue, class, race-day, time-of-day and coordinate settings. **Venue · Geoinformation** shows the venue map and one **Load** control that
fetches location geodata, the regional map and the point series together. The regional
marine map is shown in **Live**, **Coach brief** and **Venue · Geoinformation**; pick
any combination of marine layers (currents, waves, wind waves, swell, wind) and they
overlay, each in its own colour. **Strategy** has what-if toggles (wind, strength, sea breeze,
risk appetite) and a scenario × appetite table. Picking a venue in the location menu sets the shared coordinates,
which can also be edited there.


**AI panels.** (Strategy plan works for both courses; Belmont is simulated in the forecast wind, not against a real race.) The Coach brief page has an **AI briefing** button and the Strategy page has **Strategy plan** (a LangGraph workflow)
and **Ask the strategist**
(`src/frontend/ai_views.py`, logic in `src/backend/ai`, see [ai.md](ai.md)). Without a working model setting they show
"AI unavailable" and the page is otherwise unchanged.

This Streamlit dashboard runs locally and retrieves historical marine forecast
data from Open-Meteo for a selected coordinate, date range, and marine
variable.

The main view includes an Earth-style regional marine field. Directional layers
use moving particles and colour to show magnitude. Scalar conditions are kept
in point analysis, where trends and ranges are easier to interpret. Use the
embedded play button and hour slider to explore the historical map date selected
in the map view.
Click the map to inspect the local value and, when available, direction.

## Start the dashboard

From the project root:

```bash
./src/frontend/run_local.sh
```

Then open <http://127.0.0.1:8502>.

The launcher uses `uv` to create an isolated environment and install the
packages from `requirements.txt`. To use an alternative port:

```bash
PORT=8503 ./src/frontend/run_local.sh
```

## Manual start

```bash
cd src/frontend && PYTHONPATH=.. uv run --python 3.12 --with-requirements requirements.txt \
  streamlit run dashboard.py
```

## Dashboard controls

1. Open the location icon (top right) to set venue, class, race day, time of day and the shared latitude and longitude.
2. Open **Live** or **Briefs · Coach** for the regional map on the race day (choose
   the marine layer above the map; it opens at the selected hour).
3. In **Venue · Geoinformation**, choose the sailing area, marine layer, point variable
   and dates, then press **Load** once: location, map and points appear together.
4. Inspect the point summary, table, and time-series chart or download the
   result as CSV.

**Load** also applies the sailing area's coordinates to the shared location, so
Live and Coach brief use the same spot. Results stay until the next **Load**;
the "Loaded: …" line shows which selection they belong to. Sailing areas are read
only from the local geodata JSON.

## Previous strategy (3D)

The **Previous strategy** tab replays the first upwind leg of the three ILCA 7 races of
19 July 2026 (San Pedro OCR, SailSync GPS) as a 3D space-time cube: the horizontal plane
is the course and the vertical axis is time since the start gun, so each boat is a ribbon
climbing through the cube. Drag to rotate, scroll to zoom, hover a ribbon for the boat.

- **Information on the map** picks how much is drawn: *Tracks only*, *+ Weather* or
  *Full briefing*, or any mix of the individual layers (ground shadow, depth, time plane,
  start and mark, boat positions, three wind arrows, conditions table, left/right
  approach, strategy documents).
- **Colour by** finishing position, speed, or side of the course (left/right of the
  straight start→mark line, strong = aggressive).
- The **race clock** slider moves the teal time plane; wind arrows sit on that plane and
  show the wind at that moment.

What the data can and cannot do:

- GPS exists for 42-44 of the 61-62 boats per race. Holes in a track stay holes. One boat in
  race 2 (1,786 s on a 440 s median) is cut at 1.5 × the median leg so the time axis stays readable.
- All weather sources are 8-11 km from the course (Open-Meteo model cell, NOAA piers F, J, S,
  NDBC 46222) and hourly or 10-minute. They are regional values, not a wind field over the
  race area. SailSync's own wind has a direction (265°) and no speed.
- The strategy documents in `data/rag/` are synthetic. The tab shows which ones the
  conditions trigger and which inputs the rules could not check; it does not validate them.
- Depth is shaded over 0-30 m only; the race area is deeper, so the layer shows the
  breakwater and coast, not the seabed under the fleet.

Code: `src/frontend/previous_strategy_view.py` (scene and panels), `src/backend/previous_strategy.py`
(data, no Streamlit), tests in `src/backend/tests/test_previous_strategy.py`.

## Regional map layers

| Layer | Display | Open-Meteo variables |
| --- | --- | --- |
| Ocean currents | Animated direction; colour is speed | `ocean_current_velocity`, `ocean_current_direction` |
| Waves | Animated propagation; colour is height | `wave_height`, `wave_direction` |
| Wind waves | Animated propagation; colour is height | `wind_wave_height`, `wind_wave_direction` |
| Swell | Animated propagation; colour is height | `swell_wave_height`, `swell_wave_direction` |

Wave, wind-wave, and swell directions from the API describe where the waves
come **from**. The renderer reverses those bearings so particles travel toward
the propagation direction. Current direction already describes where water
flows **toward**.

## Point-analysis variables

Point charts are reserved for scalar values that are meaningful as historical
time series: current velocity, sea level, sea-surface temperature, wave height,
wave period, wave peak period, wind-wave height and period, and swell height and
period. Direction variables are shown on the regional map instead because a
standard line chart does not represent the circular 0–360° scale well.

The default location is Los Angeles Harbor at `33.72°N, 118.27°W`.

Ocean-current directions describe where the current is flowing toward: 0° is
north, 90° east, 180° south, and 270° west. The values are modelled marine data,
not measurements from a local instrument.

The map samples a 17 × 10 regional grid and caches each layer for one hour.
Particle motion is visually accelerated; it shows directional patterns rather
than literal travel distance per animation second. Open-Meteo notes that
coastal current accuracy is limited, so this view is not suitable for
navigation.

## Code structure

| File | Responsibility |
| --- | --- |
| `src/frontend/dashboard.py` | Location Agent navigation, views, session state, metrics, tables, and charts |
| `src/frontend/agent_views.py` | Coach workflow, venue, rules, briefings, strategy overview, and live views |
| `src/frontend/previous_strategy_view.py` | Previous strategy tab: 3D time-cube scene (pydeck), layer picker, conditions, left/right and strategy-document panels |
| `src/frontend/current_map.py` | Leaflet basemap, particle and colour-field canvases, time controls, interpolation, and map rendering |
| `src/backend/compute/map_grid.py` | Layer definitions, regional bounds, grid construction, masking, and direction-to-vector conversion |
| `src/backend/retrieval/marine_api.py` | Open-Meteo point and regional-grid requests |
| `src/backend/retrieval/geolocation.py` | Approved LA28 terrain and bathymetry JSON loading |
| `src/frontend/run_local.sh` | Reproducible local launcher and dependency environment |

The existing Location Agent layout remains the main interface. UI code is in
`src/frontend/`; marine calculations and data retrieval are grouped with the
`src/backend/` package.
