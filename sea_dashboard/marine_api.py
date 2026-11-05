"""Open-Meteo marine data access and current-vector grid preparation."""

import math

import pandas as pd
import requests
import streamlit as st


MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"

MARINE_VARIABLES = [
    "ocean_current_velocity",
    "ocean_current_direction",
    "sea_level_height_msl",
    "sea_surface_temperature",
    "wave_height",
    "wave_direction",
    "wave_period",
    "wave_peak_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
]

VARIABLE_LABELS = {
    variable: variable.replace("_", " ").title()
    for variable in MARINE_VARIABLES
}

MAP_LAYERS = {
    "Ocean currents": {
        "mode": "vector",
        "magnitude": "ocean_current_velocity",
        "direction": "ocean_current_direction",
        "direction_type": "toward",
        "unit": "kn",
        "legend": "CURRENT SPEED",
        "description": "Particles follow the modelled surface current.",
    },
    "Waves": {
        "mode": "directional",
        "magnitude": "wave_height",
        "direction": "wave_direction",
        "direction_type": "from",
        "unit": "m",
        "legend": "WAVE HEIGHT",
        "description": "Particles travel in wave-propagation direction; colour shows height.",
    },
    "Wind waves": {
        "mode": "directional",
        "magnitude": "wind_wave_height",
        "direction": "wind_wave_direction",
        "direction_type": "from",
        "unit": "m",
        "legend": "WIND-WAVE HEIGHT",
        "description": "Particles travel with wind waves; colour shows height.",
    },
    "Swell": {
        "mode": "directional",
        "magnitude": "swell_wave_height",
        "direction": "swell_wave_direction",
        "direction_type": "from",
        "unit": "m",
        "legend": "SWELL HEIGHT",
        "description": "Particles travel in swell direction; colour shows height.",
    },
    "Wave height": {
        "mode": "scalar",
        "value": "wave_height",
        "unit": "m",
        "legend": "WAVE HEIGHT",
        "description": "Colour field of significant wave height.",
    },
    "Wave period": {
        "mode": "scalar",
        "value": "wave_period",
        "unit": "s",
        "legend": "WAVE PERIOD",
        "description": "Colour field of mean wave period.",
    },
    "Sea temperature": {
        "mode": "scalar",
        "value": "sea_surface_temperature",
        "unit": "°C",
        "legend": "SEA TEMPERATURE",
        "description": "Colour field of sea-surface temperature.",
    },
    "Sea level": {
        "mode": "scalar",
        "value": "sea_level_height_msl",
        "unit": "m",
        "legend": "SEA-LEVEL HEIGHT",
        "description": "Colour field relative to global mean sea level.",
    },
}

GRID_ROWS = 10
GRID_COLUMNS = 17
REQUEST_BATCH_SIZE = 45


@st.cache_data(ttl=3600, show_spinner=False)
def get_marine_data(
    latitude,
    longitude,
    start_date,
    end_date,
    selected_variable
):
    """Retrieve a historical marine time series for one coordinate."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "hourly": selected_variable,
        "timezone": "America/Los_Angeles",
        "cell_selection": "sea",
    }
    response = requests.get(MARINE_API_URL, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    dataframe = pd.DataFrame(data["hourly"])
    dataframe["time"] = pd.to_datetime(dataframe["time"])
    return dataframe, data


def _axis(start, end, count):
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


def regional_bounds(latitude, longitude):
    """Bias the LA view offshore so the current field fills most of the map."""
    return {
        "south": latitude - 0.75,
        "north": latitude + 0.35,
        "west": longitude - 1.65,
        "east": longitude + 0.25,
    }


def _fetch_grid_points(coordinates, selected_date, variables, velocity_unit=None):
    """Fetch spatial points in batches that keep request URLs manageable."""
    results = []
    for offset in range(0, len(coordinates), REQUEST_BATCH_SIZE):
        batch = coordinates[offset:offset + REQUEST_BATCH_SIZE]
        params = {
            "latitude": ",".join(f"{point[0]:.5f}" for point in batch),
            "longitude": ",".join(f"{point[1]:.5f}" for point in batch),
            "start_date": str(selected_date),
            "end_date": str(selected_date),
            "hourly": ",".join(variables),
            "timezone": "America/Los_Angeles",
            "cell_selection": "sea",
        }
        if velocity_unit:
            params["wind_speed_unit"] = velocity_unit
        response = requests.get(MARINE_API_URL, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        results.extend(payload if isinstance(payload, list) else [payload])
    return results


def _vector_components(magnitude, direction, direction_type):
    """Convert a bearing and magnitude into eastward/northward components."""
    if direction_type == "from":
        direction = (direction + 180) % 360
    angle = math.radians(direction)
    return magnitude * math.sin(angle), magnitude * math.cos(angle)


@st.cache_data(ttl=3600, show_spinner=False)
def get_map_grid(latitude, longitude, selected_date, layer_name):
    """Build one day of scalar or directional frames for a map layer."""
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

    bounds = regional_bounds(latitude, longitude)
    latitudes = _axis(bounds["south"], bounds["north"], GRID_ROWS)
    longitudes = _axis(bounds["west"], bounds["east"], GRID_COLUMNS)
    coordinates = [
        (grid_latitude, grid_longitude)
        for grid_latitude in latitudes
        for grid_longitude in longitudes
    ]
    results = _fetch_grid_points(
        coordinates,
        selected_date,
        variables,
        velocity_unit="kn" if layer_name == "Ocean currents" else None,
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
                or abs(returned_latitude - requested_latitude) > 0.11
                or abs(returned_longitude - requested_longitude) > 0.11
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
        "rows": GRID_ROWS,
        "columns": GRID_COLUMNS,
        "frames": frames,
        "minimum_value": round(minimum_value, 2),
        "maximum_value": round(maximum_value, 2),
        "unit": configuration["unit"],
        "requested_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }
