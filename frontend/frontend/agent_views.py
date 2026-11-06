"""Location Agent views: Coach file, Venue map, Venue rules, Coach brief,
Sailor brief, Strategy overview and Live."""

import datetime as dt
import html
import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import requests  # noqa: E402

from backend import analysis, boat_speed, race_analysis, strategy  # noqa: E402
from backend.analysis import tagging  # noqa: E402
from backend.compute.map_grid import MAP_LAYERS, get_map_grid, local_bounds  # noqa: E402
from frontend.frontend.current_map import combine_layers, render_current_map  # noqa: E402

TEAL, INK, ORANGE = "#087f82", "#071c2c", "#c8642c"

AGENT_VIEWS = {
    "coach": "Coach file",
    "venue": "Geoinformation",
    "rules": "Venue rules",
    "coach_brief": "Coach brief",
    "sailor_brief": "Sailor brief",
    "overview": "Strategy overview",
    "speed": "Speed forecast",
    "live": "Live",
}

CSS = f"""
<style>
.la-card {{ background:#fff; border:1px solid #d9e4e1; border-radius:12px; padding:14px 16px; margin-bottom:10px; }}
.la-dark {{ background:{INK}; color:#fff; border-radius:12px; padding:14px 16px; margin-bottom:10px; }}
.la-dark .big {{ font-size:2.1rem; font-weight:800; line-height:1.1; margin:4px 0 8px; }}
.la-small {{ font-size:.82rem; color:#55666e; }}
.la-dark .la-small {{ color:#b9cdd0; }}
.la-stat {{ background:#e7f0ee; border-radius:10px; padding:10px 14px; }}
.la-stat .v {{ font-size:1.3rem; font-weight:800; color:{INK}; }}
.la-row {{ display:flex; justify-content:space-between; align-items:center; border:1px solid #d9e4e1;
  border-radius:8px; padding:8px 12px; margin:6px 0; background:#fff; gap:10px; }}
.la-badge {{ background:{INK}; color:#fff; font:700 11px ui-monospace,monospace; padding:3px 6px;
  border-radius:4px; margin-right:10px; }}
.la-ok, .la-warn, .la-bad {{ font-weight:600; font-size:.78rem; padding:3px 8px; border-radius:5px; white-space:nowrap; }}
.la-ok {{ background:#dff1e4; color:#2b7139; }}
.la-warn {{ background:#fcebdc; color:#9a4b18; }}
.la-bad {{ background:#f9dfdf; color:#9d1f1f; }}
.la-q {{ display:flex; gap:14px; padding:11px 0; border-bottom:1px solid #e3ebe9; }}
.la-q .n {{ background:{TEAL}; color:#fff; border-radius:50%; min-width:30px; height:30px; display:flex;
  align-items:center; justify-content:center; font-weight:700; }}
.la-q .t {{ font-size:.8rem; color:#55666e; font-weight:600; }}
.la-sailor {{ font-size:1.35rem; font-weight:700; color:{INK}; padding:14px 0; border-bottom:1px solid #e3ebe9; }}
.la-why td {{ padding:6px 8px 6px 0; vertical-align:top; font-size:.9rem; }}
.la-why td:first-child {{ color:{TEAL}; font-weight:700; white-space:nowrap; }}
.la-mini {{ width:100%; border-collapse:collapse; font-size:.74rem; }}
.la-mini th {{ text-align:left; color:#55666e; font-weight:600; padding:4px 8px; border-bottom:1px solid #d9e4e1; }}
.la-mini td {{ padding:4px 8px; border-bottom:1px solid #eef2f1; vertical-align:top; }}
.la-flow {{ display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 14px; }}
.la-flow div {{ background:#fff7c9; border:1px solid #eadf8f; border-radius:6px; padding:8px 10px; font-size:.85rem; }}
.la-flow div.done {{ background:#dff1e4; border-color:#b5dcbf; }}
</style>
"""


# ---------- state ----------

DEFAULTS = {
    "venue": list(strategy.VENUES)[0], "race_day": dt.date(2026, 6, 15), "time_of_day": "Midday",
    "wind_sector": "SSW", "map_hour": 13,
    "wi_sector": "SSW", "wi_strength": "Medium", "wi_breeze": "On time", "risk_appetite": "Balanced",
}


def init_state():
    """Defaults + keep agent choices alive while their widgets are on another view."""
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    classes = strategy.VENUES[st.session_state.venue]["classes"]
    if st.session_state.get("boat_class") not in classes:
        st.session_state.boat_class = classes[0]
    for key in [*DEFAULTS, "boat_class"]:
        st.session_state[key] = st.session_state[key]
    # segmented controls return None when the active option is clicked again
    for key in ("wind_sector", "map_hour", "time_of_day", "wi_sector", "wi_strength", "wi_breeze",
                "risk_appetite"):
        if st.session_state[key] is None:
            st.session_state[key] = st.session_state.get(f"_prev_{key}", DEFAULTS[key])
        st.session_state[f"_prev_{key}"] = st.session_state[key]
    if st.session_state.get("_last_tod") != st.session_state.time_of_day:
        st.session_state.map_hour = strategy.TIME_OF_DAY[st.session_state.time_of_day]
        st.session_state._last_tod = st.session_state.time_of_day
    st.session_state.setdefault("uploaded", {})
    st.session_state.setdefault("pasted", [])
    st.session_state.setdefault("hidden_demo", set())
    st.markdown(CSS, unsafe_allow_html=True)


def go(view):
    st.session_state["active_view"] = view


def use_venue_coordinates():
    spot = strategy.VENUES[st.session_state.venue]
    st.session_state["selected_latitude"] = spot["lat"]
    st.session_state["selected_longitude"] = spot["lon"]


def esc(text):
    return html.escape(str(text))


# ---------- cached data ----------

@st.cache_data(show_spinner=False)
def history():
    return strategy.load_wind(strategy.HISTORY_YEARS)


@st.cache_data(show_spinner=False)
def live_data():
    return strategy.load_wind([strategy.LIVE_YEAR])


def season():
    """Months covered by the history, e.g. "June–July" (from the data, not hard-coded)."""
    return strategy.season_label(history())


@st.cache_data(show_spinner=False)
def tides():
    return strategy.load_tides()


@st.cache_data(show_spinner=False)
def demo_documents():
    return analysis.demo_documents()


@st.cache_data(show_spinner="Reading file…")
def analyse_upload(name, data):
    return analysis.analyse(name, data)


@st.cache_data(show_spinner=False)
def race_summary():
    return race_analysis.summary()


