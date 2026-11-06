"""Local LA28 geolocation data retrieval."""

import json
from pathlib import Path

import streamlit as st


GEO_DATA_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "geo_data"
    / "data"
    / "la28"
    / "json"
)
GEO_DATA_FILES = ("bathymetry.json", "terrain.json")


@st.cache_data(show_spinner=False)
def load_geolocation_data():
    """Load metadata only from the approved LA28 JSON directory."""
    datasets = {}
    for filename in GEO_DATA_FILES:
        path = GEO_DATA_DIRECTORY / filename
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        payload.pop("values", None)
        datasets[payload["dataset"]] = payload
    return datasets
