from datetime import date
import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import agent_views
from current_map import render_current_map
from marine_api import (
    MAP_LAYERS,
    MARINE_VARIABLES,
    VARIABLE_LABELS,
    get_map_grid,
    get_marine_data,
)

RESULT_VIEW_HEIGHT = 500
EARLIEST_MAP_DATE = date(1940, 1, 1)
LATEST_MAP_DATE = date(2026, 11, 3)
GEO_DATA_DIRECTORY = (
    Path(__file__).resolve().parent.parent / "geo_data" / "data" / "la28" / "json"
)
GEO_DATA_FILES = ("bathymetry.json", "terrain.json")


def select_view(view):
    """Open one of the dashboard's main views."""
    st.session_state["active_view"] = view


def select_latest_map_date():
    """Reset the historical map picker to the latest available date."""
    st.session_state["selected_map_date"] = LATEST_MAP_DATE


def select_geolocation(area):
    """Apply a JSON-defined LA28 area to the shared coordinates."""
    st.session_state["selected_latitude"] = float(area["lat"])
    st.session_state["selected_longitude"] = float(area["lon"])


@st.cache_data(show_spinner=False)
def load_geolocation_data():
    """Load LA28 geolocation metadata only from the approved JSON folder."""
    datasets = {}
    for filename in GEO_DATA_FILES:
        path = GEO_DATA_DIRECTORY / filename
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        payload.pop("values", None)
        datasets[payload["dataset"]] = payload
    return datasets


def render_header():
    """Render top navigation and shared location controls."""
    active_view = st.session_state.setdefault("active_view", "coach")
    st.session_state.setdefault("selected_latitude", 33.72)
    st.session_state.setdefault("selected_longitude", -118.27)

    with st.container(border=True):
        for column, (view, label) in zip(
            st.columns(len(agent_views.AGENT_VIEWS)), agent_views.AGENT_VIEWS.items()
        ):
            column.button(
                label,
                key=f"show_{view}_view",
                type="primary" if active_view == view else "secondary",
                width="stretch",
                on_click=select_view,
                args=(view,),
            )
        (
            map_navigation,
            chart_navigation,
            geolocation_navigation,
            latitude_column,
            longitude_column,
        ) = st.columns([1, 1, 1, 1.25, 1.25])

        map_navigation.button(
            "Map layer",
            key="show_map_view",
            type="primary" if active_view == "map" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("map",),
        )
        chart_navigation.button(
            "Point chart",
            key="show_point_view",
            type="primary" if active_view == "point" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("point",),
        )
        geolocation_navigation.button(
            "Geolocation",
            key="show_geolocation_view",
            type="primary" if active_view == "geolocation" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("geolocation",),
        )
        latitude = latitude_column.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            format="%.5f",
            key="selected_latitude",
        )
        longitude = longitude_column.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            format="%.5f",
            key="selected_longitude",
        )

    return latitude, longitude


def render_map_view(latitude, longitude, title="Map layer"):
    """Render the regional map controls and map result."""
    if title:
        st.header(title)

    layer_column, date_column, latest_column, load_column = st.columns(
        [1.5, 1.5, 1, 1]
    )
    map_layer = layer_column.selectbox(
        "Marine layer",
        list(MAP_LAYERS),
        help="Controls the animated regional map.",
        key="selected_map_layer",
    )
    map_date = date_column.date_input(
        "Historical map date",
        value=LATEST_MAP_DATE,
        min_value=EARLIEST_MAP_DATE,
        max_value=LATEST_MAP_DATE,
        key="selected_map_date",
        help=(
            "Choose any available date from January 1, 1940 through "
            "November 3, 2026."
        ),
    )
    latest_column.write("")
    latest_column.button(
        "Current · Nov 3",
        width="stretch",
        on_click=select_latest_map_date,
        help="Return the map to November 3, 2026.",
    )
    load_column.write("")
    load_map = load_column.button(
        "Load map",
        type="primary",
        width="stretch",
    )

    layer_configuration = MAP_LAYERS[map_layer]
    st.subheader(f"Regional map: {map_layer}")
    st.caption(
        f"{layer_configuration['description']} Use the map's play button or "
        f"hour slider to explore {map_date}."
    )

    map_signature = (latitude, longitude, str(map_date), map_layer)
    stored_map_signature = st.session_state.get("map_signature")
    should_load_map = load_map or (
        st.session_state.get("map_grid") is not None
        and stored_map_signature != map_signature
    )

    if should_load_map:
        try:
            with st.spinner(f"Building the regional {map_layer.lower()} field…"):
                st.session_state["map_grid"] = get_map_grid(
                    latitude,
                    longitude,
                    map_date,
                    map_layer,
                )
                st.session_state["map_signature"] = map_signature
        except requests.exceptions.RequestException as error:
            st.error(f"Could not load the regional map layer: {error}")
        except (KeyError, ValueError) as error:
            st.error(f"Unexpected regional map response: {error}")

    map_grid = st.session_state.get("map_grid")
    if not map_grid:
        st.info("Choose a layer and date, then press **Load map**.")
        return

    render_current_map(map_grid, height=RESULT_VIEW_HEIGHT)
    if map_grid["mode"] == "scalar":
        st.caption(
            "The interpolated colour field shows relative values across "
            "the model grid. Click the map for the local value."
        )
    else:
        st.caption(
            "Particle motion is visually accelerated to make direction "
            "readable. Click the map for the local value and direction."
        )


def render_point_result(result):
    """Render a stored point-data response."""
    dataframe = result["dataframe"]
    response_data = result["response_data"]
    selected_variable = result["variable"]
    start_date = result["start_date"]
    end_date = result["end_date"]

    st.subheader("Selected location")
    latitude_metric, longitude_metric, observations_metric, elevation_metric = (
        st.columns(4)
    )
    latitude_metric.metric("Requested latitude", f"{result['latitude']:.5f}")
    longitude_metric.metric("Requested longitude", f"{result['longitude']:.5f}")
    observations_metric.metric("Observations", len(dataframe))
    elevation = response_data.get("elevation")
    elevation_metric.metric(
        "Grid elevation",
        f"{elevation} m" if elevation is not None else "N/A",
    )

    st.subheader(f"Historical data: {VARIABLE_LABELS[selected_variable]}")
    if selected_variable not in dataframe.columns:
        st.warning("The selected variable was not returned.")
        return

    values = pd.to_numeric(dataframe[selected_variable], errors="coerce")
    unit = response_data.get("hourly_units", {}).get(selected_variable, "")

    minimum_metric, average_metric, maximum_metric = st.columns(3)
    minimum_metric.metric("Minimum", f"{values.min():.2f} {unit}".strip())
    average_metric.metric("Average", f"{values.mean():.2f} {unit}".strip())
    maximum_metric.metric("Maximum", f"{values.max():.2f} {unit}".strip())

    display_dataframe = dataframe[["time", selected_variable]].rename(
        columns={selected_variable: VARIABLE_LABELS[selected_variable]}
    )
    st.dataframe(
        display_dataframe,
        width="stretch",
        height=RESULT_VIEW_HEIGHT,
        hide_index=True,
    )

    st.subheader("Time series")
    chart_dataframe = dataframe.set_index("time")
    st.line_chart(
        chart_dataframe[selected_variable],
        y_label=(
            f"{VARIABLE_LABELS[selected_variable]} ({unit})"
            if unit
            else VARIABLE_LABELS[selected_variable]
        ),
    )

    csv = dataframe.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"{selected_variable}_{start_date}_{end_date}.csv",
        mime="text/csv",
    )

    st.caption(
        "Model grid-cell coordinates: "
        f"{response_data.get('latitude')}, {response_data.get('longitude')}"
    )
    if selected_variable == "ocean_current_direction":
        direction_note = (
            " Current direction shows where water flows toward: "
            "0° north, 90° east, 180° south, and 270° west."
        )
    elif selected_variable.endswith("_direction"):
        direction_note = (
            " Wave and swell directions describe where waves come from."
        )
    else:
        direction_note = ""
    st.caption(f"Source: Open-Meteo Marine API.{direction_note}")


def render_point_view(latitude, longitude):
    """Render point-chart controls and the latest point result."""
    st.header("Point chart")

    start_column, end_column, variable_column, retrieve_column = st.columns(
        [1, 1, 1.5, 1]
    )
    start_date = start_column.date_input(
        "Start date",
        value=date(2026, 10, 20),
        key="point_start_date",
    )
    end_date = end_column.date_input(
        "End date",
        value=LATEST_MAP_DATE,
        key="point_end_date",
    )
    selected_variable = variable_column.selectbox(
        "Point variable",
        MARINE_VARIABLES,
        index=1,
        format_func=lambda variable: VARIABLE_LABELS[variable],
        key="selected_point_variable",
    )
    retrieve_column.write("")
    retrieve_data = retrieve_column.button(
        "Retrieve data",
        type="primary",
        width="stretch",
    )

    if retrieve_data:
        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        try:
            with st.spinner("Retrieving point data…"):
                dataframe, response_data = get_marine_data(
                    latitude,
                    longitude,
                    start_date,
                    end_date,
                    selected_variable,
                )
            st.session_state["point_result"] = {
                "dataframe": dataframe,
                "response_data": response_data,
                "variable": selected_variable,
                "start_date": start_date,
                "end_date": end_date,
                "latitude": latitude,
                "longitude": longitude,
            }
        except requests.exceptions.HTTPError as error:
            st.error(f"API request failed: {error}")
            if error.response is not None:
                st.code(error.response.text)
        except requests.exceptions.RequestException as error:
            st.error(f"Network error: {error}")
        except (KeyError, ValueError) as error:
            st.error(f"Unexpected API response: {error}")

    point_result = st.session_state.get("point_result")
    if point_result:
        render_point_result(point_result)
    else:
        st.info("Choose the query settings and press **Retrieve data**.")


def render_geolocation_view():
    """Render official LA28 area choices from the local geodata JSON."""
    st.header("Geolocation")
    st.caption(
        "Choose an LA28 sailing area, then apply its coordinates to the map "
        "and point chart."
    )

    try:
        datasets = load_geolocation_data()
        bathymetry = datasets["bathymetry"]
        terrain = datasets["terrain"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        st.error(f"Could not load the LA28 geolocation data: {error}")
        return

    areas = {area["key"]: area for area in bathymetry["areas"]}
    selection_column, apply_column = st.columns([3, 1])
    selected_key = selection_column.selectbox(
        "Sailing area",
        list(areas),
        format_func=lambda key: key.replace("_", " ").title(),
        key="selected_geolocation",
    )
    selected_area = areas[selected_key]
    apply_column.write("")
    apply_column.button(
        "Use this location",
        type="primary",
        width="stretch",
        on_click=select_geolocation,
        args=(selected_area,),
    )

    latitude_metric, longitude_metric, radius_metric, depth_metric = st.columns(4)
    latitude_metric.metric("Latitude", f"{selected_area['lat']:.5f}")
    longitude_metric.metric("Longitude", f"{selected_area['lon']:.5f}")
    radius_metric.metric("Area radius", f"{selected_area['radius_km']:.1f} km")
    depth = bathymetry["stats"]["value_at_area_centers"].get(selected_key)
    depth_metric.metric(
        "Centre bathymetry",
        f"{depth:.1f} {bathymetry['units']}" if depth is not None else "N/A",
        help="Negative values are below the dataset's vertical datum.",
    )

    st.subheader("Olympic sailing events")
    st.write(" · ".join(selected_area["events"]))

    st.subheader("Local geodata")
    bathymetry_column, terrain_column = st.columns(2)
    with bathymetry_column.container(border=True):
        st.markdown("**Bathymetry**")
        st.write(bathymetry["resolution"])
        st.caption(
            f"{bathymetry['provider']} · {bathymetry['vertical_datum']} · "
            f"{bathymetry['data_date']}"
        )
    with terrain_column.container(border=True):
        terrain_value = terrain["stats"]["value_at_area_centers"].get(selected_key)
        st.markdown("**Terrain**")
        st.write(
            f"Centre value: {terrain_value:.1f} {terrain['units']}"
            if terrain_value is not None
            else "Centre value: N/A"
        )
        st.caption(
            f"{terrain['provider']} · {terrain['vertical_datum']} · "
            f"{terrain['data_date']}"
        )

    st.caption(f"Local source folder: {GEO_DATA_DIRECTORY}")


def main():
    st.set_page_config(
        page_title="LA28 Location Agent",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.title("LA28 Olympic Sailing — Location Agent")
    st.write(
        "Top row: the coach's race-prep flow. Second row: raw marine data, "
        "point chart and LA28 geolocation."
    )

    agent_views.init_state()
    latitude, longitude = render_header()
    active_view = st.session_state["active_view"]
    if active_view == "coach":
        agent_views.render_coach_file()
    elif active_view == "venue":
        agent_views.render_venue_map(
            lambda: render_map_view(latitude, longitude, title=None)
        )
    elif active_view == "rules":
        agent_views.render_venue_rules(load_geolocation_data)
    elif active_view == "coach_brief":
        agent_views.render_coach_brief()
    elif active_view == "sailor_brief":
        agent_views.render_sailor_brief()
    elif active_view == "overview":
        agent_views.render_strategy_overview()
    elif active_view == "live":
        agent_views.render_live()
    elif active_view == "map":
        render_map_view(latitude, longitude)
    elif st.session_state["active_view"] == "point":
        render_point_view(latitude, longitude)
    else:
        render_geolocation_view()

    st.caption(
        "Data: Open-Meteo Marine API. Ocean currents are modelled, "
        "not station measurements."
    )


if __name__ == "__main__":
    main()