def document_entries():
    """Return uploaded files, visible demos, and pasted transcripts with their kinds."""
    uploaded = [("uploaded", doc) for doc in st.session_state.uploaded.values()]
    demo = [] if uploaded else [
        ("demo", doc) for doc in demo_documents()
        if doc["name"] not in st.session_state.hidden_demo
    ]
    return uploaded + demo + [("pasted", doc) for doc in st.session_state.pasted]


@st.cache_data(show_spinner="Preparing ILCA 7 telemetry…")
def speed_dataset(horizon_seconds=30):
    return boat_speed.build_dataset(horizon_seconds)


@st.cache_resource(show_spinner="Training ILCA 7 speed model…")
def speed_model(horizon_seconds, excluded_boat):
    return boat_speed.train_model(speed_dataset(horizon_seconds), excluded_boat)


SPEED_COLOURS = (
    (2, [49, 54, 149], "0–2 kt"),
    (4, [41, 120, 185], "2–4 kt"),
    (6, [46, 179, 126], "4–6 kt"),
    (8, [253, 174, 97], "6–8 kt"),
    (float("inf"), [215, 48, 39], "8+ kt"),
)

SPEED_LEADER_LABELS = {
    "Elliot Hanson": "1 · Elliot Hanson (GBR 215613)",
    "Lorenzo Brando Chiavarini": "2 · Lorenzo Brando Chiavarini (ITA 216159)",
    "Duko Bos": "3 · Duko Bos (NED 206717)",
}
SPEED_SELECTOR_EXCLUSIONS = {"2796_15347_USA_211414"}


def speed_colour(speed_kt):
    return next(colour for upper, colour, _ in SPEED_COLOURS if speed_kt < upper)


def speed_map_payload(location_name, location_info, **options):
    """Build the minimal field envelope required by the shared Live map."""
    bounds = local_bounds(
        location_info["lat"], location_info["lon"], location_info["radius_m"]
    )
    return {
        "title": options.pop("title", "Sailing area"),
        "mode": "scalar",
        "legend_label": "",
        "unit": "",
        "bounds": bounds,
        "latitudes": [bounds["south"], bounds["north"]],
        "longitudes": [bounds["west"], bounds["east"]],
        "rows": 2,
        "columns": 2,
        "frames": [{"time": "", "u": [None] * 4, "v": [None] * 4,
                    "value": [None] * 4}],
        "minimum_value": 0,
        "maximum_value": 0,
        "location_marker": {
            "name": location_name,
            "lat": location_info["lat"],
            "lng": location_info["lon"],
            "radius_m": location_info["radius_m"],
        },
        **options,
    }


def speed_track_points(rows, model, horizon):
    """Build the speed-coloured GPS points shared by playback and overlays."""
    predictions = model.predict(rows)
    points = []
    for (_, row), predicted_speed in zip(rows.iterrows(), predictions):
        predicted_lat, predicted_lng = boat_speed.project_position(
            float(row["lat"]), float(row["lng"]), float(row["heading_deg"]),
            float(predicted_speed), horizon,
        )
        points.append({
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "time_epoch": float(row["time_epoch"]),
            "speed_kt": float(row["speed_kt"]),
            "predicted_speed_kt": float(predicted_speed),
            "prediction_low_kt": max(
                0.0, float(predicted_speed + model.residual_low_kt)
            ),
            "prediction_high_kt": min(
                boat_speed.MAX_PLAUSIBLE_SPEED_KT,
                float(predicted_speed + model.residual_high_kt),
            ),
            "actual_future_speed_kt": (
                float(row["target_speed_kt"])
                if pd.notna(row["target_speed_kt"])
                else None
            ),
            "predicted_lat": predicted_lat,
            "predicted_lng": predicted_lng,
            "colour": speed_colour(float(row["speed_kt"])),
        })
    return points


def speed_replay_map(rows, index, model, horizon, location_name, location_info):
    """Build GPS playback data for the same renderer used by the Live map."""
    points = speed_track_points(rows, model, horizon)
    render_current_map(
        speed_map_payload(
            location_name,
            location_info,
            title="GPS speed route",
            gps_track=points,
            start_frame=index,
            autoplay=False,
        ),
        height=560,
    )


def documents():
    return [doc for _, doc in document_entries()]


def unique_name(name):
    taken = {doc["name"] for doc in documents()}
    candidate, number = name, 2
    while candidate in taken:
        candidate, number = f"{name} ({number})", number + 1
    return candidate


def delete_document(kind, name):
    if kind == "uploaded":
        st.session_state.uploaded.pop(name, None)
    elif kind == "pasted":
        st.session_state.pasted = [doc for doc in st.session_state.pasted if doc["name"] != name]
    else:
        st.session_state.hidden_demo.add(name)


def current_insight():
    hour = st.session_state.map_hour
    insight = strategy.venue_insight(history(), st.session_state.wind_sector, hour)
    when = dt.datetime.combine(st.session_state.race_day, dt.time(hour))
    return insight, strategy.tide_state(tides(), when)


def current_brief():
    insight, tide = current_insight()
    if insight["n_days"] == 0:
        return insight, tide, None
    brief = strategy.briefing(insight, tide, st.session_state.boat_class)
    st.session_state.plan = {"sector": insight["sector"], "low": insight["speed_low"],
                             "high": insight["speed_high"], "side": insight["side"]}
    return insight, tide, brief


def context_line():
    return (f"{st.session_state.venue.split(' (')[0]} · {st.session_state.race_day:%d %b %Y} · "
            f"{st.session_state.boat_class}")


LAYER_DOTS = {"Ocean currents": "🔵", "Waves": "🟠", "Wind waves": "🟣", "Swell": "🟢", "Wind": "⚪"}


def layer_picker(key):
    """Multi-select: every chosen marine layer is overlaid on the map in its own colour."""
    st.session_state.setdefault(key, ["Ocean currents"])
    st.session_state[key] = [name for name in st.session_state[key] if name in MAP_LAYERS]
    return st.pills(
        "Marine layers", list(MAP_LAYERS), selection_mode="multi", key=key,
        format_func=lambda name: f"{LAYER_DOTS.get(name, '●')} {name}",
        help="Click several layers to overlay them. Each keeps its own colour; brightness shows magnitude.",
    )


def describe_error(error):
    """Short text for a failed API call (the raw error repeats a very long request URL)."""
    response = getattr(error, "response", None)
    if response is None:
        return type(error).__name__
    try:
        reason = response.json().get("reason")
    except ValueError:
        reason = None
    return f"HTTP {response.status_code}: {reason or response.reason}"


def load_layer_grids(names, latitude, longitude, day):
    """Grids for the chosen layers (cached per layer); a layer that fails is reported and skipped."""
    if abs(latitude) > 85 or abs(longitude) > 180:
        st.error(f"The shared location ({latitude:.3f}°, {longitude:.3f}°) is outside the map's range. "
                 "Reset it in the 📍 menu, or pick a venue in Coach file.")
        return []
    grids = []
    with st.spinner(f"Building {', '.join(name.lower() for name in names)}…"):
        for name in names:
            try:
                grids.append(get_map_grid(latitude, longitude, day, name))
            except requests.exceptions.RequestException as error:
                st.error(f"Could not load {name}: {describe_error(error)}")
            except (KeyError, ValueError) as error:
                st.error(f"Unexpected {name} response: {error}")
    return grids


def layer_caption(names):
    if len(names) == 1:
        return MAP_LAYERS[names[0]]["description"]
    return "Overlay: " + " · ".join(f"{LAYER_DOTS.get(name, '●')} {name}" for name in names)


def render_layer_map(key, hour, height=420):
    """The Map-layer visualisation (same get_map_grid + render_current_map), opened on the race day at `hour`."""
    names = layer_picker(f"{key}_layers")
    if not names:
        st.info("Select at least one marine layer.")
        return
    grids = load_layer_grids(names, st.session_state["selected_latitude"],
                             st.session_state["selected_longitude"], st.session_state.race_day)
    if not grids:
        return
    stamp = f"T{hour:02d}:00"
    start = next((i for i, frame in enumerate(grids[0]["frames"]) if frame["time"].endswith(stamp)), None)
    render_current_map(combine_layers(grids, start_frame=start, autoplay=False), height=height)
    st.caption(f"{layer_caption([grid['title'] for grid in grids])} Opened at {hour:02d}:00 on "
               f"{st.session_state.race_day:%d %b}; use the slider for other hours.")


def render_speed_area_map(
    location_name, location_info, layer, key, gps_overlay=None, gps_index=None
):
    """Render a location-only or modelled marine layer for a sailing area."""
    location_payload = {
        "name": location_name,
        "lat": location_info["lat"],
        "lng": location_info["lon"],
        "radius_m": location_info["radius_m"],
    }
    if layer == "Location only":
        render_current_map(
            speed_map_payload(
                location_name,
                location_info,
                title=location_name,
                location_only=True,
                autoplay=False,
                gps_overlay=gps_overlay or [],
                gps_overlay_index=gps_index,
            ),
            height=560,
        )
        return

    try:
        with st.spinner(f"Building the regional {layer.lower()} field…"):
            grid = get_map_grid(
                location_info["lat"],
                location_info["lon"],
                st.session_state.race_day,
                layer,
                bounds=local_bounds(
                    location_info["lat"],
                    location_info["lon"],
                    location_info["radius_m"],
                ),
            )
    except requests.exceptions.RequestException as error:
        st.error(f"Could not load the regional map layer: {error}")
        return
    except (KeyError, ValueError) as error:
        st.error(f"Unexpected regional map response: {error}")
        return

    hour = st.session_state.map_hour
    stamp = f"T{hour:02d}:00"
    start = next(
        (i for i, frame in enumerate(grid["frames"]) if frame["time"].endswith(stamp)),
        None,
    )
    render_current_map({
        **grid,
        "start_frame": start,
        "autoplay": False,
        "location_marker": location_payload,
        "gps_overlay": gps_overlay or [],
        "gps_overlay_index": gps_index,
    }, height=560)
    st.caption(
        f"{MAP_LAYERS[layer]['description']} Modelled Open-Meteo data for "
        f"{st.session_state.race_day:%d %b %Y}. The marine field is fixed at "
        f"{hour:02d}:00; the map timeline follows the selected GPS track."
    )


# ---------- 1. Coach file ----------

@st.dialog("Upload coach files", width="large")
def upload_dialog():
    files_tab, transcript_tab = st.tabs(["Drag & drop or browse", "Paste a transcript"])
    with files_tab:
        uploads = st.file_uploader(
            "Drag and drop files here, or click **Upload** to pick them from your computer",
            accept_multiple_files=True, type=analysis.UPLOAD_TYPES, key="dialog_uploads")
        st.caption("Sailing instructions · wind logs · GPS tracks · results · notes · "
                   "photos of whiteboards · transcripts")
        if st.button("Add files", type="primary", disabled=not uploads, width="stretch"):
            for upload in uploads:
                data = upload.getvalue()
                st.session_state.uploaded[upload.name] = {**analyse_upload(upload.name, data), "data": data}
            st.rerun()  # closes the dialog
    with transcript_tab:
        title = st.text_input("Title", value="Debrief transcript", key="paste_title")
        text = st.text_area("Transcript (plain text, VTT or SRT)", height=180, key="paste_text",
                            placeholder="Coach: How did the first beat go?\nSailor: Right paid after 12:00.")
        if st.button("Add transcript", type="primary", disabled=not text.strip(), width="stretch"):
            st.session_state.pasted.append(analysis.analyse_pasted_transcript(unique_name(title), text))
            st.rerun()


def render_event_settings():
    """Venue, class, race day and time of day (rendered inside the header's location menu)."""
    st.selectbox("Venue", list(strategy.VENUES), key="venue", on_change=use_venue_coordinates)
    spot = strategy.VENUES[st.session_state.venue]
    st.selectbox("Class", spot["classes"], key="boat_class")
    live_days = live_data()["date"]
    st.date_input("Race day", key="race_day", min_value=live_days.min(), max_value=live_days.max(),
                  help=f"Hackathon mode: {season()} {strategy.LIVE_YEAR} is replayed as if live.")
    st.segmented_control("Time of day", list(strategy.TIME_OF_DAY), key="time_of_day")


IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
RAW_PREVIEW_TYPES = {".csv", ".gpx", ".xml"}


@st.dialog("File preview", width="large")
def preview_dialog(kind, name):
    doc = next((d for k, d in document_entries() if k == kind and d["name"] == name), None)
    if doc is None:
        st.info("This file is no longer available.")
        return
    st.markdown(f"**{doc['name']}** · {doc['entity'] or 'Unknown type'} · {doc['method'] or doc['capability'] or ''}")
    data, suffix = doc.get("data"), Path(name).suffix.lower()
    if data and suffix in IMAGE_TYPES:
        st.image(data)
    if doc["text"]:
        st.text_area("Text the agent read", doc["text"], height=320, disabled=True, key=f"preview_text_{kind}_{name}")
    elif data and suffix in RAW_PREVIEW_TYPES:
        st.code(data.decode("utf-8", errors="replace")[:5000], language=None)
        st.caption("First 5,000 characters of the file.")
    elif not data and doc["capability"] == "structured":
        st.info("Demo placeholder: upload your own file to preview its content.")
    elif not (data and suffix in IMAGE_TYPES):
        st.info("No preview for this file type yet.")
    if doc["error"]:
        st.warning(doc["error"])
    for topic, lines in doc["tags"].items():
        st.markdown(f"**{topic}**: " + " · ".join(lines[:2]))


