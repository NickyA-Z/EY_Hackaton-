"""Marine map bounds, vector conversion, and grid preparation."""

import math

import streamlit as st

from backend.retrieval.marine_api import (
    MARINE_API_URL,
    WEATHER_ARCHIVE_URL,
    fetch_grid_points,
)

MAP_LAYERS = {
    "Ocean currents": {
        "mode": "vector",
        "magnitude": "ocean_current_velocity",
        "direction": "ocean_current_direction",
        "direction_type": "toward",
        "unit": "kn",
        "speed_unit": "kn",
        "color": (64, 170, 255),
        "legend": "CURRENT SPEED",
        "description": (
            "Particles show where the current flows; colour shows speed."
        ),
    },
    "Waves": {
        "mode": "directional",
        "magnitude": "wave_height",
        "direction": "wave_direction",
        "direction_type": "from",
        "unit": "m",
        "color": (255, 159, 67),
        "legend": "WAVE HEIGHT",
        "description": "Particles show wave propagation; colour shows height.",
    },
    "Wind waves": {
        "mode": "directional",
        "magnitude": "wind_wave_height",
        "direction": "wind_wave_direction",
        "direction_type": "from",
        "unit": "m",
        "color": (192, 132, 252),
        "legend": "WIND-WAVE HEIGHT",
        "description": (
            "Particles show wind-wave propagation; colour shows height."
        ),
    },
    "Swell": {
        "mode": "directional",
        "magnitude": "swell_wave_height",
        "direction": "swell_wave_direction",
        "direction_type": "from",
        "unit": "m",
        "color": (74, 222, 128),
        "legend": "SWELL HEIGHT",
        "description": "Particles show swell propagation; colour shows height.",
    },
    "Wind": {
        "mode": "directional",
        "magnitude": "wind_speed_10m",
        "direction": "wind_direction_10m",
        "direction_type": "from",
        "unit": "kn",
        "speed_unit": "kn",
        "color": (245, 245, 250),
        "legend": "WIND SPEED",
        "description": "Particles show where the 10 m wind blows (ERA5 reanalysis); brightness shows speed.",
        "source_url": WEATHER_ARCHIVE_URL,  # not a marine variable
        "max_snap": 0.2,  # ERA5 grid is coarser than the marine grid
        "visual_scale": 0.15,  # knots are ~10x the current/wave magnitudes; keep particles readable
    },
}

GRID_ROWS = 10
GRID_COLUMNS = 17
REQUEST_BATCH_SIZE = 45


def _axis(start, end, count):
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


def regional_bounds(latitude, longitude):
    """Bias the LA view offshore so the current field fills most of the map."""
    return {
        "south": max(-90.0, latitude - 0.75),  # the API rejects coordinates beyond the poles / date line
        "north": min(90.0, latitude + 0.35),
        "west": max(-180.0, longitude - 1.65),
        "east": min(180.0, longitude + 0.25),
    }


def local_bounds(latitude, longitude, radius_m):
    """Bounds centred on a sailing area, with room around its official radius."""
    padding_m = max(radius_m * 3, 4_000)
    latitude_padding = padding_m / 111_320
    longitude_padding = padding_m / (
        111_320 * max(0.2, math.cos(math.radians(latitude)))
    )
    return {
        "south": latitude - latitude_padding,
        "north": latitude + latitude_padding,
        "west": longitude - longitude_padding,
        "east": longitude + longitude_padding,
    }


def _vector_components(magnitude, direction, direction_type):
    """Convert a bearing and magnitude into eastward/northward components."""
    if direction_type == "from":
        direction = (direction + 180) % 360
    angle = math.radians(direction)
    return magnitude * math.sin(angle), magnitude * math.cos(angle)


