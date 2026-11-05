"""Location Agent views: Coach file, Venue map, Venue rules, Coach brief,
Sailor brief, Strategy overview and Live."""

import datetime as dt
import html
import math
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import analysis, race_analysis, strategy  # noqa: E402
from backend.analysis import tagging  # noqa: E402

TEAL, INK, ORANGE = "#087f82", "#071c2c", "#c8642c"

AGENT_VIEWS = {
    "coach": "Coach file",
    "venue": "Venue map",
    "rules": "Venue rules",
    "coach_brief": "Coach brief",
    "sailor_brief": "Sailor brief",
    "overview": "Strategy overview",
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
.la-flow {{ display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 14px; }}
.la-flow div {{ background:#fff7c9; border:1px solid #eadf8f; border-radius:6px; padding:8px 10px; font-size:.85rem; }}
.la-flow div.done {{ background:#dff1e4; border-color:#b5dcbf; }}
</style>
"""


# ---------- state ----------

DEFAULTS = {
    "venue": list(strategy.VENUES)[0], "race_day": dt.date(2026, 6, 15), "time_of_day": "Midday",
    "wind_sector": "SSW", "map_hour": 13, "layers": ["Wind", "Pressure", "Terrain effects"],
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
    for key in ("wind_sector", "map_hour", "time_of_day"):
        if st.session_state[key] is None:
            st.session_state[key] = st.session_state.get(f"_prev_{key}", DEFAULTS[key])
        st.session_state[f"_prev_{key}"] = st.session_state[key]
    if st.session_state.get("_last_tod") != st.session_state.time_of_day:
        st.session_state.map_hour = strategy.TIME_OF_DAY[st.session_state.time_of_day]
        st.session_state._last_tod = st.session_state.time_of_day
    st.session_state.setdefault("uploaded", {})
    st.session_state.setdefault("pasted", [])
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


def documents():
    uploaded = list(st.session_state.uploaded.values())
    return (uploaded or demo_documents()) + st.session_state.pasted


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
                st.session_state.uploaded[upload.name] = analyse_upload(upload.name, upload.getvalue())
            st.rerun()  # closes the dialog
    with transcript_tab:
        title = st.text_input("Title", value="Debrief transcript", key="paste_title")
        text = st.text_area("Transcript (plain text, VTT or SRT)", height=180, key="paste_text",
                            placeholder="Coach: How did the first beat go?\nSailor: Right paid after 12:00.")
        if st.button("Add transcript", type="primary", disabled=not text.strip(), width="stretch"):
            st.session_state.pasted.append(analysis.analyse_pasted_transcript(title, text))
            st.rerun()


def render_coach_file():
    st.header("Coach file")
    st.caption("Upload your own files. Each one is mapped to the common venue model, read by the right "
               "capability (text, picture of text, transcript) and tagged by topic.")
    left, right = st.columns([1.7, 1], gap="large")

    with left, st.container(border=True):
        title, upload_col = st.columns([2, 1])
        title.markdown("#### Coach files")
        if upload_col.button("⬆ Upload", type="primary", width="stretch"):
            upload_dialog()
        if st.session_state.uploaded:
            st.button("Clear uploads · back to demo set",
                      on_click=lambda: st.session_state.uploaded.clear())
        else:
            st.caption("Showing the demo file set (sample texts marked DEMO SAMPLE). "
                       "Press **Upload** to add your own files.")
        for doc in documents():
            status = ('<span class="la-bad">Not read</span>' if doc["error"] else
                      '<span class="la-ok">Mapped</span>')
            st.markdown(
                f'<div class="la-row"><div><span class="la-badge">{esc(doc["badge"])}</span>{esc(doc["name"])}'
                f'</div><div class="la-small">→ {esc(doc["entity"] or "Unknown type")} · '
                f'{esc(doc["method"] or doc["capability"] or "")} &nbsp; {status}</div></div>',
                unsafe_allow_html=True)
            if doc["error"]:
                st.caption(f"⚠️ {doc['error']}")

    with right, st.container(border=True):
        st.markdown("#### Venue & event")
        st.selectbox("Venue", list(strategy.VENUES), key="venue", on_change=use_venue_coordinates)
        spot = strategy.VENUES[st.session_state.venue]
        st.caption(f"Course centre {spot['lat']:.3f}° N, {abs(spot['lon']):.3f}° W "
                   f"(`{spot['area']}`). Applied to the map and point chart.")
        st.selectbox("Class", spot["classes"], key="boat_class",
                     help="Demo focuses on one class; the list stays open for the demo.")
        st.date_input("Race day", key="race_day", min_value=dt.date(2026, 6, 1),
                      max_value=dt.date(2026, 6, 30),
                      help="Hackathon mode: June 2026 is replayed as if live.")
        st.segmented_control("Time of day", list(strategy.TIME_OF_DAY), key="time_of_day")
        st.markdown('<div class="la-stat la-small">Public data joined automatically: Open-Meteo wind & '
                    'cloud (June 2021–2025) · NOAA tides · NCEI bathymetry & terrain · SailSync race tracks'
                    '</div>', unsafe_allow_html=True)
        st.write("")
        st.button("Analyse venue →", type="primary", width="stretch", on_click=go, args=("venue",))

    st.subheader("What the coach can upload")
    rows = analysis.checklist(documents())
    st.dataframe(
        [{"": "✅" if row["provided"] else ("❗" if row["required"] else "○"), "Upload": row["item"],
          "Formats": row["formats"], "Read by": row["capability"], "Used in": row["used_in"]}
         for row in rows],
        hide_index=True, width="stretch")
    st.caption("Everything is optional except the sailing instructions; without uploads the agent "
               "works from public data only.")

    tagged = [doc for doc in documents() if doc["tags"]]
    if tagged:
        st.subheader("What the agent read")
        for doc in tagged:
            with st.expander(f"{doc['name']} — {', '.join(doc['tags'])}"):
                for topic, lines in doc["tags"].items():
                    st.markdown(f"**{topic}**")
                    for line in lines[:4]:
                        st.markdown(f"- {line}")


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


def render_venue_map(render_live_overlay):
    st.header("Venue map")
    c1, c2, c3 = st.columns([1.2, 1.2, 2.2])
    c1.segmented_control("Wind direction", strategy.SECTORS, key="wind_sector")
    c2.segmented_control("Time of day", [11, 13, 15], key="map_hour", format_func=lambda h: f"{h}:00")
    c3.pills("Layers", ["Wind", "Pressure", "Terrain effects", "Current"], selection_mode="multi", key="layers")
    insight, tide = current_insight()
    if insight["n_days"] == 0:
        st.warning(f"No June day in 2021–2025 had {insight['sector']} wind at {insight['hour']}:00. "
                   "Pick another direction or hour.")
    else:
        left, right = st.columns([2, 1], gap="medium")
        with left:
            st.markdown(venue_svg(strategy.sector_center(insight["sector"]), insight["speed"], insight["side"],
                                  st.session_state.layers, tide["state"], insight["veer_rate"]),
                        unsafe_allow_html=True)
            st.caption("Schematic course area; arrows, pressure band and why-panel are computed from the data.")
        with right:
            insight_panel(insight, tide, f"Typical at {insight['hour']}:00 · from {insight['sector']}")
            st.markdown(f'<div class="la-card la-small">Based on {insight["n_days"]} historic days '
                        f'(of {insight["total_days"]}) with similar wind + your uploaded logs.</div>',
                        unsafe_allow_html=True)
            st.button("Generate coach brief →", type="primary", width="stretch",
                      on_click=go, args=("coach_brief",))

    st.subheader("Live data overlay")
    st.caption("Open-Meteo marine model over the venue: currents, waves, swell, temperature or sea level.")
    render_live_overlay()


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
        st.warning("Pick a wind direction and hour with historic data on the Venue map first.")
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


def render_sailor_brief():
    insight, tide, brief = current_brief()
    st.header("Sailor brief")
    st.caption(context_line())
    if brief is None:
        st.warning("Pick a wind direction and hour with historic data on the Venue map first.")
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
        st.warning("Pick a wind direction and hour with historic data on the Venue map first.")
        return

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


# ---------- 7. Live ----------

def render_live():
    st.header("Live strategy check")
    _, tide, brief = current_brief()
    plan = st.session_state.get("plan")
    if brief is None or not plan:
        st.warning("The briefing needs a valid wind direction and hour on the Venue map first.")
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
                "Hackathon mode: replaying June 2026 data as if live.")
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

        view_col, map_col = st.columns([1, 2.2])
        with view_col:
            offset = st.segmented_control("Map time", [0, 1, 2], default=0, key="live_offset",
                                          format_func=lambda h: "T0" if h == 0 else f"T+{h}")
            shown = hours[min(selected + (offset or 0), len(hours) - 1)]
            st.markdown(f'<div class="la-dark"><div class="la-small">{shown["time"]:%H:%M} · from '
                        f'{strategy.sector(shown["dir"])}</div><div class="big">{shown["speed"]:.0f} kt</div>'
                        f'Gusts {shown["gust"]:.0f} kt</div>', unsafe_allow_html=True)
        map_col.markdown(venue_svg(shown["dir"], shown["speed"], plan["side"],
                                   ["Wind", "Pressure", "Terrain effects"], tide["state"]), unsafe_allow_html=True)

        st.markdown("#### Insight notifications")
        feed = [(index, check(index)) for index in range(last, -1, -1)]
        feed = [(index, r) for index, r in feed if r["status"] != "Plan holds"]
        if not feed:
            st.caption("No changes yet. New strategy suggestions appear here when the weather moves off plan.")
        for index, r in feed:
            st.info(f"**{hours[index]['time']:%H:%M}** — {r['message']}"
                    + (f"\n\n{r['warning']}" if r["warning"] else ""),
                    icon="🔁" if r["status"] == "Change" else "⏰")
