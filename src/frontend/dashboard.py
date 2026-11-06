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
from backend import strategy
from backend.retrieval.marine_api import (
    POINT_VARIABLES,
    VARIABLE_LABELS,
    get_marine_data,
)
from frontend import agent_views, globe
from frontend.current_map import combine_layers, render_current_map
from frontend.previous_strategy_view import render_previous_strategy
from frontend.styles import apply_global_styles

RESULT_VIEW_HEIGHT = 500
APP_TITLE = "LA28 Olympic Sailing — Location Agent"
EARLIEST_MAP_DATE = date(1940, 1, 1)
LATEST_MAP_DATE = date(2026, 11, 3)


def select_view(view):
    """Open one of the dashboard's main views."""
    st.session_state["active_view"] = view


def select_geolocation(area):
    """Apply a JSON-defined LA28 area to the shared coordinates."""
    st.session_state["selected_latitude"] = float(area["lat"])
    st.session_state["selected_longitude"] = float(area["lon"])


def enter_venue():
    """Globe callback: the dive into a venue finished, open the dashboard there."""
    choice = st.session_state["prep_globe"].entered
    if not choice or choice["id"] not in strategy.VENUES:
        return
    if choice["id"] != st.session_state["venue"]:
        st.session_state["venue"] = choice["id"]
        agent_views.use_venue_coordinates()
    st.session_state["globe_entered"] = True
    st.session_state["active_view"] = "venue"


def pick_location():
    """Globe callback: a click on the globe sets the shared coordinates."""
    point = st.session_state["prep_globe"].picked
    if point:
        st.session_state["selected_latitude"] = float(point["lat"])
        st.session_state["selected_longitude"] = float(point["lon"])


def back_to_globe():
    st.session_state["globe_entered"] = False
    st.session_state["globe_returning"] = True


def render_location_settings():
    """Venue, event and shared coordinates (header location menu and globe page)."""
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


def render_globe_landing():
    """Preparation starts on the globe; entering a venue opens the dashboard."""
    intro, location_column = st.columns([6, 0.5], vertical_alignment="center")
    intro.caption("Pick a live or upcoming event on the globe and dive into the venue. "
                  "Click the globe to set the shared location.")
    latitude = st.session_state["selected_latitude"]
    longitude = st.session_state["selected_longitude"]
    with location_column.popover(
        "", icon=":material/location_on:", width="stretch",
        help=f"Venue, event and location · {latitude:.3f}, {longitude:.3f}",
    ):
        render_location_settings()
    globe.render_globe(
        {
            "venue": st.session_state["venue"],
            "name": st.session_state["venue"].split(" (")[0],
            "boat_class": st.session_state["boat_class"],
            "race_day": f"{st.session_state['race_day']:%d %b %Y}",
            "time_of_day": st.session_state["time_of_day"],
            "lat": latitude,
            "lon": longitude,
        },
        returning=st.session_state.pop("globe_returning", False),
        key="prep_globe",
        on_entered=enter_venue,
        on_picked=pick_location,
    )


def render_header():
    """Render grouped navigation and compact shared location controls."""
    active_view = st.session_state.setdefault("active_view", "venue")
    if active_view == "live":
        active_view = st.session_state["active_view"] = "venue"

    with st.container(border=True, key="dashboard_header"):
        (
            venue_navigation, strategy_navigation, briefs_navigation,
            speed_navigation, previous_navigation, globe_navigation, coach_navigation, location_column,
        ) = st.columns([1, 1, 1, 1.2, 1.3, 0.32, 0.32, 0.32], vertical_alignment="center")

        globe_navigation.button(
            "",
            icon=":material/public:",
            key="show_globe",
            width="stretch",
            help="Back to the event globe",
            on_click=back_to_globe,
        )

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
        speed_navigation.button(
            "Speed forecast",
            key="show_speed_view",
            type="primary" if active_view == "speed" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("speed",),
        )
        previous_navigation.button(
            "Previous strategy",
            key="show_previous_view",
            type="primary" if active_view == "previous" else "secondary",
            width="stretch",
            on_click=select_view,
            args=("previous",),
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
            render_location_settings()

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
        map_grids = agent_views.load_layer_grids(
            map_layers, latitude, longitude, map_date
        )
        if map_grids:
            st.session_state["map_grids"] = map_grids
        elif st.session_state.get("marine_rate_limited"):
            return
        if st.session_state.get("marine_rate_limited"):
            st.info("Point data was not requested because the Open-Meteo daily limit has been reached.")
        else:
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
                if getattr(error.response, "status_code", None) == 429:
                    st.session_state["marine_rate_limited"] = True
                    st.warning("Open-Meteo's daily API limit has been reached. Previously loaded point data remains available.")
                else:
                    st.error(f"Point data request failed: {error}")
            except requests.exceptions.RequestException as error:
                st.error(f"Network error: {error}")
            except (KeyError, ValueError) as error:
                st.error(f"Unexpected point data response: {error}")
    st.session_state["geo_loaded"] = {
        "area": area["key"], "layers": [grid["title"] for grid in map_grids],
        "map_date": map_date, "start_date": start_date,
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
    _, mode_column = st.columns([4, 1.3], vertical_alignment="bottom")
    # Showcase switch: Preparation = every planning view; Live = the live race view only.
    if st.session_state.get("showcase_mode", "") is None:  # re-clicking the active option clears it
        st.session_state["showcase_mode"] = st.session_state.get("_showcase_mode", "Preparation")
    st.session_state.setdefault("showcase_mode", "Preparation")
    mode = mode_column.segmented_control(
        "Showcase", ["Preparation", "● Live"],
        key="showcase_mode", label_visibility="collapsed", width="stretch",
    )
    st.session_state["_showcase_mode"] = mode
    agent_views.init_state()
    # The location inputs live in the Preparation header; Streamlit drops widget keys on runs where
    # the widget is not drawn (Live), so keep a shadow copy and restore from it.
    for key, default in (("selected_latitude", 33.72), ("selected_longitude", -118.27)):
        st.session_state[key] = st.session_state.get(key, st.session_state.get(f"_{key}", default))
        st.session_state[f"_{key}"] = st.session_state[key]
    if mode == "● Live":
        if not st.session_state.get("globe_entered"):
            st.info("Choose a venue in Preparation before loading live marine data.")
            return
        agent_views.render_live(showcase=APP_TITLE)
        st.caption("Data: Open-Meteo Marine API. Ocean currents are modelled, not station measurements.")
        return
    st.session_state.setdefault("selected_latitude", 33.72)
    st.session_state.setdefault("selected_longitude", -118.27)
    if not st.session_state.get("globe_entered"):
        render_globe_landing()
        return
    st.markdown(agent_views.prep_band(APP_TITLE), unsafe_allow_html=True)
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
    elif active_view == "speed":
        agent_views.render_speed_forecast()
    elif active_view == "previous":
        render_previous_strategy()
    else:
        st.session_state["active_view"] = "venue"
        st.header("Geoinformation")
        agent_views.render_venue_map(render_geo_data)

    st.caption(
        "Data: Open-Meteo Marine API. Ocean currents are modelled, "
        "not station measurements."
    )


if __name__ == "__main__":
    main()
