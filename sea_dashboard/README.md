# LA28 Location Agent dashboard

Top row: the coach's race-prep flow — **Coach file → Venue map → Venue rules →
Coach brief → Sailor brief → Strategy overview → Live** (`agent_views.py`, logic
in `../backend`, see `../backend/README.md`). Second row: the marine-data views
below (Map layer, Point chart, Geolocation). Picking a venue in Coach file sets
the shared latitude/longitude.


This Streamlit dashboard runs locally and retrieves historical marine forecast
data from Open-Meteo for a selected coordinate, date range, and marine
variable.

The main view includes an Earth-style regional marine field. Directional layers
use moving particles, while scalar layers use a colour surface. Use the embedded
play button and hour slider to explore the end date selected in the sidebar.
Click the map to inspect the local value and, when available, direction.

## Start the dashboard

From the project root:

```bash
./sea_dashboard/run_local.sh
```

Then open <http://127.0.0.1:8501>.

The launcher uses `uv` to create an isolated environment and install the
packages from `requirements.txt`. To use an alternative port:

```bash
PORT=8502 ./sea_dashboard/run_local.sh
```

## Manual start

```bash
cd sea_dashboard
uv run --python 3.12 --with-requirements requirements.txt \
  streamlit run dashboard.py
```

## Dashboard controls

1. Enter the latitude and longitude in the top header.
2. Press **Map layer** to open the regional-map view, choose a layer and
   historical date, then press **Load map**.
3. Press **Point chart** to open the point-data view, choose a date range and
   variable, then press **Retrieve data**.
4. Press **Geolocation** to select an official LA28 sailing area from the
   local terrain and bathymetry JSON, then press **Use this location** to apply
   its coordinates to the other views.
5. Inspect the point summary, table, and time-series chart or download the
   result as CSV.

The three header buttons switch between independent views while preserving the
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
| Wave height | Colour field | `wave_height` |
| Wave period | Colour field | `wave_period` |
| Sea temperature | Colour field | `sea_surface_temperature` |
| Sea level | Colour field | `sea_level_height_msl` |

Wave, wind-wave, and swell directions from the API describe where the waves
come **from**. The renderer reverses those bearings so particles travel toward
the propagation direction. Current direction already describes where water
flows **toward**.

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
| `dashboard.py` | Streamlit controls, session state, metrics, tables, charts, and error presentation |
| `marine_api.py` | Open-Meteo requests, layer definitions, caching, spatial grid construction, masking, and direction-to-vector conversion |
| `current_map.py` | Leaflet basemap, particle and colour-field canvases, time controls, interpolation, and map rendering |
| `run_local.sh` | Reproducible local launcher and dependency environment |

This keeps external-data logic independent from presentation, so API changes
can be handled without editing the map renderer or dashboard layout.
