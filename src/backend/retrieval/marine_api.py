"""Open-Meteo marine API retrieval functions."""

import pandas as pd
import requests
import streamlit as st

from backend.venue_time import open_meteo_to_local, open_meteo_to_local_labels


MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
# 10 m wind for the map's Wind layer (ERA5 reanalysis, 1940 onwards).
WEATHER_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

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

# Point charts focus on scalar values that are meaningful as time series.
# Direction variables remain part of MARINE_VARIABLES because the regional
# map combines them with their corresponding magnitude.
POINT_VARIABLES = [
    "ocean_current_velocity",
    "sea_level_height_msl",
    "sea_surface_temperature",
    "wave_height",
    "wave_period",
    "wave_peak_period",
    "wind_wave_height",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_period",
]

VARIABLE_LABELS = {
    variable: variable.replace("_", " ").title()
    for variable in MARINE_VARIABLES
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_marine_data(
    latitude,
    longitude,
    start_date,
    end_date,
    selected_variable,
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
    # The API labels times with one fixed offset (GMT-8 even in summer); use the real LA clock.
    dataframe["time"] = open_meteo_to_local(dataframe["time"], data.get("utc_offset_seconds"))
    return dataframe, data


def fetch_grid_points(
    coordinates,
    selected_date,
    variables,
    batch_size,
    velocity_unit=None,
    url=MARINE_API_URL,
):
    """Retrieve spatial points in URL-safe request batches (marine API unless `url` says otherwise)."""
    results = []
    for offset in range(0, len(coordinates), batch_size):
        batch = coordinates[offset:offset + batch_size]
        params = {
            "latitude": ",".join(f"{point[0]:.5f}" for point in batch),
            "longitude": ",".join(f"{point[1]:.5f}" for point in batch),
            "start_date": str(selected_date),
            "end_date": str(selected_date),
            "hourly": ",".join(variables),
            "timezone": "America/Los_Angeles",
        }
        if url == MARINE_API_URL:
            params["cell_selection"] = "sea"
        if velocity_unit:
            params["wind_speed_unit"] = velocity_unit
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        for point in payload if isinstance(payload, list) else [payload]:
            hourly = point.get("hourly", {})
            if "time" in hourly:   # relabel with the real LA clock so map hours match the briefs
                hourly["time"] = open_meteo_to_local_labels(hourly["time"], point.get("utc_offset_seconds"))
            results.append(point)
    return results