def render_coach_file():
    st.header("Coach file")
    st.caption("Upload your own files. Each one is mapped to the common venue model, read by the right "
               "capability (text, picture of text, transcript) and tagged by topic.")

    with st.container(border=True):
        title, upload_col = st.columns([4, 1], vertical_alignment="center")
        title.markdown("#### Files")
        if upload_col.button("Upload", icon=":material/upload:", type="primary", width="stretch"):
            upload_dialog()
        entries = document_entries()
        if not st.session_state.uploaded:
            st.caption("Showing the demo file set (sample texts marked DEMO SAMPLE). "
                       "Press **Upload** to add your own files.")
            if st.session_state.hidden_demo:
                st.button("Restore demo files", on_click=st.session_state.hidden_demo.clear)
        if not entries:
            st.info("No files yet.")
        for kind, doc in entries:
            info, preview_col, delete_col = st.columns([12, 0.7, 0.7], vertical_alignment="center")
            status = ('<span class="la-bad">Not read</span>' if doc["error"] else
                      '<span class="la-ok">Mapped</span>')
            info.markdown(
                f'<div class="la-row"><div><span class="la-badge">{esc(doc["badge"])}</span>{esc(doc["name"])}'
                f'</div><div class="la-small">→ {esc(doc["entity"] or "Unknown type")} · '
                f'{esc(doc["method"] or doc["capability"] or "")} &nbsp; {status}</div></div>',
                unsafe_allow_html=True)
            if preview_col.button("", icon=":material/visibility:", key=f"preview_{kind}_{doc['name']}",
                                  help="Preview", width="stretch"):
                preview_dialog(kind, doc["name"])
            delete_col.button("", icon=":material/delete:", key=f"delete_{kind}_{doc['name']}",
                              help="Delete", width="stretch", on_click=delete_document,
                              args=(kind, doc["name"]))
            if doc["error"]:
                st.caption(f"⚠️ {doc['error']}")

    with st.expander("What the coach can upload (demo guide)"):
        head = "".join(f"<th>{title}</th>" for title in ("", "Upload", "Formats", "Read by", "Used in"))
        body = "".join(
            f"<tr><td>{'✅' if row['provided'] else ('❗' if row['required'] else '○')}</td>"
            f"<td>{esc(row['item'])}</td><td>{esc(row['formats'])}</td><td>{esc(row['capability'])}</td>"
            f"<td>{esc(row['used_in'])}</td></tr>"
            for row in analysis.checklist(documents()))
        st.markdown(f'<table class="la-mini"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>',
                    unsafe_allow_html=True)
        st.caption("Everything is optional except the sailing instructions; without uploads the agent "
                   "works from public data only. Public data joined automatically: Open-Meteo wind & cloud "
                   f"({season()} 2021–2025) · NOAA tides · NCEI bathymetry & terrain · SailSync race tracks.")


# ---------- 2. Venue map ----------

def _arrow(x, y, toward_deg, length, color=INK, width=3):
    rad = math.radians(toward_deg)
    dx, dy = math.sin(rad) * length, -math.cos(rad) * length
    x0, y0, x1, y1 = x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2
    left = (x1 - 9 * math.sin(rad - 0.45), y1 + 9 * math.cos(rad - 0.45))
    right = (x1 - 9 * math.sin(rad + 0.45), y1 + 9 * math.cos(rad + 0.45))
    return (f'<line x1="{x0:.0f}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y1:.0f}" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round"/><polygon points="{x1:.0f},{y1:.0f} '
            f'{left[0]:.0f},{left[1]:.0f} {right[0]:.0f},{right[1]:.0f}" fill="{color}"/>')


def venue_svg(wind_from, speed, side, layers, tide_state, veer_rate=0.0):
    toward = (wind_from + 180) % 360
    length = 30 + min(speed, 25) * 3
    terrain = "Terrain effects" in layers
    parts = [
        '<svg viewBox="0 0 860 560" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Venue map, wind from {wind_from:.0f} degrees at {speed:.0f} knots" '
        'style="width:100%;border-radius:10px;font-family:system-ui,sans-serif">',
        '<rect width="860" height="560" fill="#d7e9ec"/>',
        '<path d="M0 0 H860 V140 C760 170 640 125 520 160 C400 195 250 150 0 190 Z" fill="#e7e3d8"/>',
    ]
    if terrain:
        parts.append('<path d="M0 0 H280 V80 L130 150 L0 165 Z" fill="#cfc4ad"/>')
    parts += [
        '<text x="50" y="70" font-size="17" fill="#4a4a4a">Hills (Palos Verdes)</text>',
        '<text x="560" y="70" font-size="17" fill="#4a4a4a">Port / city</text>',
        '<line x1="400" y1="185" x2="790" y2="185" stroke="#6b6b6b" stroke-width="7" stroke-linecap="round"/>',
        '<text x="550" y="212" font-size="15" fill="#4a4a4a">Breakwater</text>',
    ]
    if "Pressure" in layers:
        band_x = {"Right": 430, "Left": 70, "Middle": 250}[side]
        parts.append(f'<rect x="{band_x}" y="225" width="360" height="70" rx="12" fill="{TEAL}" opacity=".75"/>'
                     f'<text x="{band_x + 16}" y="252" font-size="15" font-weight="700" fill="#fff">'
                     f'Pressure band + {max(1, round(speed * 0.2))} kt</text>')
    if "Current" in layers:
        flow = 0 if tide_state == "Flood" else 180  # flood sets into the harbour (north)
        for x in (110, 330, 560, 780):
            parts.append(_arrow(x, 500, flow, 40, color="#1b8f8a", width=2))
        parts.append(f'<text x="20" y="545" font-size="13" fill="#1b6f6a">{tide_state} tide current</text>')
    parts += [
        '<rect x="200" y="310" width="480" height="210" fill="none" stroke="#1f1f1f" stroke-width="2" stroke-dasharray="8 6"/>',
        '<text x="210" y="510" font-size="14">Course area A</text>',
        f'<circle cx="280" cy="380" r="9" fill="{ORANGE}"/><text x="262" y="405" font-size="13">Mark 1</text>',
        f'<line x1="610" y1="360" x2="610" y2="480" stroke="{ORANGE}" stroke-width="3"/>'
        '<text x="575" y="500" font-size="13">Start line</text>',
        '<circle cx="790" cy="470" r="27" fill="#fff" stroke="#1f1f1f" stroke-width="1.5"/>'
        '<text x="783" y="462" font-size="13" font-weight="700">N</text>'
        '<line x1="790" y1="466" x2="790" y2="488" stroke="#1f1f1f" stroke-width="2"/>',
    ]
    if "Wind" in layers:
        for x, y in [(150, 410), (330, 360), (470, 360), (330, 460), (470, 460), (620, 330), (740, 400)]:
            near_breakwater = terrain and x > 560
            parts.append(_arrow(x, y, toward + (veer_rate * 2 if near_breakwater else 0),
                                length * (1.15 if near_breakwater else 1)))
    parts.append("</svg>")
    return "".join(parts)