@st.cache_data(ttl=3600, show_spinner=False)
def get_map_grid(latitude, longitude, selected_date, layer_name, bounds=None, *, grid_rows=GRID_ROWS, grid_columns=GRID_COLUMNS):
    """Build one day of scalar or directional frames for a map layer.

    ``grid_rows`` x ``grid_columns`` points are requested; the dashboard asks for 5 x 5 around the selected location
    (one request batch) and keeps the 10 x 17 default for the regional map."""
    if layer_name not in MAP_LAYERS:
        raise ValueError(f"Unsupported map layer: {layer_name}")

    configuration = MAP_LAYERS[layer_name]
    mode = configuration["mode"]
    if mode == "scalar":
        variables = [configuration["value"]]
        value_variable = configuration["value"]
    else:
        variables = [
            configuration["magnitude"],
            configuration["direction"],
        ]
        value_variable = configuration["magnitude"]

    max_snap = configuration.get("max_snap", 0.11)
    bounds = bounds or regional_bounds(latitude, longitude)
    latitudes = _axis(bounds["south"], bounds["north"], grid_rows)
    longitudes = _axis(bounds["west"], bounds["east"], grid_columns)
    coordinates = [
        (grid_latitude, grid_longitude)
        for grid_latitude in latitudes
        for grid_longitude in longitudes
    ]
    results = fetch_grid_points(
        coordinates,
        selected_date,
        variables,
        batch_size=REQUEST_BATCH_SIZE,
        velocity_unit=configuration.get("speed_unit"),
        url=configuration.get("source_url", MARINE_API_URL),
    )

    if len(results) != len(coordinates):
        raise ValueError(
            f"Expected {len(coordinates)} grid points, received {len(results)}."
        )

    times = results[0]["hourly"]["time"]
    frames = []
    minimum_value = math.inf
    maximum_value = -math.inf

    for time_index, timestamp in enumerate(times):
        eastward = []
        northward = []
        values = []

        for coordinate, result in zip(coordinates, results):
            requested_latitude, requested_longitude = coordinate
            returned_latitude = result.get("latitude")
            returned_longitude = result.get("longitude")
            value_values = result.get("hourly", {}).get(value_variable, [])
            value = (
                value_values[time_index]
                if time_index < len(value_values)
                else None
            )

            snapped_too_far = (
                returned_latitude is None
                or returned_longitude is None
                or abs(returned_latitude - requested_latitude) > max_snap
                or abs(returned_longitude - requested_longitude) > max_snap
            )
            if value is None or snapped_too_far:
                eastward.append(None)
                northward.append(None)
                values.append(None)
                continue

            if mode == "scalar":
                eastward.append(None)
                northward.append(None)
            else:
                direction_values = result.get("hourly", {}).get(
                    configuration["direction"], []
                )
                direction = (
                    direction_values[time_index]
                    if time_index < len(direction_values)
                    else None
                )
                if direction is None:
                    eastward.append(None)
                    northward.append(None)
                    values.append(None)
                    continue
                u_component, v_component = _vector_components(
                    value,
                    direction,
                    configuration["direction_type"],
                )
                eastward.append(round(u_component, 5))
                northward.append(round(v_component, 5))

            values.append(round(value, 5))
            minimum_value = min(minimum_value, value)
            maximum_value = max(maximum_value, value)

        frames.append({
            "time": timestamp,
            "u": eastward,
            "v": northward,
            "value": values,
        })

    if math.isinf(minimum_value):
        minimum_value = 0.0
        maximum_value = 0.0

    return {
        "title": layer_name,
        "mode": mode,
        "legend_label": configuration["legend"],
        "description": configuration["description"],
        "bounds": bounds,
        "latitudes": latitudes,
        "longitudes": longitudes,
        "rows": grid_rows,
        "columns": grid_columns,
        "frames": frames,
        "minimum_value": round(minimum_value, 2),
        "maximum_value": round(maximum_value, 2),
        "unit": configuration["unit"],
        "color": list(configuration["color"]),
        "visual_scale": configuration.get("visual_scale", 1.0),
        "requested_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }
