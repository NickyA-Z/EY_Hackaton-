"""Streamlit entry point for the LA28 marine dashboard."""

from datetime import date
import json

import pandas as pd
import requests
import streamlit as st

from backend.retrieval.geolocation import (
    GEO_DATA_DIRECTORY,
    load_geolocation_data,
)
from backend.retrieval.marine_api import (
    POINT_VARIABLES,
    VARIABLE_LABELS,
    get_marine_data,
)
from frontend.frontend import agent_views
from frontend.frontend.current_map import combine_layers, render_current_map
from frontend.frontend.styles import apply_global_styles

RESULT_VIEW_HEIGHT = 500
EARLIEST_MAP_DATE = date(1940, 1, 1)
LATEST_MAP_DATE = date(2026, 11, 3)


def select_view(view):
    """Open one of the dashboard's main views."""
    st.session_state["active_view"] = view


def select_geolocation(area):
    """Apply a JSON-defined LA28 area to the shared coordinates."""
    st.session_state["selected_latitude"] = float(area["lat"])
    st.session_state["selected_longitude"] = float(area["lon"])


def render_header():
    """Render grouped navigation and compact shared location controls."""
    active_view = st.session_state.setdefault("active_view", "live")
    st.session_state.setdefault("selected_latitude", 33.72)
    st.session_state.setdefault("selected_longitude", -118.27)

    with st.container(border=True, key="dashboard_header"):
        (
            live_navigation, venue_navigation, briefs_navigation, strategy_navigation,
            _, coach_navigation, location_column,
        ) = st.columns([1, 1, 1, 1, 1.6, 0.32, 0.32], vertical_alignment="center")

        venue_label = {
            "venue": "Venue · Geoinformation",
            "rules": "Venue · Rules",
        }.get(active_view, "Venue")
        with venue_navigation.popover(venue_label, width="stretch"):
            st.caption("VENUE")
            st.button(
                "Geoinformation",
                key="show_venue_view",
                type="primary" if active_view == "venue" else "secondary",
                width="stretch",
                on_click=select_view,
                args=("venue",),
            )
            st.button(
                "Rules",
                key="show_rules_view",
                type="primary" if active_view == "rules" else "secondary",
                width="stretch",
                on_click=select_view,
                args=("rules",),
            )

        briefs_label = {
            "coach_brief": "Briefs · Coach",
            "sailor_brief": "Briefs · Sailor",
        }.get(active_view, "Briefs")
        with briefs_navigation.popover(briefs_label, width="stretch"):
            st.caption("BRIEFS")
            st.button(
                "Coach",
                key="show_coach_brief_view",
                type="primary" if active_view == "coach_brief" else "secondary",
                width="stretch",
                on_click=select_view,
                args=("coach_brief",),
            )
            st.button(
                "Sailor",
                key="show_sailor_brief_view",
                type="primary" if active_view == "sailor_brief" else "secondary",
                width="stretch",
                on_click=select_view,
                args=("sailor_brief",),
            )

        strategy_navigation.button(
            "Strategy",
            key="show_overview_view",
            type="primary" if active_view == "overview" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("overview",),
        )
        live_navigation.button(
            "● Live",
            key="show_live_view",
            type="primary" if active_view == "live" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("live",),
        )

        coach_navigation.button(
            "",
            icon=":material/upload_file:",
            key="show_coach_view",
            type="primary" if active_view == "coach" else "secondary",
            width="stretch",
            help="Coach file: upload, preview and delete files",
            on_click=select_view,
            args=("coach",),
        )

        latitude = st.session_state["selected_latitude"]
        longitude = st.session_state["selected_longitude"]
        with location_column.popover(
            "",
            icon=":material/location_on:",
            help=f"Venue, event and location · {latitude:.3f}, {longitude:.3f}",
            width="stretch",
        ):
            st.caption("VENUE & EVENT")
            agent_views.render_event_settings()
            st.caption("SHARED LOCATION")
            st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                format="%.5f",
                key="selected_latitude",
            )
            st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                format="%.5f",
                key="selected_longitude",
            )
            st.caption("Picking a venue sets these coordinates. Used by the regional map and point analysis.")

    return (
        st.session_state["selected_latitude"],
        st.session_state["selected_longitude"],
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


def request_geo_load(area):
    """Load-button callback: apply the sailing area's coordinates, then load on this run."""
    select_geolocation(area)
    st.session_state["geo_load_requested"] = True


def load_geo_data(area):
    """Fetch the regional map and the point series for one area; keep earlier results on error."""
    latitude, longitude = float(area["lat"]), float(area["lon"])
    map_date = st.session_state["selected_map_date"]
    start_date = st.session_state["point_start_date"]
    map_layers = st.session_state["selected_map_layers"]
    variable = st.session_state["selected_point_variable"]
    if start_date > map_date:
        st.error("Points start date must be on or before the map date.")
        return
    with st.spinner("Loading location, map and points…"):
        st.session_state["map_grids"] = agent_views.load_layer_grids(
            map_layers, latitude, longitude, map_date
        )
        try:
            dataframe, response_data = get_marine_data(
                latitude, longitude, start_date, map_date, variable
            )
            st.session_state["point_result"] = {
                "dataframe": dataframe,
                "response_data": response_data,
                "variable": variable,
                "start_date": start_date,
                "end_date": map_date,
                "latitude": latitude,
                "longitude": longitude,
            }
        except requests.exceptions.HTTPError as error:
            st.error(f"Point data request failed: {error}")
            if error.response is not None:
                st.code(error.response.text)
        except requests.exceptions.RequestException as error:
            st.error(f"Network error: {error}")
        except (KeyError, ValueError) as error:
            st.error(f"Unexpected point data response: {error}")
    st.session_state["geo_loaded"] = {
        "area": area["key"], "layers": map_layers, "map_date": map_date, "start_date": start_date,
    }


def render_location_facts(area, bathymetry, terrain):
    """Local geodata for one LA28 sailing area."""
    key = area["key"]
    latitude_metric, longitude_metric, radius_metric, depth_metric = st.columns(4)
    latitude_metric.metric("Latitude", f"{area['lat']:.5f}")
    longitude_metric.metric("Longitude", f"{area['lon']:.5f}")
    radius_metric.metric("Area radius", f"{area['radius_km']:.1f} km")
    depth = bathymetry["stats"]["value_at_area_centers"].get(key)
    depth_metric.metric(
        "Centre bathymetry",
        f"{depth:.1f} {bathymetry['units']}" if depth is not None else "N/A",
        help="Negative values are below the dataset's vertical datum.",
    )
    st.markdown("**Olympic sailing events:** " + " · ".join(area["events"]))
    bathymetry_column, terrain_column = st.columns(2)
    with bathymetry_column.container(border=True):
        st.markdown("**Bathymetry**")
        st.write(bathymetry["resolution"])
        st.caption(
            f"{bathymetry['provider']} · {bathymetry['vertical_datum']} · "
            f"{bathymetry['data_date']}"
        )
    with terrain_column.container(border=True):
        terrain_value = terrain["stats"]["value_at_area_centers"].get(key)
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


def render_geo_data():
    """One control bar and one Load button for location, regional map and point series."""
    try:
        datasets = load_geolocation_data()
        bathymetry, terrain = datasets["bathymetry"], datasets["terrain"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        st.error(f"Could not load the LA28 geolocation data: {error}")
        return
    areas = {area["key"]: area for area in bathymetry["areas"]}

    defaults = {
        "selected_geolocation": next(iter(areas)),
        "selected_point_variable": "wave_height",
        "selected_map_date": LATEST_MAP_DATE,
        "point_start_date": date(2026, 10, 20),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    if st.session_state["selected_geolocation"] not in areas:
        st.session_state["selected_geolocation"] = defaults["selected_geolocation"]
    if st.session_state["selected_point_variable"] not in POINT_VARIABLES:
        st.session_state["selected_point_variable"] = defaults["selected_point_variable"]

    area_column, variable_column, start_column, date_column, load_column = st.columns(
        [1.4, 1.3, 1, 1, 0.9], vertical_alignment="bottom"
    )
    area_key = area_column.selectbox(
        "Sailing area",
        list(areas),
        format_func=lambda key: key.replace("_", " ").title(),
        key="selected_geolocation",
    )
    variable_column.selectbox(
        "Point variable",
        POINT_VARIABLES,
        format_func=lambda variable: VARIABLE_LABELS[variable],
        key="selected_point_variable",
    )
    start_column.date_input(
        "Points from", min_value=EARLIEST_MAP_DATE, max_value=LATEST_MAP_DATE,
        key="point_start_date",
    )
    date_column.date_input(
        "Map date (points to)", min_value=EARLIEST_MAP_DATE, max_value=LATEST_MAP_DATE,
        key="selected_map_date",
        help="Any date from January 1, 1940 through November 3, 2026.",
    )
    load_column.button(
        "Load", type="primary", width="stretch",
        on_click=request_geo_load, args=(areas[area_key],),
        help="Applies the area's coordinates and loads location, map and points together.",
    )

    selected_layers = agent_views.layer_picker("selected_map_layers")
    if not selected_layers:
        st.info("Select at least one marine layer to load the map.")

    if st.session_state.pop("geo_load_requested", False) and selected_layers:
        load_geo_data(areas[area_key])

    loaded = st.session_state.get("geo_loaded")
    if not loaded:
        st.info("Choose the area, layer, variable and dates, then press **Load**.")
        return
    area = areas.get(loaded["area"], areas[area_key])
    st.caption(
        f"Loaded: {area['key'].replace('_', ' ').title()} · {' + '.join(loaded['layers'])} · map "
        f"{loaded['map_date']} · points {loaded['start_date']} → {loaded['map_date']}"
    )

    st.markdown("#### 1 · Location")
    render_location_facts(area, bathymetry, terrain)

    st.markdown(f"#### 2 · Regional map: {' + '.join(loaded['layers'])}")
    map_grids = st.session_state.get("map_grids")
    if map_grids:
        render_current_map(combine_layers(map_grids), height=RESULT_VIEW_HEIGHT)
        st.caption(
            f"{agent_views.layer_caption([grid['title'] for grid in map_grids])} Particle motion is "
            "visually accelerated; use the play button or hour slider. Click the map for local details."
        )

    st.markdown("#### 3 · Points")
    point_result = st.session_state.get("point_result")
    if point_result:
        render_point_result(point_result)


def main():
    st.set_page_config(
        page_title="LA28 Location Agent",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    apply_global_styles()
    st.title("LA28 Olympic Sailing — Location Agent")
    st.caption("Race preparation, venue intelligence and live decision support.")

    agent_views.init_state()
    render_header()
    active_view = st.session_state["active_view"]
    if active_view == "coach":
        agent_views.render_coach_file()
    elif active_view == "venue":
        st.header("Geoinformation")
        agent_views.render_venue_map(render_geo_data)
    elif active_view == "rules":
        agent_views.render_venue_rules(load_geolocation_data)
    elif active_view == "coach_brief":
        agent_views.render_coach_brief()
    elif active_view == "sailor_brief":
        agent_views.render_sailor_brief()
    elif active_view == "overview":
        agent_views.render_strategy_overview()
    else:  # "live" (and any view name from before the merge into Geoinformation)
        agent_views.render_live()

    st.caption(
        "Data: Open-Meteo Marine API. Ocean currents are modelled, "
        "not station measurements."
    )


if __name__ == "__main__":
    main()
