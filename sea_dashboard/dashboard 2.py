import streamlit as st
import requests
import pandas as pd
from datetime import date

from current_map import render_current_map
from marine_api import (
    MAP_LAYERS,
    MARINE_VARIABLES,
    VARIABLE_LABELS,
    get_map_grid,
    get_marine_data,
)


# ---------------------------------------
# MAIN APPLICATION
# ---------------------------------------

def main():

    st.set_page_config(
        page_title="LA28 Marine Conditions",
        layout="wide"
    )

    st.title("LA28 Olympic Sailing — Marine Conditions")

    st.write(
        "Select a location to retrieve historical "
        "ocean-current and wave data."
    )

    # -----------------------------------
    # SIDEBAR SETTINGS
    # -----------------------------------

    st.sidebar.header("Location")

    latitude = st.sidebar.number_input(
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=33.72,
        format="%.5f"
    )

    longitude = st.sidebar.number_input(
        "Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=-118.27,
        format="%.5f"
    )

    st.sidebar.header("Date range")

    start_date = st.sidebar.date_input(
        "Start date",
        value=date(2026, 10, 20)
    )

    end_date = st.sidebar.date_input(
        "End date",
        value=date(2026, 11, 3)
    )

    st.sidebar.header("Map layer")

    map_layer = st.sidebar.selectbox(
        "Select map layer",
        list(MAP_LAYERS),
        help="Controls the animated regional map."
    )

    st.sidebar.header("Point chart")

    selected_variable = st.sidebar.selectbox(
        "Select point variable",
        MARINE_VARIABLES,
        index=1,
        format_func=lambda variable: VARIABLE_LABELS[variable]
    )

    retrieve_data = st.sidebar.button(
        "Retrieve marine data",
        type="primary",
        width="stretch"
    )

    st.sidebar.caption(
        "Data: Open-Meteo Marine API. Ocean currents are modelled, "
        "not station measurements."
    )

    # -----------------------------------
    # DYNAMIC REGIONAL MAP
    # -----------------------------------

    layer_configuration = MAP_LAYERS[map_layer]
    st.subheader(f"Regional map: {map_layer}")
    st.caption(
        f"{layer_configuration['description']} Use the map's play button or "
        f"hour slider to explore {end_date}."
    )

    map_signature = (latitude, longitude, str(end_date), map_layer)
    stored_map_signature = st.session_state.get("map_signature")
    should_load_map = retrieve_data or (
        st.session_state.get("map_grid") is not None
        and stored_map_signature != map_signature
    )

    if should_load_map:
        try:
            with st.spinner(f"Building the regional {map_layer.lower()} field…"):
                st.session_state["map_grid"] = get_map_grid(
                    latitude,
                    longitude,
                    end_date,
                    map_layer,
                )
                st.session_state["map_signature"] = map_signature
        except requests.exceptions.RequestException as e:
            st.error(f"Could not load the regional map layer: {e}")
        except (KeyError, ValueError) as e:
            st.error(f"Unexpected regional map response: {e}")

    map_grid = st.session_state.get("map_grid")
    if map_grid:
        render_current_map(map_grid)
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
    else:
        st.info(
            "Choose a map layer and press **Retrieve marine data** to build "
            "the regional visualization."
        )

    # -----------------------------------
    # GET DATA
    # -----------------------------------

    if retrieve_data:

        if start_date > end_date:
            st.error("Start date must be before end date.")
            return

        try:
            df, data = get_marine_data(
                latitude,
                longitude,
                start_date,
                end_date,
                selected_variable
            )

            # -----------------------------------
            # DISPLAY LOCATION INFORMATION
            # -----------------------------------

            st.subheader("Selected location")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Requested latitude",
                f"{latitude:.5f}"
            )

            col2.metric(
                "Requested longitude",
                f"{longitude:.5f}"
            )

            col3.metric(
                "Observations",
                len(df)
            )

            col4.metric(
                "Grid elevation",
                f"{data.get('elevation', 'N/A')} m"
                if data.get("elevation") is not None
                else "N/A"
            )

            # -----------------------------------
            # DISPLAY DATA
            # -----------------------------------

            st.subheader(
                f"Historical data: {VARIABLE_LABELS[selected_variable]}"
            )

            if selected_variable not in df.columns:
                st.warning(
                    "The selected variable was not returned."
                )
                return

            values = pd.to_numeric(
                df[selected_variable],
                errors="coerce"
            )

            unit = (
                data.get("hourly_units", {})
                .get(selected_variable, "")
            )

            summary1, summary2, summary3 = st.columns(3)
            summary1.metric(
                "Minimum",
                f"{values.min():.2f} {unit}".strip()
            )
            summary2.metric(
                "Average",
                f"{values.mean():.2f} {unit}".strip()
            )
            summary3.metric(
                "Maximum",
                f"{values.max():.2f} {unit}".strip()
            )

            display_df = df[["time", selected_variable]].rename(
                columns={selected_variable: VARIABLE_LABELS[selected_variable]}
            )

            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True
            )

            # -----------------------------------
            # CHART
            # -----------------------------------

            st.subheader("Time series")

            chart_df = df.set_index("time")

            st.line_chart(
                chart_df[selected_variable],
                y_label=(
                    f"{VARIABLE_LABELS[selected_variable]} ({unit})"
                    if unit
                    else VARIABLE_LABELS[selected_variable]
                )
            )

            # -----------------------------------
            # CSV DOWNLOAD
            # -----------------------------------

            csv = df.to_csv(index=False)

            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=(
                    f"{selected_variable}_"
                    f"{start_date}_{end_date}.csv"
                ),
                mime="text/csv"
            )

            # -----------------------------------
            # API GRID CELL
            # -----------------------------------

            st.caption(
                "Model grid-cell coordinates: "
                f"{data.get('latitude')}, "
                f"{data.get('longitude')}"
            )

            if selected_variable == "ocean_current_direction":
                direction_note = (
                    " Current direction shows where water flows toward: "
                    "0° north, 90° east, 180° south, and 270° west."
                )
            elif selected_variable.endswith("_direction"):
                direction_note = (
                    " Wave and swell directions describe where waves come "
                    "from."
                )
            else:
                direction_note = ""

            st.caption(
                f"Source: Open-Meteo Marine API.{direction_note}"
            )

        except requests.exceptions.HTTPError as e:
            st.error(f"API request failed: {e}")

            if e.response is not None:
                st.code(e.response.text)

        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")

        except (KeyError, ValueError) as e:
            st.error(f"Unexpected API response: {e}")

    else:
        st.info(
            "Choose the query settings and press **Retrieve marine data** "
            "in the sidebar."
        )


if __name__ == "__main__":
    main()