def why_rows(insight, tide):
    rate = insight["veer_rate"]
    turn = f"{'veering right' if rate > 0 else 'backing left'} ~{abs(rate):.0f}° per hour"
    onset = f"{insight['onset_hour']}:00" if insight["onset_hour"] is not None else "—"
    turns = f" until about {tide['turns']:%H:%M}" if tide["turns"] is not None else ""
    history_text = (f"The wind kept turning {insight['side'].lower()} on {insight['kept_turning']} of "
                    f"{insight['n_days']} similar days." if insight["side"] != "Middle"
                    else f"No consistent trend over {insight['n_days']} similar days.")
    return [
        ("Sea breeze", f"Thermal breeze in by ~{onset}, {turn}."),
        ("Terrain", "Palos Verdes blocks the left; the coast bends the breeze so there is more wind "
                    "near the breakwater (right side)."),
        ("Current", f"{tide['state']} tide{turns}; "
                    f"{'sets toward the harbour mouth' if tide['state'] == 'Flood' else 'runs out of the harbour'}."),
        ("History", history_text),
    ]


def insight_panel(insight, tide, label):
    st.markdown(
        f'<div class="la-dark"><div class="la-small">{esc(label)}</div>'
        f'<div class="big">{insight["speed"]:.0f} kt</div>Favoured side: <b>{esc(insight["side"])}'
        f'{" (towards breakwater)" if insight["side"] == "Right" else ""}</b><br>'
        f'Shifts: <b>{esc(insight["shift"])} + ~{insight["swing"]:.0f}° oscillations</b></div>',
        unsafe_allow_html=True)
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in why_rows(insight, tide))
    st.markdown(f'<div class="la-card"><b>Why?</b><table class="la-why">{rows}</table></div>',
                unsafe_allow_html=True)


def render_venue_map(render_geo_data):
    st.subheader("Venue map")
    c1, c2, _ = st.columns([1.3, 1.2, 2.5])
    c1.segmented_control("Wind direction", strategy.SECTORS, key="wind_sector")
    c2.segmented_control("Time of day", [11, 13, 15], key="map_hour", format_func=lambda h: f"{h}:00")
    insight, tide = current_insight()
    left, right = st.columns([2, 1], gap="medium")
    with left:
        render_layer_map("venue_map", insight["hour"], height=460)  # same map as Live
    with right:
        if insight["n_days"] == 0:
            st.warning(f"No {season()} day in 2021–2025 had {insight['sector']} wind at {insight['hour']}:00. "
                       "Pick another direction or hour.")
        else:
            insight_panel(insight, tide, f"Typical at {insight['hour']}:00 · from {insight['sector']}")
            st.markdown(f'<div class="la-card la-small">Based on {insight["n_days"]} historic days '
                        f'(of {insight["total_days"]}) with similar wind + your uploaded logs.</div>',
                        unsafe_allow_html=True)
            st.button("Generate coach brief →", type="primary", width="stretch",
                      on_click=go, args=("coach_brief",))

    st.subheader("Location, map & points")
    st.caption("One Load fetches all three for the chosen sailing area: local geodata, the Open-Meteo "
               "marine map and the point time series.")
    render_geo_data()


# ---------- 3. Venue rules ----------

def render_venue_rules(load_geolocation_data):
    st.header("Venue rules")
    st.caption(context_line())
    spot = strategy.VENUES[st.session_state.venue]
    left, right = st.columns([1, 1.4], gap="large")
    with left, st.container(border=True):
        st.markdown("#### Venue facts (local geodata)")
        try:
            bathymetry = load_geolocation_data()["bathymetry"]
            area = next(a for a in bathymetry["areas"] if a["key"] == spot["area"])
            depth = bathymetry["stats"]["value_at_area_centers"].get(spot["area"])
            st.metric("Race area radius", f"{area['radius_km']:.1f} km")
            st.metric("Centre depth", f"{depth:.1f} {bathymetry['units']}" if depth is not None else "N/A")
            st.write("Events: " + " · ".join(area["events"]))
            st.caption(area.get("notes", ""))
        except (OSError, KeyError, StopIteration, ValueError) as error:
            st.error(f"Could not load venue geodata: {error}")

    rule_docs = [doc for doc in documents() if doc["entity"] == "Venue rules" and doc["text"]]
    text = "\n".join(doc["text"] for doc in rule_docs)
    rules, covered = tagging.extract_rules(text)
    with right, st.container(border=True):
        st.markdown("#### Rules checklist")
        if not rule_docs:
            st.warning("No Notice of Race or Sailing Instructions uploaded. Add them in **Coach file** "
                       "(PDF, DOCX, TXT or a photo).")
        for item, lines in covered.items():
            badge = '<span class="la-ok">Found</span>' if lines else '<span class="la-warn">Check</span>'
            st.markdown(f'<div class="la-row"><div><b>{esc(item)}</b><div class="la-small">'
                        f'{esc(lines[0]) if lines else "Not in the uploaded documents"}</div></div>{badge}</div>',
                        unsafe_allow_html=True)
    if rules:
        st.subheader("All rule lines found")
        st.caption("From: " + ", ".join(doc["name"] for doc in rule_docs))
        for rule in rules:
            st.markdown(f"- {rule}")


# ---------- 4. Coach brief / 5. Sailor brief ----------

def answers(brief):
    edits = st.session_state.setdefault("edits", {})
    return [(q, edits.get(q, a)) for q, a in brief["questions"]]


def coach_notes_for_brief():
    """Lines from coach notes and transcripts that touch the brief's topics."""
    picked = []
    for doc in documents():
        if doc["entity"] in ("Coach notes", "Transcript", "Picture of text"):
            for topic in ("Side of course", "Start", "Upwind / downwind", "Sailor"):
                picked += [(doc["name"], topic, line) for line in doc["tags"].get(topic, [])[:2]]
    return picked


