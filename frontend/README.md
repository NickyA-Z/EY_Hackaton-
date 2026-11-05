# LA28 Location Agent dashboard

The compact top navigation groups the coach's race-prep flow into **Coach file**,
**Venue** (Map and Rules), **Briefs** (Coach and Sailor), **Strategy**, and
**Live** (`frontend/agent_views.py`, logic in `../backend`, see
`../backend/README.md`). **Venue · Geoinformation** shows the venue map and one **Load** control that
fetches location geodata, the regional map and the point series together. The regional
marine map (same logic as the former Map tool) is shown in **Live**, **Coach brief**
and **Venue · Geoinformation**. **Strategy** has what-if toggles (wind, strength, sea breeze,
risk appetite) and a scenario × appetite table. Picking a venue in Coach file sets the shared coordinates,
which can also be edited from the location popover.


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
./frontend/run_local.sh
```

Then open <http://127.0.0.1:8502>.

The launcher uses `uv` to create an isolated environment and install the
packages from `requirements.txt`. To use an alternative port:

```bash
PORT=8503 ./frontend/run_local.sh
```

## Manual start

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements frontend/requirements.txt \
  streamlit run frontend/frontend/dashboard.py
```

## Dashboard controls

1. Open the coordinate popover to review or edit the shared latitude and longitude.
2. Open **Live** or **Briefs · Coach** for the regional map on the race day (choose
   the marine layer above the map; it opens at the selected hour).
3. In **Venue · Geoinformation**, choose the sailing area, marine layer, point variable
   and dates, then press **Load** once: location, map and points appear together.
4. In the same view, open **Location** to choose an official LA28 sailing area from the
   local terrain and bathymetry JSON, then press **Use this location** to apply
   its coordinates to the other views.
5. Inspect the point summary, table, and time-series chart or download the
   result as CSV.

The data-tool segments switch between independent views while preserving the
latest loaded results. In the map view, changing the layer or historical date
reloads an existing map for that selection. **Current · Nov 3** resets the map
to the latest available date. Geolocation options are read only from
`geo_data/data/la28/json`.

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
| `frontend/dashboard.py` | Location Agent navigation, views, session state, metrics, tables, and charts |
| `frontend/agent_views.py` | Coach workflow, venue, rules, briefings, strategy overview, and live views |
| `frontend/current_map.py` | Leaflet basemap, particle and colour-field canvases, time controls, interpolation, and map rendering |
| `../backend/compute/map_grid.py` | Layer definitions, regional bounds, grid construction, masking, and direction-to-vector conversion |
| `../backend/retrieval/marine_api.py` | Open-Meteo point and regional-grid requests |
| `../backend/retrieval/geolocation.py` | Approved LA28 terrain and bathymetry JSON loading |
| `run_local.sh` | Reproducible local launcher and dependency environment |

The existing Location Agent layout remains the main interface. UI code is in
`frontend/`; marine calculations and data retrieval are grouped with the
existing root-level `backend/` package.
