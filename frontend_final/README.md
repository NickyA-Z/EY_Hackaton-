# LA28 Location Agent dashboard

The single-row top navigation holds **Live**, **Venue** (Geoinformation and Rules),
**Briefs** (Coach and Sailor) and **Strategy** (`frontend/agent_views.py`, logic in
`../backend`, see `../backend/README.md`). Two icons sit at the right: **upload** opens
the Coach file page (upload, preview and delete files) and **location** opens the
venue, class, race-day, time-of-day and coordinate settings. **Venue · Geoinformation** shows the venue map and one **Load** control that
fetches location geodata, the regional map and the point series together. The regional
marine map is shown in **Live**, **Coach brief** and **Venue · Geoinformation**; pick
any combination of marine layers (currents, waves, wind waves, swell, wind) and they
overlay, each in its own colour. **Strategy** has what-if toggles (wind, strength, sea breeze,
risk appetite) and a scenario × appetite table. Picking a venue in the location menu sets the shared coordinates,
which can also be edited there.


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
./frontend_final/run_local.sh
```

Then open <http://127.0.0.1:8504>.

The launcher uses `uv` to create an isolated environment and install the
packages from `requirements.txt`. To use an alternative port:

```bash
PORT=8504 ./frontend_final/run_local.sh
```

## Manual start

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements frontend_final/requirements.txt \
  streamlit run frontend_final/frontend/dashboard.py
```

## Dashboard controls

0. Preparation opens on the event globe. Pick an LA 2028 venue (pin, list or **Enter venue →**) to dive into the dashboard; the globe icon in the header goes back. Non-LA pins are demo previews.
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

The map samples a 5 × 5 grid around the selected location, so each layer fits
in one API batch. It caches each layer for one hour.
Particle motion is visually accelerated; it shows directional patterns rather
than literal travel distance per animation second. Open-Meteo notes that
coastal current accuracy is limited, so this view is not suitable for
navigation.

## Code structure

| File | Responsibility |
| --- | --- |
| `frontend/dashboard.py` | Location Agent navigation, views, session state, metrics, tables, and charts |
| `frontend/agent_views.py` | Coach workflow, venue, rules, briefings, strategy overview, and live views |
| `frontend/globe.py` | Preparation landing globe (`st.components.v2`): event pins per boat class, dive-in to a venue, click to set the shared location |
| `frontend/current_map.py` | Leaflet basemap, particle and colour-field canvases, time controls, interpolation, and map rendering |
| `../backend/compute/map_grid.py` | Layer definitions, regional bounds, grid construction, masking, and direction-to-vector conversion |
| `../backend/retrieval/marine_api.py` | Open-Meteo point and regional-grid requests |
| `../backend/retrieval/geolocation.py` | Approved LA28 terrain and bathymetry JSON loading |
| `run_local.sh` | Reproducible local launcher and dependency environment |

The existing Location Agent layout remains the main interface. UI code is in
`frontend/`; marine calculations and data retrieval are grouped with the
existing root-level `backend/` package.
