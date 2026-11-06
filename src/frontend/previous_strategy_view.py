"""Previous strategy: the 19 July 2026 races as a 3D space-time cube.

Horizontal plane = the course (GPS). Vertical axis = time since the start gun, so every boat is a
ribbon climbing through the cube. The "Information on the map" picker adds or removes the weather,
depth, marks and the strategy panels, from a bare track view up to a full briefing.
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import previous_strategy as ps  # noqa: E402
from backend.race_model import model as race_model  # noqa: E402

TEAL, ORANGE, GREY = (8, 127, 130), (200, 100, 44), (90, 90, 90)

# ---- the layer picker ----
L_SHADOW, L_DEPTH, L_PLANE = "Ground shadow of tracks", "Depth (bathymetry)", "Time plane"
L_MARKS, L_BOATS = "Start & first mark", "Boats at the time plane"
L_WIND_OM, L_WIND_NOAA, L_WIND_SS = "Wind · Open-Meteo", "Wind · NOAA pier", "Wind · SailSync setting"
L_COND, L_SIDE, L_DOCS = "Conditions table", "Left / right approach", "Strategy documents (synthetic)"
ALL_LAYERS = [L_SHADOW, L_DEPTH, L_PLANE, L_MARKS, L_BOATS, L_WIND_OM, L_WIND_NOAA, L_WIND_SS,
              L_COND, L_SIDE, L_DOCS]
PRESETS = {
    "Tracks only": [L_SHADOW, L_PLANE, L_BOATS],
    "+ Weather": [L_SHADOW, L_PLANE, L_BOATS, L_MARKS, L_WIND_OM, L_WIND_NOAA, L_COND],
    "Full briefing": ALL_LAYERS,
}
COLOUR_MODES = ["Finishing position", "Speed", "Side of the course"]
BOAT_FILTERS = {"All tracked boats": None, "Top 10 finishers": 10, "Top 3 finishers": 3, "Winner only": 1}

POSITION_STOPS = [(0.0, (0, 150, 136)), (0.5, (240, 180, 40)), (1.0, (200, 60, 50))]
SPEED_STOPS = [(0.0, (30, 60, 160)), (3.0, (80, 170, 200)), (5.0, (250, 200, 60)), (7.0, (220, 70, 40))]
SIDE_COLOURS = {"Left": (40, 90, 200), "Right": (230, 120, 30), "n/a": (140, 140, 140)}


# ---------- cached data ----------

@st.cache_data(show_spinner="Loading GPS tracks and race results…")
def _load():
    return ps.load_fleet_tracks(), race_model.legs()


@st.cache_data(show_spinner="Building the race…")
def _race_bundle(race_id):
    tracks, legs = _load()
    race = ps.build_race(race_id, legs, tracks)
    marks = ps.race_marks(race_id, legs, tracks)
    approaches = ps.race_approaches(race_id, legs, tracks, marks)
    return {"race": race, "marks": marks, "approaches": approaches,
            "segments": ps.segments_frame(race, approaches),
            "sailsync_wind_dir": float(legs.loc[legs["race"] == race_id, "wind_dir"].dropna().mean())
            if legs.loc[legs["race"] == race_id, "wind_dir"].notna().any() else None}


@st.cache_data(show_spinner=False)
def _conditions(race_id, station):
    bundle = _race_bundle(race_id)
    race = bundle["race"]
    start, end = race["t0"], race["t0"] + race["duration_s"]
    return ps.conditions_at((start + end) / 2, race["origin"], station, window=(start, end))


@st.cache_data(show_spinner=False)
def _depth_image(bounds):
    return ps.bathymetry_image(bounds)


# ---------- colour helpers ----------

def _ramp(values, stops):
    xs = [s[0] for s in stops]
    return np.stack([np.interp(values, xs, [s[1][c] for s in stops]) for c in range(3)], axis=1)


def _colours(frame, mode, max_position, highlight):
    """RGBA (Nx4, 0-255) for a frame with position, speed_kn, side, style, boat_id."""
    if mode == "Speed":
        rgb = _ramp(frame["speed_kn"].fillna(0).to_numpy(float), SPEED_STOPS)
        alpha = np.full(len(frame), 235.0)
    elif mode == "Side of the course":
        rgb = np.array([SIDE_COLOURS.get(s, SIDE_COLOURS["n/a"]) for s in frame["side"]], dtype=float)
        alpha = np.where(frame["style"].eq("Aggressive"), 245.0, 150.0)
    else:
        position = frame["position"].fillna(max_position).to_numpy(float)
        rgb = _ramp(np.clip((position - 1) / max(max_position - 1, 1), 0, 1), POSITION_STOPS)
        alpha = np.full(len(frame), 235.0)
    if highlight:
        alpha = np.where(frame["boat_id"].eq(highlight), 255.0, alpha * 0.3)
    return np.column_stack([rgb, alpha]).round().astype(int)


def _px(width):
    """Fixed on-screen line width.

    pydeck turns every UNQUOTED string layer argument into a deck.gl expression ("@@=..."), so
    width_units="pixels" becomes the undefined variable `pixels` and floods the canvas with giant
    strokes (verified in a browser). String literals must be quoted ("'pixels'"); the pixel
    clamps below avoid the issue altogether.
    """
    return {"get_width": 1, "width_min_pixels": width, "width_max_pixels": width}


def _mmss(seconds):
    seconds = int(round(float(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


# ---------- scene pieces ----------

def _arrow_paths(head_xy, from_deg, length_m, z, origin):
    """Shaft + two barbs of an arrow that points where the wind blows TO, ending at head_xy."""
    toward = math.radians((from_deg + 180) % 360)
    ux, uy = math.sin(toward), math.cos(toward)
    hx, hy = head_xy
    tail = (hx - ux * length_m, hy - uy * length_m)

    def barb(sign):
        angle = math.radians(25) * sign
        bx = ux * math.cos(angle) - uy * math.sin(angle)
        by = ux * math.sin(angle) + uy * math.cos(angle)
        return (hx - bx * 0.28 * length_m, hy - by * 0.28 * length_m)

    def path(*points):
        xs, ys = zip(*points)
        lng, lat = ps.to_lnglat(np.array(xs), np.array(ys), *origin)
        return [[float(a), float(b), float(z)] for a, b in zip(lng, lat)]

    return [path(tail, (hx, hy)), path((hx, hy), barb(1)), path((hx, hy), barb(-1))], tail


def _wind_layers(entries, origin, z, zoom_bounds):
    """entries: [(label, colour, from_deg, speed_kn or None)] stacked upwind (west) of the fleet."""
    min_x, mid_y = zoom_bounds["min_x"] - 120, (zoom_bounds["min_y"] + zoom_bounds["max_y"]) / 2
    paths, labels = [], []
    for k, (label, colour, from_deg, speed) in enumerate(entries):
        head = (min_x, mid_y + (k - (len(entries) - 1) / 2) * 260)
        length = (max(speed, 1.0) if speed is not None else 8.0) * 35
        shapes, tail = _arrow_paths(head, from_deg, length, z, origin)
        paths += [{"path": s, "color": [*colour, 235]} for s in shapes]
        lng, lat = ps.to_lnglat(tail[0], tail[1], *origin)
        speed_text = f"{speed:.1f} kn " if speed is not None else "speed n/a · "
        labels.append({"lng": float(lng), "lat": float(lat), "z": float(z),
                       "text": f"{label}: {speed_text}from {ps.compass(from_deg)} {from_deg:.0f} deg",
                       "r": colour[0], "g": colour[1], "b": colour[2]})
    return [
        pdk.Layer("PathLayer", data=paths, get_path="path", get_color="color",
                  **_px(3), pickable=False),
        _text_layer(labels, 13),
    ]


def _text_layer(rows, size):
    return pdk.Layer(
        "TextLayer", data=pd.DataFrame(rows), get_position="[lng, lat, z]", get_text="text",
        get_size=size, get_color="[r, g, b, 255]", pickable=False,
        get_text_anchor="'start'", get_alignment_baseline="'center'",
        background=True, get_background_color=[255, 255, 255, 215], background_padding=[4, 2],
    )


def _bounds(race):
    xs = np.concatenate([b["x"][b["valid"]] for b in race["boats"]])
    ys = np.concatenate([b["y"][b["valid"]] for b in race["boats"]])
    return {"min_x": float(xs.min()), "max_x": float(xs.max()),
            "min_y": float(ys.min()), "max_y": float(ys.max())}


@dataclass(frozen=True)
class Options:
    """What the user asked the scene to show."""

    selected: tuple
    mode: str
    boat_filter: int | None
    highlight: str | None
    now: float
    z_per_s: float
    noaa_station: str

    def has(self, layer):
        return layer in self.selected


def _corners(box, origin):
    """(west, south, east, north) of the scene, with room for the wind arrows and the time axis."""
    west, south = ps.to_lnglat(box["min_x"] - 450, box["min_y"] - 250, *origin)
    east, north = ps.to_lnglat(box["max_x"] + 250, box["max_y"] + 250, *origin)
    return float(west), float(south), float(east), float(north)


def _tooltip_columns(frame, time_column):
    frame["pos_label"] = frame["position"].map(lambda p: "n/a" if pd.isna(p) else f"P{int(p)}")
    frame["speed_label"] = frame["speed_kn"].map(lambda v: f"{v:.1f} kn")
    frame["t_label"] = frame[time_column].map(_mmss)


def _depth_layers(opts, corners):
    if not opts.has(L_DEPTH):
        return []
    depth = _depth_image(corners)
    if not depth:
        return []
    return [pdk.Layer("BitmapLayer", data=None, image=f"'{depth[0]}'", bounds=list(depth[1]),
                      opacity=0.55, pickable=False)]


def _track_layers(bundle, opts, max_position):
    frame = bundle["segments"]
    if opts.boat_filter:
        frame = frame[frame["position"].le(opts.boat_filter) & frame["position"].notna()]
    frame = frame[frame["t1"] <= opts.now].copy()
    if frame.empty:
        return []
    frame["z0"], frame["z1"] = frame["t0"] * opts.z_per_s, frame["t1"] * opts.z_per_s
    frame[["cr", "cg", "cb", "ca"]] = _colours(frame, opts.mode, max_position, opts.highlight)
    frame["line_px"] = np.where(frame["boat_id"].eq(opts.highlight), 6, np.where(frame["position"].eq(1), 4, 2))
    _tooltip_columns(frame, "t1")
    layers = []
    if opts.has(L_SHADOW):
        layers.append(pdk.Layer(
            "LineLayer", data=frame[["lng0", "lat0", "lng1", "lat1"]].round(6),
            get_source_position="[lng0, lat0, 4]", get_target_position="[lng1, lat1, 4]",
            get_color=[40, 40, 40, 60], **_px(1), pickable=False))
    keep = ["lng0", "lat0", "lng1", "lat1", "z0", "z1", "cr", "cg", "cb", "ca",
            "name", "pos_label", "speed_label", "t_label", "side"]
    for px in sorted(frame["line_px"].unique()):   # one layer per line width: winner and highlight stand out
        layers.append(pdk.Layer(
            "LineLayer", data=frame.loc[frame["line_px"] == px, keep].round(6),
            get_source_position="[lng0, lat0, z0]", get_target_position="[lng1, lat1, z1]",
            get_color="[cr, cg, cb, ca]", **_px(int(px)), pickable=True))
    return layers


def _plane_layers(opts, corners):
    if not opts.has(L_PLANE):
        return []
    west, south, east, north = corners
    z = opts.now * opts.z_per_s
    ring = [[west, south, z], [east, south, z], [east, north, z], [west, north, z]]
    return [pdk.Layer("PolygonLayer", data=[{"polygon": ring}], get_polygon="polygon",
                      get_fill_color=[*TEAL, 38], get_line_color=[*TEAL, 220],
                      line_width_min_pixels=2, stroked=True, filled=True, pickable=False)]


def _axis_layers(race, opts, corners):
    """The time axis stands on the south-west corner, ticked every minute (every two on long races)."""
    lng, lat = corners[0], corners[1]
    z_top = race["duration_s"] * opts.z_per_s
    step = 60 if race["duration_s"] <= 900 else 120
    ticks = [{"lng": lng, "lat": lat, "z": s * opts.z_per_s, "text": f" {_mmss(s)}", "r": 60, "g": 60, "b": 60}
             for s in range(0, int(race["duration_s"]) + 1, step)]
    return [pdk.Layer("PathLayer", data=[{"path": [[lng, lat, 0], [lng, lat, z_top]]}], get_path="path",
                      get_color=[60, 60, 60, 200], **_px(2), pickable=False),
            _text_layer(ticks, 12)]


def _mark_layers(bundle, opts):
    marks = bundle["marks"]
    if not opts.has(L_MARKS) or marks.empty:
        return []
    z_top = bundle["race"]["duration_s"] * opts.z_per_s
    pins = [{"path": [[float(m.lng), float(m.lat), 0], [float(m.lng), float(m.lat), z_top]]}
            for m in marks.itertuples()]
    names = {0: "Start", 1: "Mark 1"}
    tags = [{"lng": float(m.lng), "lat": float(m.lat), "z": z_top, "text": f" {names.get(int(m.mark), m.mark)}",
             "r": 90, "g": 40, "b": 140} for m in marks.itertuples()]
    return [pdk.Layer("PathLayer", data=pins, get_path="path", get_color=[90, 40, 140, 130],
                      **_px(2), pickable=False),
            _text_layer(tags, 14)]


def _boat_layers(bundle, opts, max_position):
    if not opts.has(L_BOATS):
        return []
    here = ps.positions_at(bundle["race"], opts.now)
    if opts.boat_filter:
        here = here[here["position"].le(opts.boat_filter) & here["position"].notna()]
    if here.empty:
        return []
    side = bundle["approaches"].set_index(bundle["approaches"]["boat_id"].astype(str))
    here["side"] = here["boat_id"].map(side["side"]).fillna("n/a")
    here["style"] = here["boat_id"].map(side["style"]).fillna("n/a")
    here[["cr", "cg", "cb", "ca"]] = _colours(here, opts.mode, max_position, opts.highlight)
    here["ca"] = np.where(here["finished"], here["ca"] * 0.5, here["ca"]).round().astype(int)
    here["z"] = here["t"] * opts.z_per_s
    _tooltip_columns(here, "t")
    return [pdk.Layer("ScatterplotLayer", data=here, get_position="[lng, lat, z]",
                      get_fill_color="[cr, cg, cb, ca]", get_radius=14,
                      radius_min_pixels=4, radius_max_pixels=10, pickable=True)]


def _wind_entries(bundle, opts):
    """Arrows ride on the time plane and use the wind at that moment of the race."""
    winds = ps.winds_at(bundle["race"]["t0"] + opts.now, opts.noaa_station)
    entries = []
    if opts.has(L_WIND_OM) and winds["open_meteo"]:
        entries.append(("Open-Meteo", TEAL, winds["open_meteo"]["dir"], winds["open_meteo"]["speed_kn"]))
    if opts.has(L_WIND_NOAA) and winds["noaa"]:
        name = ps.NOAA_WIND_STATIONS[opts.noaa_station][0]
        entries.append((f"NOAA {name}", ORANGE, winds["noaa"]["dir"], winds["noaa"]["speed_kn"]))
    if opts.has(L_WIND_SS) and bundle["sailsync_wind_dir"] is not None:
        entries.append(("SailSync", GREY, bundle["sailsync_wind_dir"], None))
    return entries


def _view_state(box, origin, marks):
    """Centre on the fleet and turn the map so the beat (start -> mark 1) points up the screen."""
    lng, lat = ps.to_lnglat((box["min_x"] + box["max_x"]) / 2, (box["min_y"] + box["max_y"]) / 2, *origin)
    extent = max(box["max_x"] - box["min_x"], box["max_y"] - box["min_y"]) + 700
    zoom = math.log2(156543.03 * math.cos(math.radians(origin[0])) / (extent / 650)) - 1.4
    bearing = 0.0
    if len(marks) >= 2:
        ordered = marks.sort_values("mark")
        dx, dy = ps.to_metres(ordered.iloc[1].lat, ordered.iloc[1].lng, ordered.iloc[0].lat, ordered.iloc[0].lng)
        bearing = ps.bearing_deg(float(dx), float(dy))
    return pdk.ViewState(latitude=float(lat), longitude=float(lng), zoom=float(zoom), pitch=50, bearing=float(bearing))


def _build_deck(bundle, opts):
    race = bundle["race"]
    box = _bounds(race)
    corners = _corners(box, race["origin"])
    max_position = int(max([b["position"] or 0 for b in race["boats"]] + [1]))
    layers = [
        *_depth_layers(opts, corners),
        *_track_layers(bundle, opts, max_position),
        *_plane_layers(opts, corners),
        *_axis_layers(race, opts, corners),
        *_mark_layers(bundle, opts),
        *_boat_layers(bundle, opts, max_position),
    ]
    entries = _wind_entries(bundle, opts)
    if entries:
        layers += _wind_layers(entries, race["origin"], opts.now * opts.z_per_s, box)
    return pdk.Deck(
        layers=layers, map_style="light",
        initial_view_state=_view_state(box, race["origin"], bundle["marks"]),
        tooltip={"html": "<b>{name}</b><br/>{pos_label} · {speed_label} · {t_label}<br/>side: {side}",
                 "style": {"fontSize": "12px"}},
    )


# ---------- panels ----------

def _fmt(value, unit="", digits=1):
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def _conditions_panel(race_ids, labels, station):
    st.subheader("Conditions")
    rows = []
    for rid in race_ids:
        c = _conditions(rid, station)
        for key, name in (("open_meteo", "Open-Meteo"), ("noaa", "NOAA pier")):
            w = c[key]
            if w:
                rows.append({"Race": labels[rid], "Source": name, "Wind kn": f"{w['speed_kn']:.1f}",
                             "From": f"{ps.compass(w['dir'])} {w['dir']:.0f}°", "Gust kn": _fmt(w["gust_kn"]),
                             "2 h change kn": _fmt(w["rise_2h_kn"]), "Where": w["source"]})
        if c["waves"]:
            rows.append({"Race": labels[rid], "Source": "Waves (buoy)", "Wind kn": "", "From": "",
                         "Gust kn": "", "2 h change kn": "",
                         "Where": f"{c['waves']['height_m']:.2f} m, {_fmt(c['waves']['period_s'], ' s')} · {c['waves']['source']}"})
        tide = c["tide"]
        rows.append({"Race": labels[rid], "Source": "Tide", "Wind kn": "", "From": "", "Gust kn": "",
                     "2 h change kn": "",
                     "Where": f"{tide['state']}, next turn {'n/a' if tide['turns'] is None else format(tide['turns'], '%H:%M')}"
                              + (" · turns during the race" if tide["turns_in_race"] else "") + f" · {tide['source']}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=35 * len(rows) + 40)
    st.caption("Every source is 8-11 km from the course and hourly or 10-minute, so these are regional "
               "values, not a wind field over the race area. SailSync's own wind has a direction only.")


def _side_panel(bundle):
    st.subheader("Left / right approach (best 10 tracked boats)")
    app = bundle["approaches"].copy()
    positions = {b["boat_id"]: b["position"] for b in bundle["race"]["boats"]}
    names = {b["boat_id"]: b["name"] for b in bundle["race"]["boats"]}
    app["boat_id"] = app["boat_id"].astype(str)
    app["position"] = app["boat_id"].map(positions)
    app["Boat"] = app["boat_id"].map(names)
    app = app.dropna(subset=["position"]).sort_values("position")
    top = app[app["position"] <= 10]
    c1, c2 = st.columns(2)
    c1.metric("Finishers 1-10 on the right (tracked)", f"{int((top['side'] == 'Right').sum())} of {len(top)}")
    c2.metric("Whole tracked fleet on the right", f"{int((app['side'] == 'Right').sum())} of {len(app)}")
    shown = app.head(10).assign(  # the 10 best-placed boats that have GPS
        Position=lambda d: d["position"].astype(int),
        Side=lambda d: d["side"], Style=lambda d: d["style"],
        **{"Furthest off the line": lambda d: (d["offset"].abs() * 100).round(0).astype(int).astype(str) + " % of the leg"},
    )[["Position", "Boat", "Side", "Style", "Furthest off the line"]]
    st.dataframe(shown, hide_index=True, width="stretch")
    st.caption("Side = which side of the straight start→mark line each boat sailed furthest from, looking "
               "up the beat. Aggressive = furthest point ≥ 25 % of the leg length off the line "
               "(backend/race_model/model.py).")


def _docs_panel(rid, labels, station):
    st.subheader("Strategy documents triggered by these conditions")
    st.warning("The documents are synthetic (`synthetic: true` in the corpus front matter). They show what the team's "
               "rules would have said, not what worked.", icon="⚠️")
    choice = st.radio("Wind used for the trigger rules", ["NOAA pier (observed)", "Open-Meteo (model)"],
                      horizontal=True, key="ps_trigger_source")
    source = "noaa" if choice.startswith("NOAA") else "open_meteo"
    result = ps.strategy_documents(_conditions(rid, station), source)
    st.caption(f"{labels[rid]} · inputs: " + ", ".join(f"{k} = {v}" for k, v in result["inputs"].items()))
    for doc in result["selected"]:
        with st.expander(f"{doc['id']} · {doc['title']}  —  {doc['reason']}", expanded=doc["id"] in ("TS-02", "TS-07", "TS-04", "TS-03")):
            if doc["core"]:
                st.markdown("**Core idea**  \n" + doc["core"])
            if doc["upwind"]:
                st.markdown("**Upwind**  \n" + doc["upwind"])
    st.caption("Not provided to the rules, so rules that need them cannot fire: " + ", ".join(result["missing"]) + ". "
               "TS-02's reason text says 'no rain, current < 0.5 kt' although neither was measured - "
               "the rule treats a missing value as passing.")


# ---------- the view ----------

def _apply_preset():
    st.session_state["ps_layers"] = list(PRESETS[st.session_state["ps_preset"]])


def render_previous_strategy():
    st.header("Previous strategy")
    st.caption("19 July 2026 · San Pedro OCR · ILCA 7 · first upwind leg of three races. "
               "Height = time since the start gun, so each boat is a ribbon climbing through the cube. "
               "Drag to rotate, scroll to zoom, hover a ribbon for the boat.")
    tracks, legs = _load()
    race_ids = ps.race_ids(legs)
    labels = {rid: ps.race_label(legs, rid) for rid in race_ids}

    st.session_state.setdefault("ps_layers", list(PRESETS["+ Weather"]))
    st.session_state.setdefault("ps_preset", "+ Weather")

    top = st.columns([1.2, 1.3, 1.2, 1.4])
    rid = top[0].selectbox("Race", race_ids, format_func=labels.get, key="ps_race")
    mode = top[1].radio("Colour by", COLOUR_MODES, key="ps_colour", horizontal=False)
    boat_filter_label = top[2].selectbox("Boats", list(BOAT_FILTERS), key="ps_boats")
    boat_filter = BOAT_FILTERS[boat_filter_label]

    bundle = _race_bundle(rid)
    race = bundle["race"]
    boat_names = {b["boat_id"]: b["name"] for b in race["boats"]}
    pick = top[3].selectbox("Highlight a boat", ["—", *boat_names.values()], key="ps_highlight")
    highlight = next((k for k, v in boat_names.items() if v == pick), None)

    st.radio("Information on the map", list(PRESETS), key="ps_preset", horizontal=True,
             on_change=_apply_preset,
             help="A preset fills the box below; add or remove single items to make your own mix.")
    selected = st.multiselect("Layers", ALL_LAYERS, key="ps_layers", label_visibility="collapsed")

    controls = st.columns([3, 1.2, 1.2])
    duration = int(race["duration_s"])
    now = controls[0].slider("Race clock (seconds after the start gun)", 0, duration, duration, step=ps.STEP_S,
                             key=f"ps_now_{rid}", format="%d s")
    z_per_s = controls[1].slider("Time stretch (m per s)", 0.25, 4.0, 1.0, 0.25, key="ps_stretch")
    noaa_station = controls[2].selectbox(
        "NOAA wind pier", list(ps.NOAA_WIND_STATIONS), key="ps_station",
        format_func=lambda s: f"{ps.NOAA_WIND_STATIONS[s][0]} ({s})")

    deck = _build_deck(bundle, Options(tuple(selected), mode, boat_filter, highlight, float(now),
                                       float(z_per_s), noaa_station))
    st.pydeck_chart(deck, height=640)

    legend = {"Finishing position": "teal = first → amber → red = last of the tracked boats",
              "Speed": "blue = slow → yellow → red = 7 kn+ (smoothed over 30 s)",
              "Side of the course": "blue = left of the straight line, orange = right; "
                                    "strong colour = aggressive, faded = conservative"}[mode]
    st.caption(f"Colour: {legend}. Wide ribbon = race winner. The teal plane is the race clock.")

    coverage = np.array([b["valid"].mean() for b in race["boats"]])
    note = (f"GPS for {race['tracked']} of {race['in_race']} boats in this race. On the tracked boats the "
            f"leg is covered {coverage.mean():.0%} of the time on average (lowest {coverage.min():.0%}); "
            "holes in a track stay holes and are not bridged.")
    if race["truncated"]:
        names = ", ".join(boat_names.get(b, b) for b in race["truncated"])
        note += (f" Cut at {race['cap_s']:.0f} s (1.5 × the median leg) to keep the time axis readable: {names}.")
    st.caption(note)

    if L_COND in selected:
        _conditions_panel(race_ids, labels, noaa_station)
    if L_SIDE in selected:
        _side_panel(bundle)
    if L_DOCS in selected:
        _docs_panel(rid, labels, noaa_station)
