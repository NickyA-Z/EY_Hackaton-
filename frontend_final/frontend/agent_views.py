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
from frontend_final.frontend.current_map import combine_layers, render_current_map  # noqa: E402
from frontend_final.frontend.race_map import render_current_map as render_race_map  # noqa: E402
from frontend_final.frontend.race_progress import load_race_progress, race_track_window  # noqa: E402

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
.la-ex {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:4px 0 14px; }}
.la-ex > div {{ background:#fff; border:1px solid #d9e4e1; border-top:4px solid {TEAL}; border-radius:12px; padding:12px 14px; }}
.la-ex h5 {{ margin:0 0 8px; font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; color:#55666e; }}
.la-ex .hero {{ font-size:1.5rem; font-weight:800; color:{INK}; line-height:1.15; }}
.la-ex .step {{ display:flex; align-items:center; gap:8px; margin:5px 0; font-size:.85rem; }}
.la-ex .step b {{ background:{INK}; color:#fff; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:.75rem; }}
.la-ex .bar {{ display:flex; align-items:center; gap:8px; margin:6px 0; font-size:.8rem; }}
.la-ex .bar span.l {{ width:112px; color:#55666e; }}
.la-ex .bar span.t {{ flex:1; background:#eef2f1; border-radius:5px; height:16px; }}
.la-ex .bar span.t i {{ display:block; height:100%; border-radius:5px; background:{TEAL}; }}
.la-ex .bar span.v {{ width:38px; font-weight:700; text-align:right; }}
@media (max-width:900px) {{ .la-ex {{ grid-template-columns:1fr; }} }}
.la-slide {{ background:#fbfcfb; border:1px solid #d9e4e1; border-radius:16px; padding:18px 20px; margin:6px 0 18px;
  background-image:radial-gradient(#e3ebe9 1px, transparent 1px); background-size:18px 18px; }}
.la-slide .title {{ font-size:1.25rem; font-weight:800; color:{INK}; margin-bottom:14px; }}
.la-slide h6 {{ margin:0 0 6px; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:#55666e; }}
.la-slide .pipe {{ display:grid; grid-template-columns:repeat(5,1fr); gap:26px; }}
.la-slide .stage {{ position:relative; background:#fff; border:2px solid {TEAL}; border-radius:14px; padding:12px; }}
.la-slide .stage:not(:last-child)::after {{ content:"➜"; position:absolute; right:-23px; top:42%; color:{ORANGE}; font-size:1.3rem; }}
.la-slide .stage .n {{ position:absolute; top:-12px; left:12px; background:{ORANGE}; color:#fff; border-radius:50%;
  width:24px; height:24px; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:.8rem; }}
.la-slide .stage .big {{ font-size:1.6rem; font-weight:800; color:{INK}; margin:2px 0 6px; }}
.la-slide .chip {{ display:inline-block; background:#e7f0ee; color:{INK}; border-radius:999px; padding:2px 8px; margin:2px 3px 0 0; font-size:.72rem; }}
.la-slide .lower {{ display:grid; grid-template-columns:1.2fr 1fr 0.9fr; gap:14px; margin-top:16px; }}
.la-slide .panel {{ background:#fff; border:1px solid #d9e4e1; border-radius:12px; padding:12px 14px; }}
.la-slide .bar {{ display:flex; align-items:center; gap:8px; margin:7px 0; font-size:.8rem; }}
.la-slide .bar span.l {{ width:118px; color:#55666e; }}
.la-slide .bar span.t {{ flex:1; background:#eef2f1; border-radius:5px; height:18px; }}
.la-slide .bar span.t i {{ display:block; height:100%; border-radius:5px; background:{TEAL}; }}
.la-slide .bar span.v {{ width:38px; font-weight:700; text-align:right; }}
.la-slide .big-o {{ font-size:2rem; font-weight:800; color:{TEAL}; line-height:1.1; }}
.la-slide .val {{ display:flex; align-items:center; gap:10px; margin:10px 0; font-weight:600; color:{INK}; }}
.la-slide .val b {{ background:{INK}; color:#fff; border-radius:10px; min-width:34px; height:34px; display:flex;
  align-items:center; justify-content:center; font-size:1.1rem; }}
@media (max-width:1000px) {{ .la-slide .pipe, .la-slide .lower {{ grid-template-columns:1fr; }}
  .la-slide .stage::after {{ display:none; }} }}
/* ---------- live view: instrument band + connected timeline ---------- */
.lv-band {{ display:grid; grid-template-columns:280px minmax(0,1fr); gap:28px; align-items:start; padding:26px 30px; margin:4px 0 18px;
  border-radius:20px; color:#fff; background:radial-gradient(120% 140% at 0% 0%, #0d3a66 0%, #071c2c 55%, #02050b 100%);
  box-shadow:0 18px 40px rgba(7,28,44,.18); }}
.lv-dial {{ width:220px; height:220px; margin:0 auto; }}
.lv-head {{ margin-bottom:8px; }}
.lv-head span {{ font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; color:#5fd0ea; }}
.lv-head .t {{ margin:4px 0 0; color:#fff; font-size:clamp(1.6rem, 2.6vw, 2.3rem); font-weight:700;
  letter-spacing:-.01em; line-height:1.15; }}
.st-key-showcase_mode {{ position:relative; z-index:5; }}
.lv-mid {{ display:flex; flex-direction:column; gap:20px; min-width:0; }}
.lv-path {{ display:flex; align-items:center; gap:0; }}
.lv-path i {{ flex:1; height:2px; min-width:24px; background:linear-gradient(90deg, rgba(95,208,234,.8), var(--st)); }}
.lv-node {{ padding:12px 16px; border:1px solid rgba(255,255,255,.14); border-radius:14px; background:rgba(255,255,255,.05);
  backdrop-filter:blur(8px); white-space:nowrap; }}
.lv-node span {{ display:block; font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; color:rgba(255,255,255,.6); }}
.lv-node b {{ display:block; font-size:1.35rem; font-weight:800; margin-top:2px; }}
.lv-node em {{ display:block; font-style:normal; font-size:.78rem; color:rgba(255,255,255,.6); white-space:normal; max-width:280px; }}
.lv-node.now {{ border-color:var(--st); box-shadow:0 0 0 3px color-mix(in srgb, var(--st) 25%, transparent); }}
.lv-insight {{ position:relative; padding:16px 18px 14px; border-radius:14px; background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.1); }}
.lv-tag {{ position:absolute; top:-12px; left:16px; color:#000; font-weight:700; font-size:.78rem; padding:3px 9px; border-radius:4px; }}
.lv-status {{ font-weight:700; font-size:.82rem; letter-spacing:.06em; text-transform:uppercase; margin-top:4px; }}
.lv-insight p {{ margin:6px 0 6px; font-size:1.12rem; line-height:1.45; color:#fff; }}
.lv-rule {{ font-size:.75rem; color:rgba(255,255,255,.5); }}
.lv-cap {{ font-size:.75rem; letter-spacing:.14em; text-transform:uppercase; color:#55666e; margin-bottom:6px; }}
.st-key-live_timeline {{ position:relative; margin-bottom:18px; }}
.st-key-live_timeline [data-testid="stHorizontalBlock"] {{ position:relative; gap:10px; }}
.st-key-live_timeline [data-testid="stHorizontalBlock"]::before {{ content:""; position:absolute; left:0; right:0; top:50%;
  height:2px; background:linear-gradient(90deg, #5fd0ea, #d9e4e1); z-index:0; }}
.st-key-live_timeline button {{ position:relative; z-index:1; border-radius:14px; min-height:3.4rem; line-height:1.25;
  background:#fff; border:1px solid #d9e4e1; color:{INK}; font-size:.85rem; box-shadow:0 4px 12px rgba(7,28,44,.06); }}
.st-key-live_timeline button[kind="primary"] {{ background:{INK}; border-color:{INK}; color:#fff;
  box-shadow:0 0 0 3px rgba(95,208,234,.45); }}
.st-key-live_timeline button[kind="primary"]:hover {{ background:{INK}; }}
.st-key-simulate_next button {{ border-style:dashed; color:#FF6600; border-color:#FF6600; background:#fff7f1; }}
.lv-feed {{ border-left:2px solid #d9e4e1; margin:6px 0 10px 8px; padding-left:18px; }}
.lv-item {{ position:relative; display:flex; gap:14px; padding:10px 0; }}
.lv-item::before {{ content:""; position:absolute; left:-25px; top:16px; width:12px; height:12px; border-radius:50%;
  background:#FF6600; box-shadow:0 0 0 4px #fff; }}
.lv-item.warn::before {{ background:#f59e0b; }}
.lv-t {{ font-weight:800; color:{INK}; min-width:48px; }}
@media (max-width:900px) {{ .lv-band {{ grid-template-columns:1fr; justify-items:center; }}
  .lv-mid {{ width:100%; }}
  .lv-path {{ flex-direction:column; align-items:stretch; }} .lv-path i {{ height:18px; width:2px; min-width:0; margin:0 auto; }} }}
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


@st.cache_data(show_spinner=False)
def speed_race_progress():
    return load_race_progress()


def speed_replay_map(rows, index, model, horizon, *, location_name, location_info, race=None,
                     first_beat=True, compare_agent=True):
    """Build GPS playback data for the same renderer used by the Live map."""
    points = speed_track_points(rows, model, horizon)
    render_race_map(
        speed_map_payload(
            location_name,
            location_info,
            title="GPS speed route",
            gps_track=points,
            race_progress=[race] if race else [],
            replay_phase="first_beat" if first_beat else "full_race",
            compare_agent=compare_agent,
            focus_boat=rows.iloc[0]["boat"] if not rows.empty else None,
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
    if st.session_state.get("marine_rate_limited") and st.button("Retry marine data", key=f"{key}_retry"):
        st.session_state["marine_rate_limited"] = False
        st.rerun()
    st.session_state.setdefault(key, list(MAP_LAYERS))
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
    cache = st.session_state.setdefault("marine_grid_cache", {})
    grids = []
    if st.session_state.get("marine_rate_limited"):
        st.warning("Open-Meteo's daily API limit has been reached. Showing marine layers already loaded in this session; new layers will be available when the limit resets.")
        return [cache[(latitude, longitude, str(day), name)] for name in names
                if (latitude, longitude, str(day), name) in cache]
    with st.spinner(f"Building {', '.join(name.lower() for name in names)}…"):
        for name in names:
            cache_key = (latitude, longitude, str(day), name)
            if cache_key in cache:
                grids.append(cache[cache_key])
                continue
            try:
                grid = get_map_grid(
                    latitude, longitude, day, name,
                    bounds=local_bounds(latitude, longitude, 4_000),
                    grid_rows=5, grid_columns=5,
                )
                cache[cache_key] = grid
                grids.append(grid)
            except requests.exceptions.RequestException as error:
                if getattr(getattr(error, "response", None), "status_code", None) == 429:
                    st.session_state["marine_rate_limited"] = True
                    st.warning("Open-Meteo's daily API limit has been reached. Showing any layers already loaded in this session. Try new data after the limit resets.")
                    break
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

    if st.session_state.get("marine_rate_limited"):
        st.warning("Open-Meteo's daily API limit has been reached. Select Location only to view the sailing area without marine data.")
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
                grid_rows=5,
                grid_columns=5,
            )
    except requests.exceptions.RequestException as error:
        if getattr(getattr(error, "response", None), "status_code", None) == 429:
            st.session_state["marine_rate_limited"] = True
            st.warning("Open-Meteo's daily API limit has been reached. Select Location only to view the sailing area without marine data.")
        else:
            st.error(f"Could not load the regional map layer: {describe_error(error)}")
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
        "boat_label": SPEED_LEADER_LABELS.get(st.session_state.get("speed_boat"), st.session_state.get("speed_boat")),
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

# ---------- model explainer (demo toggle) ----------

@st.cache_data(show_spinner=False)
def race_model_outcome():
    """Numbers for the race-model slide (None if no race data downloaded)."""
    try:
        from backend.race_model import model as race_model
        table, marks, tracks = race_model.build()
    except (SystemExit, FileNotFoundError):
        return None
    summary = race_model.summary(table)
    summary["label"] = summary["side"] + " · " + summary["style"]
    summary["ahead"] = summary["gained_pct"] * summary["legs"]
    by_label = summary.groupby("label")[["ahead", "legs"]].sum()
    fit = race_model.fit(table)
    return {"rows": (by_label["ahead"] / by_label["legs"]).round().astype(int).sort_values(ascending=False).to_dict(),
            "legs": int(len(table)), "boats": int(table["boat_id"].nunique()), "races": int(table["race"].nunique()),
            "points": int(sum(len(t) for session in tracks.values() for t in session.values())),
            "marks": int(len(marks)), "train": fit["train_rows"], "test": fit["test_rows"], "mae": fit["test_mae_s"]}


def _bars(rows):
    return "".join(f'<div class="bar"><span class="l">{esc(k)}</span><span class="t"><i style="width:{v}%"></i></span>'
                   f'<span class="v">{v}%</span></div>' for k, v in rows.items())


def _loop_svg(steps):
    """Circular fine-tuning loop: steps placed on a ring with arrows between them."""
    cx, cy, r = 150, 120, 82
    nodes = []
    for i, label in enumerate(steps):
        angle = -math.pi / 2 + 2 * math.pi * i / len(steps)
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        nodes.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="{TEAL}"/>'
                     f'<text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">{i + 1}</text>'
                     f'<text x="{x + (14 if x >= cx else -14):.0f}" y="{y + 4:.0f}" font-size="11" fill="{INK}" '
                     f'text-anchor="{"start" if x >= cx else "end"}">{esc(label)}</text>')
    ring = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#b9d3d0" stroke-width="2" stroke-dasharray="5 5"/>'
    return (f'<svg viewBox="-60 0 420 240" width="100%" height="230">{ring}'
            f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="13" font-weight="800" fill="{INK}">repeat</text>'
            f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="10" fill="#55666e">until error stops falling</text>'
            + "".join(nodes) + "</svg>")


def _slide(title, stages, loop, outcome, value):
    pipe = "".join(
        f'<div class="stage"><div class="n">{i}</div><h6>{esc(head)}</h6><div class="big">{big}</div>'
        + "".join(f'<span class="chip">{esc(c)}</span>' for c in chips) + "</div>"
        for i, (head, big, chips) in enumerate(stages, 1))
    values = "".join(f'<div class="val"><b>{icon}</b>{esc(text)}</div>' for icon, text in value)
    return (f'<div class="la-slide"><div class="title">{esc(title)}</div><div class="pipe">{pipe}</div>'
            f'<div class="lower"><div class="panel"><h6>Fine-tuning loop</h6>{loop}</div>'
            f'<div class="panel"><h6>Outcome</h6>{outcome}</div><div class="panel"><h6>Value for the coach</h6>{values}</div>'
            f'</div></div>')


def model_explainer(kind, speed_model=None):
    """Demo toggle: one whiteboard-style slide. Data -> model -> fine-tuning -> outcome -> value."""
    if not st.toggle("Demo · how the model works", key=f"explain_{kind}"):
        return
    if kind == "race":
        o = race_model_outcome()
        if o is None:
            st.info("Download the race data first: python -m backend.race_model.fetch_data")
            return
        stages = [
            ("Data ingested", f"{o['points']:,}", ["GPS points", f"{o['boats']} boats", f"{o['races']} races", "mark times", "wind per leg"]),
            ("Course rebuilt", f"{o['marks']}", ["buoys + starts", "median of boats", "at rounding time"]),
            ("Modelled", f"{o['legs']}", ["boat-legs", "left / right", "how far out", "seconds vs fleet"]),
            ("Fine-tuned", f"{o['train']} → {o['test']}", ["train: fleet", "test: winners", "25% threshold"]),
            ("Outcome", f"{max(o['rows'].values())}%", ["best approach", "beats typical boat"]),
        ]
        loop = _loop_svg(["Train on the fleet", "Test on the winners", "Measure the error", "Tune features + threshold", "Add more race days"])
        mae = f" · winner error {o['mae']:.0f} s" if o["mae"] is not None else ""
        outcome = (_bars(o["rows"]) + f'<div class="la-small">% of legs ahead of the typical boat · 19 Jul, leg 1{mae}</div>')
        value = [("◎", "Which side pays, per wind"), ("⚑", "Bold or safe: proven odds"), ("↻", "Gets sharper every regatta")]
        st.markdown(_slide("Race model · which approach gains time", stages, loop, outcome, value), unsafe_allow_html=True)
    else:
        m = speed_model
        stages = [
            ("Data ingested", "44", ["GPS tracks", "19 Jul", "1 point / 1.7 s"]),
            ("Features", "7", ["speed now", "30 s + 60 s trend", "acceleration", "turn rate", "heading"]),
            ("Modelled", "ridge", ["small + explainable", "10 s steps", "30 s ahead"]),
            ("Fine-tuned", f"{m.boats}", ["other boats", "chosen boat left out", "last 20% held back"]),
            ("Outcome", f"{m.validation_mae_kt:.2f} kt", ["average error", f"{m.training_rows:,} samples"]),
        ]
        loop = _loop_svg(["Train on other boats", "Hold back race end", "Measure the error", "Tune smoothing + ridge", "Add more tracks"])
        span = m.residual_high_kt - m.residual_low_kt
        outcome = (f'<div class="big-o">{m.validation_mae_kt:.2f} kt</div><div class="la-small">average error, 30 s ahead</div>'
                   f'<div class="big-o" style="margin-top:10px">±{span / 2:.1f} kt</div><div class="la-small">80% band</div>')
        value = [("⏱", "See slowdowns 30 s early"), ("⛵", "Compare trim + tactics"), ("↻", "Same model at any venue")]
        st.markdown(_slide("Speed model · speed 30 seconds ahead", stages, loop, outcome, value), unsafe_allow_html=True)


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
    model_explainer("race")
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
    st.header("Race replay & forecast")
    st.caption("Recorded SailSync tracks · 19 July 2026 · ILCA 7")

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

    races = speed_race_progress()
    if not races:
        st.info("Race course data is unavailable.")
        return
    race_number = boat_col.radio("Race", [race["race"] for race in races],
                                format_func=lambda number: f"Race {number}", horizontal=True, key="speed_race")
    race = next(race for race in races if race["race"] == race_number)
    phase_col, compare_col = st.columns([2, 1])
    phase = phase_col.radio("Replay phase", ["First beat", "Full race"], horizontal=True, key="speed_phase")
    first_beat = phase == "First beat"
    agent_available = any(track["agent"] and track["points" if first_beat else "full_points"]
                          for track in race["tracks"])
    compare_agent = compare_col.toggle("Compare with agent", value=True, disabled=not agent_available,
                                       key="speed_compare_agent") and agent_available
    if not agent_available:
        st.caption("No agent simulation is available for this race and replay phase.")
    st.caption(" · ".join(f"{entry['position']}: {entry['name']}"
                          + (" (GPS unavailable)" if not entry["gps_available"] else "")
                          for entry in race["rankings"]))
    available_boats = set(data["boat"].unique()) - SPEED_SELECTOR_EXCLUSIONS
    boats = [entry["name"] for entry in race["rankings"] if entry["name"] in available_boats]
    boats += sorted(name for name in available_boats - set(boats) if " Agent" not in name)
    if st.session_state.get("speed_focus_race") != race_number:
        st.session_state["speed_boat"] = boats[0]
        st.session_state["speed_focus_race"] = race_number
    selected_boat = st.selectbox("Focus boat", boats, key="speed_boat",
                                 format_func=lambda name: next((f"{entry['position']} · {name}" for entry in race["rankings"]
                                                          if entry["name"] == name), name))
    boat_rows, _ = race_track_window(data[data["boat"] == selected_boat], race, first_beat)
    if boat_rows.empty:
        st.info("No recorded GPS points for this boat in the selected race.")
        return
    if not first_beat:
        st.caption("Estimated 45-minute race window; official finish times are unavailable. "
                   "Agent comparison uses the full-race simulation where available.")
        if not race["finish"]:
            st.caption("Finish position unavailable for this race.")
    model = speed_model(horizon, selected_boat)
    st.caption("Use ▶ Play / ❚❚ Pause on the map to control the race replay.")
    speed_replay_map(boat_rows, 0, model, horizon, location_name=location, location_info=location_info,
                     race=race, first_beat=first_beat, compare_agent=compare_agent)

    with st.expander("Environmental layers"):
        layer = st.selectbox("Map data", ["Location only", *MAP_LAYERS], key="speed_calibrated_layer")
        render_speed_area_map(location, location_info, layer, "speed_calibrated")
    with st.expander("How the forecast works & model accuracy"):
        model_explainer("speed", model)
        st.caption(
            f"Validation MAE: {model.validation_mae_kt:.2f} kt · "
            f"{model.training_rows:,} samples from {model.boats} other boats · "
            "GPS-derived speed is smoothed over 30 seconds."
        )


# ---------- 8. Live ----------

def render_live(showcase=False):
    """Live strategy check. showcase=<app title>: the stand-alone Live mode, title inside the band."""
    if not showcase:
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

    selected = min(st.session_state.get("selected_hour", last), last)
    now, upcoming = hours[selected], hours[selected + 1:selected + 3]
    result = check(selected)
    st.markdown(live_band(plan, now, upcoming, result, title=showcase or None), unsafe_allow_html=True)

    with st.container(key="live_timeline"):
        st.markdown(f'<div class="lv-cap">Race day · {now["time"]:%d %b} · replaying {season()} '
                    f'{strategy.LIVE_YEAR} as if live</div>', unsafe_allow_html=True)
        nodes = st.columns(len(hours) + 1)
        for index in range(last + 1):
            row = hours[index]
            dot = {"Plan holds": ":green[●]", "Change coming": ":orange[●]", "Change": ":red[●]"}[check(index)["status"]]
            if nodes[index].button(f"{dot} {row['time']:%H:%M}  \n{strategy.sector(row['dir'])} {row['speed']:.0f} kt",
                                   key=f"snap_{index}", width="stretch",
                                   type="primary" if index == selected else "secondary"):
                st.session_state.selected_hour = index
                st.rerun()
        if last < len(hours) - 1 and nodes[last + 1].button(
                f"Next hour ▸  \n{hours[last + 1]['time']:%H:%M}", key="simulate_next", width="stretch"):
            st.session_state.live_index = st.session_state.selected_hour = last + 1
            st.rerun()

    if result["warning"]:
        st.warning(result["warning"], icon="📣")

    _, map_time = st.columns([3, 1], vertical_alignment="bottom")
    offset = map_time.segmented_control("Map time", [0, 1, 2], default=0, key="live_offset", width="stretch",
                                        label_visibility="collapsed",
                                        format_func=lambda h: "Now" if h == 0 else f"+{h} h")
    shown = hours[min(selected + (offset or 0), len(hours) - 1)]
    render_layer_map("live_map", shown["time"].hour, height=600 if showcase else 460)

    feed = [(index, check(index)) for index in range(last, -1, -1)]
    feed = [(index, r) for index, r in feed if r["status"] != "Plan holds"]
    st.markdown("#### Strategy changes")
    if not feed:
        st.caption("No changes yet. New strategy suggestions appear here when the weather moves off plan.")
    else:
        st.markdown('<div class="lv-feed">' + "".join(
            f'<div class="lv-item {"bad" if r["status"] == "Change" else "warn"}"><span class="lv-t">'
            f'{hours[index]["time"]:%H:%M}</span><div><b>{esc(r["status"])}</b> · {esc(r["message"])}'
            + (f'<div class="la-small">{esc(r["warning"])}</div>' if r["warning"] else "") + "</div></div>"
            for index, r in feed) + "</div>", unsafe_allow_html=True)


STATUS_COLOR = {"Plan holds": "#2bd4a4", "Change coming": "#f59e0b", "Change": "#FF6600"}


def _point(bearing, radius, centre=100):
    angle = math.radians(bearing)
    return centre + radius * math.sin(angle), centre - radius * math.cos(angle)


def wind_dial(wind_from, speed, plan_sector, color):
    """Compass: cyan arc = briefing window, needle = wind now (blowing towards the centre)."""
    planned = strategy.sector_center(plan_sector)
    ticks = "".join(
        f'<line x1="{_point(b, 86)[0]:.1f}" y1="{_point(b, 86)[1]:.1f}" x2="{_point(b, 80 if b % 45 else 74)[0]:.1f}" '
        f'y2="{_point(b, 80 if b % 45 else 74)[1]:.1f}" stroke="rgba(255,255,255,{.25 if b % 45 else .6})" stroke-width="1.5"/>'
        for b in range(0, 360, 5))
    letters = "".join(f'<text x="{_point(b, 62)[0]:.1f}" y="{_point(b, 62)[1] + 4:.1f}" text-anchor="middle" '
                      f'font-size="11" fill="rgba(255,255,255,.55)">{t}</text>'
                      for b, t in ((0, "N"), (90, "E"), (180, "S"), (270, "W")))
    a, b = _point(planned - 33.75, 92), _point(planned + 33.75, 92)
    arc = (f'<path d="M{a[0]:.1f} {a[1]:.1f} A92 92 0 0 1 {b[0]:.1f} {b[1]:.1f}" fill="none" stroke="#5fd0ea" '
           'stroke-width="6" stroke-linecap="round" style="filter:drop-shadow(0 0 6px rgba(95,208,234,.7))"/>')
    tail, tip = _point(wind_from, 88), _point(wind_from, 50)
    needle = (f'<line x1="{tail[0]:.1f}" y1="{tail[1]:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" stroke="{color}" '
              f'stroke-width="4" stroke-linecap="round"/><circle cx="{tail[0]:.1f}" cy="{tail[1]:.1f}" r="6" fill="{color}"/>')
    return (f'<svg viewBox="-8 -8 216 216" class="lv-dial" role="img" aria-label="Wind {speed:.0f} kt from '
            f'{strategy.sector(wind_from)}; briefing window {plan_sector}">{ticks}{arc}{letters}{needle}'
            f'<text x="100" y="104" text-anchor="middle" font-size="34" font-weight="800" fill="#fff">{speed:.0f}</text>'
            f'<text x="100" y="124" text-anchor="middle" font-size="11" fill="rgba(255,255,255,.6)">kt · {strategy.sector(wind_from)}</text></svg>')


CONFIDENCE_COLOR = {"High": "#2bd4a4", "Medium-high": "#5fd0ea", "Medium": "#f59e0b", "Low": "#FF6600"}


def instrument_band(eyebrow, title, dial, nodes, color, tag, status, message, rule, *, show_insight=True):
    """Dark band shared by Preparation and Live: title, dial, three connected boxes, agent insight.

    nodes: three (label, value, detail) tuples; the middle one is highlighted.
    """
    boxes = [f'<div class="lv-node{" now" if i == 1 else ""}"><span>{esc(label)}</span><b>{esc(value)}</b>'
             + (f'<em>{esc(detail)}</em>' if detail else "") + "</div>"
             for i, (label, value, detail) in enumerate(nodes)]
    head = (f'<div class="lv-head"><span>{esc(eyebrow)}</span><div class="t">{esc(title)}</div></div>'
            if title else "")
    insight = (f'<div class="lv-insight"><div class="lv-tag" style="background:{color}">{esc(tag)}</div>'
               f'<div class="lv-status" style="color:{color}">● {esc(status)}</div><p>{esc(message)}</p>'
               f'<div class="lv-rule">{esc(rule)}</div></div>') if show_insight else ""
    return (f'<div class="lv-band">{dial}<div class="lv-mid">{head}'
            f'<div class="lv-path" style="--st:{color}">{"<i></i>".join(boxes)}</div>'
            f'{insight}</div></div>')


def live_band(plan, now, upcoming, result, title=None):
    """Live: brief → now → next 2 h, checked by the rule engine."""
    color = STATUS_COLOR[result["status"]]
    speeds = [row["speed"] for row in upcoming] or [now["speed"]]
    low, high = round(min(speeds)), round(max(speeds))
    brief = f'{plan["sector"]} {plan["low"]:.0f}–{plan["high"]:.0f} kt'
    return instrument_band(
        f'Live race view · {now["time"]:%d %b} · race day', title,
        wind_dial(now["dir"], now["speed"], plan["sector"], color),
        [("Brief", brief, ""),
         (f'Now · {now["time"]:%H:%M}', f'{strategy.sector(now["dir"])} {now["speed"]:.0f} kt',
          f'gusts {now["gust"]:.0f} · {strategy.sky(now["cloud"]).lower()}'),
         ("Next 2 h", f"{low}–{high} kt" if low != high else f"{low} kt", "")],
        color, "Wind agent", result["status"], result["message"], f"Rule engine v0.1 · live wind vs the brief ({brief})")


def prep_band(title):
    """Preparation: event date → weather forecast → venue, with the briefing agent's call."""
    insight, tide, brief = current_brief()
    state = st.session_state
    venue = state.venue.split(" (")[0]
    lat, lon = state.get("selected_latitude", 33.72), state.get("selected_longitude", -118.27)
    event = (f"{state.race_day:%d %b %Y}", f"{state.time_of_day} · {state.map_hour}:00 start")
    place = (venue, f"{state.boat_class} · {lat:.3f}, {lon:.3f}")
    if brief is None:
        color = "#f59e0b"
        return instrument_band(
            "Race preparation", title, wind_dial(strategy.sector_center(insight["sector"]), 0, insight["sector"], color),
            [("Event", *event), ("Weather forecast", f'{insight["sector"]} · no match', "no similar historic days"),
             ("Venue", *place)],
            color, "Briefing agent", "No forecast",
            f'No historic day had {insight["sector"]} wind at {insight["hour"]}:00. Pick another wind direction '
            "in Venue · Geoinformation.", f'{insight["total_days"]} historic days checked',
            show_insight=False)
    color = CONFIDENCE_COLOR.get(brief["confidence"], "#5fd0ea")
    answers = dict(brief["questions"])
    return instrument_band(
        "Race preparation", title,
        wind_dial(strategy.sector_center(insight["sector"]), insight["speed"], insight["sector"], color),
        [("Event", *event),
         ("Weather forecast", brief["cards"]["Wind"],
          f'gusts {insight["gust"]:.0f} · sea breeze {brief["cards"]["Sea breeze"].lower()} · {brief["cards"]["Current"].lower()}'),
         ("Venue", *place)],
        color, "Briefing agent", f'Confidence {brief["confidence"].lower()}',
        f'{answers["Which side pays, and why?"]} {answers["Where to start?"]}',
        f'Based on {insight["n_days"]} of {insight["total_days"]} historic days with {insight["sector"]} wind at {insight["hour"]}:00',
        show_insight=False)