def briefing_text(brief, sailor=False):
    lines = [f"{'Sailor' if sailor else 'Coach'} brief — {context_line()}", ""]
    if not sailor:
        lines += [f"{k}: {v}" for k, v in brief["cards"].items()] + [""]
    lines += [f"{i}. {a}" if sailor else f"{i}. {q}\n   {a}" for i, (q, a) in enumerate(answers(brief), 1)]
    if not sailor:
        lines += ["", "Challenger AI:"] + [f"- {f} → {a}" for f, a in brief["challenger"]]
        lines += [f"Plan confidence: {brief['confidence']}"]
    return "\n".join(lines)


def render_coach_brief():
    insight, tide, brief = current_brief()
    st.header("Coach brief")
    st.caption(f"{context_line()} · drafted from the venue map, history and your files. "
               "Ready for the 08:00 team briefing.")
    if brief is None:
        st.warning("Pick a wind direction and hour with historic data in Venue · Geoinformation first.")
        return
    left, right = st.columns([2, 1], gap="medium")
    with left, st.container(border=True):
        for column, (label, value) in zip(st.columns(3), brief["cards"].items()):
            column.markdown(f'<div class="la-stat"><div class="la-small">{esc(label)}</div>'
                            f'<div class="v">{esc(value)}</div></div>', unsafe_allow_html=True)
        editing = st.session_state.get("editing", False)
        for number, (question, answer) in enumerate(answers(brief), 1):
            if editing:
                st.session_state.edits[question] = st.text_area(question, answer, key=f"edit_{number}")
            else:
                st.markdown(f'<div class="la-q"><div class="n">{number}</div><div><div class="t">'
                            f'{esc(question)}</div>{esc(answer)}</div></div>', unsafe_allow_html=True)
        b1, b2, b3, _ = st.columns([1, 1.2, 0.8, 1.6])
        b1.download_button("Export", briefing_text(brief), file_name=f"coach_brief_{st.session_state.race_day}.txt",
                           on_click="ignore", type="primary")
        b2.button("Sailor brief →", on_click=go, args=("sailor_brief",))
        if b3.button("Done" if editing else "Edit"):
            st.session_state.editing = not editing
            st.rerun()
        notes = coach_notes_for_brief()
        if notes:
            with st.expander(f"From your coach file ({len(notes)} lines)"):
                for name, topic, line in notes:
                    st.markdown(f"- **{topic}** — {line}  \n  <span class='la-small'>{esc(name)}</span>",
                                unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            st.markdown('#### Challenger AI <span class="la-warn">Tries to disprove the plan</span>',
                        unsafe_allow_html=True)
            for finding, action in brief["challenger"]:
                color = ORANGE if ("risk" in action or "Check" in action) else "#2b7139"
                st.markdown(f'<div class="la-card">{esc(finding)}<br><b style="color:{color}">{esc(action)}</b></div>',
                            unsafe_allow_html=True)
            st.markdown(f"Plan confidence: **{brief['confidence']}**")
        st.button("Start live monitoring →", type="primary", width="stretch", on_click=go, args=("live",))

    st.subheader("Race-area conditions at the planned hour")
    render_layer_map("brief_map", insight["hour"], height=420)


def render_sailor_brief():
    insight, tide, brief = current_brief()
    st.header("Sailor brief")
    st.caption(context_line())
    if brief is None:
        st.warning("Pick a wind direction and hour with historic data in Venue · Geoinformation first.")
        return
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        for number, (_, answer) in enumerate(answers(brief), 1):
            st.markdown(f'<div class="la-sailor">{number}. {esc(answer)}</div>', unsafe_allow_html=True)
        st.write("")
        st.download_button("Share with sailors", briefing_text(brief, sailor=True), on_click="ignore",
                           file_name=f"sailor_brief_{st.session_state.race_day}.txt", type="primary")
    with right:
        st.markdown(venue_svg(strategy.sector_center(insight["sector"]), insight["speed"], insight["side"],
                              ["Wind", "Pressure"], tide["state"]), unsafe_allow_html=True)
        for label, value in brief["cards"].items():
            st.markdown(f'<div class="la-stat" style="margin-bottom:6px"><div class="la-small">{esc(label)}</div>'
                        f'<div class="v">{esc(value)}</div></div>', unsafe_allow_html=True)


# ---------- 6. Strategy overview ----------

def render_what_if(insight):
    """Toggles for weather options and the team's risk appetite; shows how the approach changes."""
    st.subheader("What if…")
    c1, c2, c3, c4 = st.columns([1.5, 1.1, 1.1, 1.4])
    c1.segmented_control("Wind direction", strategy.SECTORS, key="wi_sector")
    c2.segmented_control("Wind strength", list(strategy.STRENGTHS), key="wi_strength")
    c3.segmented_control("Sea breeze", strategy.BREEZE_TIMING, key="wi_breeze")
    c4.segmented_control("Team risk appetite", list(strategy.APPETITES), key="risk_appetite")
    state = st.session_state
    what_if = strategy.venue_insight(history(), state.wi_sector, insight["hour"])
    base = strategy.scenario_approach(insight, strategy.strength_band(insight["speed"]), "On time",
                                      state.risk_appetite)
    scenario = strategy.scenario_approach(what_if, state.wi_strength, state.wi_breeze, state.risk_appetite)
    if not what_if["n_days"]:
        st.caption(f"No {season()} day in 2021–2025 had {state.wi_sector} at {insight['hour']}:00, so the "
                   "side is unknown and the approach falls back to the middle.")
    labels = {"side": "Favoured side", "commitment": "Commitment", "start": "Start",
              "first_beat": "First beat", "corners": "How far to go", "plan_b": "Plan B trigger"}
    cells = st.columns(3)
    for index, (key, label) in enumerate(labels.items()):
        changed = scenario[key] != base[key]
        badge = '<span class="la-warn">changed</span>' if changed else '<span class="la-ok">as plan</span>'
        cells[index % 3].markdown(f'<div class="la-card"><div class="la-small">{label} {badge}</div>'
                                  f'<b>{esc(scenario[key])}</b></div>', unsafe_allow_html=True)
    st.caption(f"Compared with the brief: {insight['sector']} at {insight['hour']}:00, "
               f"{strategy.strength_band(insight['speed']).lower()} breeze, sea breeze on time, "
               f"{state.risk_appetite.lower()} appetite.")


def render_scenario_table(insight):
    """Every wind scenario seen at this hour: likelihood x impact vs the team's appetite, with a lever per row."""
    appetite = st.session_state.risk_appetite
    rows = strategy.scenario_matrix(history(), insight["hour"], insight["sector"], insight["speed"], appetite)
    st.subheader("Scenarios vs risk appetite")
    st.caption(f"Likelihood (1–5, share of {season()} days at {insight['hour']}:00) × impact on the plan (1–5) = "
               f"score. {appetite} appetite accepts up to {strategy.APPETITES[appetite]}; pick a lever per "
               "scenario to see the residual score.")
    widths = [2.4, 0.6, 0.5, 0.5, 0.8, 1.2, 3.4, 0.8]
    for column, title in zip(st.columns(widths), ["Scenario", "Days", "L", "I", "Score", "Appetite",
                                                  "Lever", "Residual"]):
        column.markdown(f'<div class="la-small"><b>{title}</b></div>', unsafe_allow_html=True)
    for row in rows:
        cols = st.columns(widths, vertical_alignment="center")
        cols[0].markdown(f"**{row['scenario']}**  \n<span class='la-small'>favours {row['side'].lower()}</span>",
                         unsafe_allow_html=True)
        cols[1].write(row["days"])
        cols[2].write(row["likelihood"])
        cols[3].write(row["impact"])
        chip = "la-ok" if row["within"] else "la-bad"
        cols[4].markdown(f'<span class="{chip}">{row["score"]}</span>', unsafe_allow_html=True)
        cols[5].markdown(f'<span class="la-small">{"within" if row["within"] else "outside"} appetite</span>',
                         unsafe_allow_html=True)
        key = f"lever_{appetite}_{row['scenario']}"
        lever = cols[6].segmented_control("Lever", list(strategy.LEVERS), default=row["lever"], key=key,
                                          label_visibility="collapsed") or "None"
        left = strategy.residual(row, lever)
        cols[7].markdown(f'<span class="{"la-ok" if left <= strategy.APPETITES[appetite] else "la-bad"}">'
                         f'{left}</span>', unsafe_allow_html=True)
    st.caption("Levers: None keeps the plan · Hedge stays closer to the middle (impact −1) · "
               "Switch side commits to the other side (impact −2) · Plan B prepares the light-air / late-breeze "
               "plan (likelihood −1, impact −1). Recommended levers are pre-selected.")

def render_strategy_overview():
    insight, tide, brief = current_brief()
    st.header("Strategy overview")
    st.caption(context_line())
    docs = documents()
    live_started = st.session_state.get("live_index") is not None
    steps = [("Start trigger · event session", True),
             ("Previous-year weather & geodata", insight["n_days"] > 0),
             ("Coach documentation", any(doc["text"] for doc in docs)),
             ("Strategy prediction", brief is not None),
             ("Challenger iterations", brief is not None),
             ("Live monitoring", live_started),
             ("End trigger · event done", False)]
    st.markdown('<div class="la-flow">' + "".join(
        f'<div class="{"done" if done else ""}">{"✓ " if done else ""}{esc(name)}</div>' for name, done in steps)
        + "</div>", unsafe_allow_html=True)
    if brief is None:
        st.warning("Pick a wind direction and hour with historic data in Venue · Geoinformation first.")
        return

    render_what_if(insight)
    render_scenario_table(insight)

    plan, race, files = st.columns(3, gap="medium")
    with plan, st.container(border=True):
        st.markdown("#### Plan")
        st.markdown(f"**Favoured side:** {insight['side']}  \n**Shifts:** {insight['shift']} "
                    f"(~{abs(insight['veer_rate']):.0f}°/h)  \n**Wind:** {brief['cards']['Wind']}  \n"
                    f"**Sea breeze:** {brief['cards']['Sea breeze']}  \n**Current:** {brief['cards']['Current']}"
                    f"  \n**Confidence:** {brief['confidence']}")
    with race, st.container(border=True):
        st.markdown("#### What the winners did")
        try:
            summary = race_summary()
        except (OSError, KeyError, ValueError) as error:
            st.error(f"Race tracks unavailable: {error}")
            summary = None
        if summary:
            st.caption(f"SailSync {summary['boat_class']} · {summary['date']} · {summary['fleet_size']} tracks")
            for item in summary["races"]:
                st.markdown(f"**{item['race']}** — winners went **{item['winner_side'] or '—'}** on beat 1 "
                            f"({len(item['winner_offsets'])} of {len(summary['winners'])} winners logged, "
                            f"upwind ≈ {item['upwind_bearing']:.0f}°)")
            agrees = summary["verdict"] == insight["side"]
            st.markdown(f'<span class="{"la-ok" if agrees else "la-warn"}">'
                        f'{"Agrees with the plan" if agrees else "Differs from the plan"}: '
                        f'{summary["verdict"]} in {summary["agreement"]} of {len(summary["races"])} races</span>',
                        unsafe_allow_html=True)
    with files, st.container(border=True):
        st.markdown("#### Coach file signals")
        counts = {}
        for doc in docs:
            for topic, lines in doc["tags"].items():
                counts[topic] = counts.get(topic, 0) + len(lines)
        if counts:
            for topic, count in sorted(counts.items(), key=lambda item: -item[1]):
                st.markdown(f"- {topic}: {count} mentions")
        else:
            st.caption("No text read yet.")

    st.subheader("Challenger findings")
    for finding, action in brief["challenger"]:
        st.markdown(f"- {finding} → **{action}**")
    if summary:
        with st.expander("First-beat offsets per boat (metres, + = right looking upwind)"):
            race_tabs = st.tabs([item["race"] for item in summary["races"]])
            for tab, item in zip(race_tabs, summary["races"]):
                tab.bar_chart({name: offset for name, offset in sorted(item["offsets"].items(), key=lambda kv: kv[1])},
                              horizontal=True, height=520)


# ---------- 7. Speed forecast ----------

def render_speed_forecast():
    """Replay an unseen boat and predict its speed 30 seconds ahead."""
    st.header("ILCA 7 speed forecast")
    st.caption("A short-horizon forecast learned from 44 SailSync GPS tracks. "
               "Choose any of the three LA28 sailing areas.")

    horizon = 30
    data = speed_dataset(horizon)
    locations = boat_speed.FORECAST_LOCATIONS
    if not st.session_state.get("_speed_location_default_migrated"):
        if st.session_state.get("speed_location") in (None, "Belmont Shore"):
            st.session_state["speed_location"] = "LA Outer Harbor"
        st.session_state["_speed_location_default_migrated"] = True
    location_col, boat_col = st.columns([1, 2])
    location = location_col.selectbox("Sailing area", list(locations), key="speed_location")
    location_info = locations[location]
    if not location_info["telemetry"]:
        st.markdown(
            f'<div class="la-card"><b>{esc(location)}</b> · '
            f'{location_info["lat"]:.3f}, {location_info["lon"]:.3f} '
            '<span class="la-warn">No data available</span></div>',
            unsafe_allow_html=True,
        )
        st.warning(
            "No calibrated ILCA 7 GPS data is available for this sailing area. "
            "The map shows its exact location and race-area radius without a route.",
            icon="ℹ️",
        )
        layer = st.selectbox(
            "Map data",
            ["Location only", *MAP_LAYERS],
            key="speed_uncalibrated_layer",
        )
        render_speed_area_map(location, location_info, layer, "speed_uncalibrated")
        return

    available_boats = set(data["boat"].unique()) - SPEED_SELECTOR_EXCLUSIONS
    leaders = [name for name in SPEED_LEADER_LABELS if name in available_boats]
    boats = leaders + sorted(available_boats - set(leaders))
    selected_boat = boat_col.selectbox(
        "Live boat feed",
        boats,
        key="speed_boat",
        format_func=lambda name: SPEED_LEADER_LABELS.get(name, name),
    )

    boat_rows = data[data["boat"] == selected_boat].reset_index(drop=True)
    maximum = max(0, len(boat_rows) - 1)
    if st.session_state.get("speed_replay_boat") != selected_boat:
        st.session_state.speed_replay_boat = selected_boat
        st.session_state.speed_replay_position = min(maximum, maximum // 2)
    index = min(
        maximum, st.session_state.get("speed_replay_position", maximum // 2)
    )
    model = speed_model(horizon, selected_boat)

    st.subheader("GPS movement and predicted position")
    layer = st.selectbox(
        "Map data",
        ["GPS speed route", "Location only", *MAP_LAYERS],
        key="speed_calibrated_layer",
    )
    if layer == "GPS speed route":
        st.caption(
            "Hover over the trail for speed. Dark marker = current GPS position; orange marker = "
            f"projected position in {horizon} seconds at the predicted speed."
        )
        speed_replay_map(
            boat_rows, index, model, horizon, location, location_info
        )
    else:
        render_speed_area_map(
            location,
            location_info,
            layer,
            "speed_calibrated",
            gps_overlay=speed_track_points(boat_rows, model, horizon),
            gps_index=index,
        )
    st.caption(
        f"Validation MAE: {model.validation_mae_kt:.2f} kt · "
        f"{model.training_rows:,} samples from {model.boats} other boats · "
        "GPS-derived speed is smoothed over 30 seconds."
    )


# ---------- 8. Live ----------

def render_live():
    st.header("Live strategy check")
    _, _, brief = current_brief()
    plan = st.session_state.get("plan")
    if brief is None or not plan:
        st.warning("The briefing needs a valid wind direction and hour in Venue · Geoinformation first.")
        return
    day = live_data()[live_data()["date"] == st.session_state.race_day]
    hours = day[day["hour"].between(9, 18)].to_dict("records")
    if not hours:
        st.error("No replay data for this race day.")
        return
    st.session_state.setdefault("live_index", 1)
    last = min(st.session_state.live_index, len(hours) - 1)

    def check(index):
        return strategy.live_check(plan["sector"], plan["low"], plan["high"], hours[index], hours[index + 1:index + 3])

    top, sim = st.columns([3, 1])
    top.caption("Weather pulled every hour and compared with this morning's brief. "
                f"Hackathon mode: replaying {season()} {strategy.LIVE_YEAR} data as if live.")
    if sim.button("Simulate next hour ▸", type="primary", width="stretch", disabled=last >= len(hours) - 1):
        st.session_state.live_index = st.session_state.selected_hour = last + 1
        st.rerun()
    selected = min(st.session_state.get("selected_hour", last), last)

    snapshots, main = st.columns([1, 2.6], gap="medium")
    with snapshots, st.container(border=True):
        st.markdown("#### Hourly snapshots")
        for index in range(last, -1, -1):
            result = check(index)
            mood = "on plan" if result["status"] == "Plan holds" else result["status"].lower()
            row = hours[index]
            if st.button(f"{row['time']:%d %b %H:%M} · {strategy.sector(row['dir'])} {row['speed']:.0f} kt · {mood}",
                         key=f"snap_{index}", width="stretch",
                         type="primary" if index == selected else "secondary"):
                st.session_state.selected_hour = index
                st.rerun()

    with main:
        now, upcoming = hours[selected], hours[selected + 1:selected + 3]
        result = check(selected)
        next_speeds = [row["speed"] for row in upcoming] or [now["speed"]]
        for column, (label, value) in zip(st.columns(3), [
                ("Wind now", f"{strategy.sector(now['dir'])} {now['speed']:.0f} kt"),
                ("Next 2 h", f"{min(next_speeds):.0f}–{max(next_speeds):.0f} kt"),
                ("Sky", strategy.sky(now["cloud"]))]):
            column.markdown(f'<div class="la-card"><div class="la-small">{label}</div>'
                            f'<div style="font-size:1.5rem;font-weight:800;color:{INK}">{value}</div></div>',
                            unsafe_allow_html=True)
        badge = {"Plan holds": "la-ok", "Change coming": "la-warn", "Change": "la-bad"}[result["status"]]
        st.markdown(f'<div class="la-card"><b>AI insight</b> <span class="{badge}">{result["status"]}</span>'
                    f'<p style="margin:8px 0 0">{esc(result["message"])}</p><div class="la-small">Rule engine v0.1: '
                    f'compares live wind with the brief ({plan["sector"]} {plan["low"]:.0f}–{plan["high"]:.0f} kt).'
                    '</div></div>', unsafe_allow_html=True)
        if result["warning"]:
            st.warning(result["warning"], icon="📣")

        view_col, map_col = st.columns([1, 2.6])
        with view_col:
            offset = st.segmented_control("Map time", [0, 1, 2], default=0, key="live_offset",
                                          format_func=lambda h: "T0" if h == 0 else f"T+{h}")
            shown = hours[min(selected + (offset or 0), len(hours) - 1)]
            st.markdown(f'<div class="la-dark"><div class="la-small">{shown["time"]:%H:%M} · from '
                        f'{strategy.sector(shown["dir"])}</div><div class="big">{shown["speed"]:.0f} kt</div>'
                        f'Gusts {shown["gust"]:.0f} kt</div>', unsafe_allow_html=True)
        with map_col:
            render_layer_map("live_map", shown["time"].hour, height=440)

        st.markdown("#### Insight notifications")
        feed = [(index, check(index)) for index in range(last, -1, -1)]
        feed = [(index, r) for index, r in feed if r["status"] != "Plan holds"]
        if not feed:
            st.caption("No changes yet. New strategy suggestions appear here when the weather moves off plan.")
        for index, r in feed:
            st.info(f"**{hours[index]['time']:%H:%M}** — {r['message']}"
                    + (f"\n\n{r['warning']}" if r["warning"] else ""),
                    icon="🔁" if r["status"] == "Change" else "⏰")
