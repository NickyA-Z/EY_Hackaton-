"""Location Agent front end v0.1: Upload -> Venue map -> Briefing -> Live."""

import datetime as dt
import html
import math
import sys
from pathlib import Path

import requests
import streamlit as st

import engine

# shortcut: imports the sea dashboard by path, upgrade to a package when the repo gets one.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sea_dashboard"))
from current_map import render_current_map  # noqa: E402
from marine_api import get_map_grid  # noqa: E402

STEPS = ["1 Upload", "2 Venue map", "3 Briefing", "4 Live"]
NAVY, ORANGE = "#13294b", "#d4703a"

CSS = f"""
<style>
.block-container {{ padding-top: 1.2rem; max-width: 1280px; }}
header[data-testid="stHeader"] {{ display: none; }}
.la-bar {{ background:{NAVY}; color:#fff; border-radius:10px; padding:14px 22px; display:flex;
  justify-content:space-between; align-items:center; margin-bottom:10px; }}
.la-bar b {{ font-size:1.15rem; }}
.la-bar span {{ font-size:.9rem; opacity:.9; }}
.la-card {{ background:#fff; border:1px solid #e3e7ec; border-radius:12px; padding:16px 18px; margin-bottom:12px; }}
.la-dark {{ background:{NAVY}; color:#fff; border-radius:12px; padding:16px 18px; margin-bottom:12px; }}
.la-dark .big {{ font-size:2.2rem; font-weight:800; line-height:1.1; margin:4px 0 8px; }}
.la-small {{ font-size:.82rem; color:#5b6773; }}
.la-dark .la-small {{ color:#c9d3df; }}
.la-stat {{ background:#f1f3f6; border-radius:10px; padding:10px 14px; }}
.la-stat .v {{ font-size:1.35rem; font-weight:800; color:{NAVY}; }}
.la-row {{ display:flex; justify-content:space-between; align-items:center; border:1px solid #e3e7ec;
  border-radius:8px; padding:9px 12px; margin:6px 0; background:#fff; }}
.la-badge {{ background:{NAVY}; color:#fff; font:700 11px ui-monospace,monospace; padding:3px 6px;
  border-radius:4px; margin-right:10px; }}
.la-ok {{ background:#e3f3e6; color:#2f7a3e; font-weight:600; font-size:.8rem; padding:3px 8px; border-radius:5px; }}
.la-warn {{ background:#fdeee3; color:#a4511c; font-weight:600; font-size:.8rem; padding:3px 8px; border-radius:5px; }}
.la-bad {{ background:#fbe3e3; color:#a42020; font-weight:600; font-size:.8rem; padding:3px 8px; border-radius:5px; }}
.la-q {{ display:flex; gap:14px; padding:12px 0; border-bottom:1px solid #eceff3; }}
.la-q .n {{ background:{NAVY}; color:#fff; border-radius:50%; min-width:30px; height:30px; display:flex;
  align-items:center; justify-content:center; font-weight:700; }}
.la-q .t {{ font-size:.8rem; color:#5b6773; font-weight:600; }}
.la-why td {{ padding:6px 8px 6px 0; vertical-align:top; font-size:.9rem; }}
.la-why td:first-child {{ color:#2a5caa; font-weight:700; white-space:nowrap; }}
</style>
"""


# ---------- data (cached, local files) ----------

@st.cache_data
def history():
    return engine.load_wind(engine.HISTORY_YEARS)


@st.cache_data
def live_data():
    return engine.load_wind([engine.LIVE_YEAR])


@st.cache_data
def tides():
    return engine.load_tides()


def go(step):
    st.session_state.step = step


def esc(text):
    return html.escape(str(text))


# ---------- venue map drawing ----------

def arrow(x, y, toward_deg, length, color=NAVY, width=3):
    rad = math.radians(toward_deg)
    dx, dy = math.sin(rad) * length, -math.cos(rad) * length
    x0, y0, x1, y1 = x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2
    head = 9
    left = (x1 - head * math.sin(rad - 0.45), y1 + head * math.cos(rad - 0.45))
    right = (x1 - head * math.sin(rad + 0.45), y1 + head * math.cos(rad + 0.45))
    return (f'<line x1="{x0:.0f}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y1:.0f}" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round"/>'
            f'<polygon points="{x1:.0f},{y1:.0f} {left[0]:.0f},{left[1]:.0f} {right[0]:.0f},{right[1]:.0f}" fill="{color}"/>')


def venue_svg(wind_from, speed, side, layers, tide_state, veer_rate=0.0):
    toward = (wind_from + 180) % 360
    length = 30 + min(speed, 25) * 3
    parts = [
        '<svg viewBox="0 0 860 560" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Venue map, wind from {wind_from:.0f} degrees at {speed:.0f} knots" '
        'style="width:100%;border-radius:10px;font-family:Inter,system-ui,sans-serif">',
        '<rect width="860" height="560" fill="#dce8f3"/>',
        '<path d="M0 0 H860 V140 C760 170 640 125 520 160 C400 195 250 150 0 190 Z" fill="#e6e1d6"/>',
    ]
    if "Terrain effects" in layers:
        parts.append('<path d="M0 0 H280 V80 L130 150 L0 165 Z" fill="#cfc4ad"/>')
    parts += [
        '<text x="50" y="70" font-size="17" fill="#4a4a4a">Hills (Palos Verdes)</text>',
        '<text x="560" y="70" font-size="17" fill="#4a4a4a">Port / city</text>',
        '<line x1="400" y1="185" x2="790" y2="185" stroke="#6b6b6b" stroke-width="7" stroke-linecap="round"/>',
        '<text x="550" y="212" font-size="15" fill="#4a4a4a">Breakwater</text>',
    ]
    if "Pressure" in layers:
        band_x = {"Right": 430, "Left": 70, "Middle": 250}[side]
        parts.append(f'<rect x="{band_x}" y="225" width="360" height="70" rx="12" fill="#5a83b3" opacity=".85"/>'
                     f'<text x="{band_x + 16}" y="252" font-size="15" font-weight="700" fill="#fff">'
                     f'Pressure band + {max(1, round(speed * 0.2))} kt</text>')
    if "Current" in layers:
        flow = 0 if tide_state == "Flood" else 180  # flood sets into the harbour (north)
        for x in (110, 330, 560, 780):
            parts.append(arrow(x, 500, flow, 40, color="#1b8f8a", width=2))
        parts.append(f'<text x="20" y="545" font-size="13" fill="#1b8f8a">{tide_state} tide current</text>')
    parts += [
        '<rect x="200" y="310" width="480" height="210" fill="none" stroke="#1f1f1f" stroke-width="2" stroke-dasharray="8 6"/>',
        '<text x="210" y="510" font-size="14" fill="#1f1f1f">Course area A</text>',
        '<circle cx="280" cy="380" r="9" fill="#d4703a"/><text x="262" y="405" font-size="13">Mark 1</text>',
        '<line x1="610" y1="360" x2="610" y2="480" stroke="#d4703a" stroke-width="3"/>'
        '<text x="575" y="500" font-size="13">Start line</text>',
        '<circle cx="790" cy="470" r="27" fill="#fff" stroke="#1f1f1f" stroke-width="1.5"/>'
        '<text x="783" y="462" font-size="13" font-weight="700">N</text>'
        '<line x1="790" y1="466" x2="790" y2="488" stroke="#1f1f1f" stroke-width="2"/>',
    ]
    if "Wind" in layers:
        for x, y in [(150, 410), (330, 360), (470, 360), (330, 460), (470, 460), (620, 330), (740, 400)]:
            bend = veer_rate * 2 if ("Terrain effects" in layers and x > 560) else 0
            boost = 1.15 if ("Terrain effects" in layers and x > 560) else 1
            parts.append(arrow(x, y, toward + bend, length * boost))
    parts.append("</svg>")
    return "".join(parts)


def why_rows(insight, tide):
    rate = insight["veer_rate"]
    turn = f"{'veering right' if rate > 0 else 'backing left'} ~{abs(rate):.0f}° per hour"
    onset = f"{insight['onset_hour']}:00" if insight["onset_hour"] is not None else "—"
    turns = f" until about {tide['turns']:%H:%M}" if tide["turns"] is not None else ""
    return [
        ("Sea breeze", f"Thermal breeze in by ~{onset}, {turn}."),
        ("Terrain", "Palos Verdes blocks the left; the coast bends the breeze so there is "
                    "more wind near the breakwater (right side)."),
        ("Current", f"{tide['state']} tide{turns}; "
                    f"{'sets toward the harbour mouth' if tide['state'] == 'Flood' else 'runs out of the harbour'}."),
        ("History", f"The wind kept turning {insight['side'].lower()} on {insight['kept_turning']} "
                    f"of {insight['n_days']} similar days."
         if insight["side"] != "Middle" else f"No consistent trend over {insight['n_days']} similar days."),
    ]


def insight_panel(insight, tide, label):
    st.markdown(
        f'<div class="la-dark"><div class="la-small">{esc(label)}</div>'
        f'<div class="big">{insight["speed"]:.0f} kt</div>'
        f'Favoured side: <b>{esc(insight["side"])}'
        f'{" (towards breakwater)" if insight["side"] == "Right" else ""}</b><br>'
        f'Shifts: <b>{esc(insight["shift"])} + ~{insight["swing"]:.0f}° oscillations</b></div>',
        unsafe_allow_html=True)
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in why_rows(insight, tide))
    st.markdown(f'<div class="la-card"><b>Why?</b><table class="la-why">{rows}</table></div>',
                unsafe_allow_html=True)


# ---------- pages ----------

def page_upload():
    st.markdown("## New venue analysis")
    st.caption("Drop your own files. We map each one to the common venue model and join it "
               "with public weather, tide and terrain data.")
    left, right = st.columns([1.7, 1], gap="large")

    with left, st.container(border=True):
        st.markdown("#### Coach files")
        uploads = st.file_uploader(
            "Drop files or browse", accept_multiple_files=True,
            type=[ext.lstrip(".") for ext in engine.FILE_TYPES],
            help="CSV · Excel · GPX / tracker exports · wind logs · photos & drawings · text debriefs")
        names = [upload.name for upload in uploads] or engine.DEMO_FILES
        if not uploads:
            st.caption("Showing the demo file set. Drop your own files to replace it.")
        st.session_state.files = names
        for name in names:
            badge, entity = engine.map_file(name)
            status = ('<span class="la-ok">Mapped</span>' if entity
                      else '<span class="la-warn">Needs review</span>')
            st.markdown(
                f'<div class="la-row"><div><span class="la-badge">{esc(badge)}</span>{esc(name)}</div>'
                f'<div>→ {esc(entity or "Unknown type")} &nbsp; {status}</div></div>',
                unsafe_allow_html=True)
        st.caption("wind_log files are joined with historic data from the year before the event.")

    with right, st.container(border=True):
        st.markdown("#### Venue & event")
        venue = st.selectbox("Venue", list(engine.VENUES), key="venue")
        spot = engine.VENUES[venue]
        st.caption(f"Course centre: {spot['lat']:.3f}° N, {abs(spot['lon']):.3f}° W "
                   f"(area `{spot['area']}`)")
        st.selectbox("Class", spot["classes"], key="boat_class",
                     help="Demo focuses on one class; the list stays open for the demo.")
        st.date_input("Race day", key="race_day",
                      min_value=dt.date(2026, 6, 1), max_value=dt.date(2026, 6, 30),
                      help="Hackathon mode: June 2026 is replayed as if it were live.")
        st.segmented_control("Time of day", list(engine.TIME_OF_DAY), key="time_of_day")
        st.markdown(
            '<div class="la-stat la-small">Public data joined automatically: Open-Meteo wind & '
            'cloud cover (June 2021–2025) · NOAA tide predictions · NCEI bathymetry & terrain · '
            'event results</div>', unsafe_allow_html=True)
        st.write("")
        st.button("Analyse venue →", type="primary", width="stretch", on_click=go, args=(STEPS[1],))


def current_insight():
    hour = st.session_state.map_hour
    insight = engine.venue_insight(history(), st.session_state.wind_sector, hour)
    when = dt.datetime.combine(st.session_state.race_day, dt.time(hour))
    return insight, engine.tide_state(tides(), when)


def page_venue_map():
    c1, c2, c3 = st.columns([1.2, 1.2, 2.2])
    c1.segmented_control("Wind direction", engine.SECTORS, key="wind_sector")
    c2.segmented_control("Time of day", [11, 13, 15], key="map_hour", format_func=lambda h: f"{h}:00")
    c3.pills("Layers", ["Wind", "Pressure", "Terrain effects", "Current"],
             selection_mode="multi", key="layers")
    insight, tide = current_insight()
    left, right = st.columns([2, 1], gap="medium")

    if insight["n_days"] == 0:
        left.warning(f"No June day in 2021–2025 had {insight['sector']} wind at "
                     f"{insight['hour']}:00. Pick another direction or hour.")
        return
    with left:
        st.markdown(venue_svg(engine.sector_center(insight["sector"]), insight["speed"],
                              insight["side"], st.session_state.layers, tide["state"],
                              insight["veer_rate"]), unsafe_allow_html=True)
        st.caption("Schematic course area; arrows, pressure band and why-panel are computed from the data.")
    with right:
        insight_panel(insight, tide, f"Typical at {insight['hour']}:00 · from {insight['sector']}")
        st.markdown(f'<div class="la-card la-small">Based on {insight["n_days"]} historic days '
                    f'(of {insight["total_days"]}) with similar wind + your uploaded logs and '
                    'race results.</div>', unsafe_allow_html=True)
        st.button("Generate strategy briefing →", type="primary", width="stretch",
                  on_click=go, args=(STEPS[2],))

    with st.expander("Ocean current field (Open-Meteo marine model, loads on demand)"):
        if st.toggle("Load current field for race day", key="load_currents"):
            spot = engine.VENUES[st.session_state.venue]
            try:
                with st.spinner("Building the regional current field…"):
                    render_current_map(get_map_grid(spot["lat"], spot["lon"],
                                                    st.session_state.race_day, "Ocean currents"))
            except (requests.exceptions.RequestException, KeyError, ValueError) as error:
                st.error(f"Could not load the current field: {error}")


def answers(brief):
    """The four answers, with the coach's edits applied."""
    edits = st.session_state.setdefault("edits", {})
    return [(q, edits.get(q, a)) for q, a in brief["questions"]]


def briefing_text(brief, sailor=False):
    header = (f"Race-day briefing — {st.session_state.venue} · {st.session_state.race_day:%d %b %Y} · "
              f"{st.session_state.boat_class}")
    lines = [header, ""]
    if not sailor:
        lines += [f"{k}: {v}" for k, v in brief["cards"].items()] + [""]
    lines += [f"{i}. {q}\n   {a}" if not sailor else f"{i}. {a}"
              for i, (q, a) in enumerate(answers(brief), 1)]
    if not sailor:
        lines += ["", "Challenger AI:"] + [f"- {f} → {a}" for f, a in brief["challenger"]]
        lines += [f"Plan confidence: {brief['confidence']}"]
    return "\n".join(lines)


def page_briefing():
    insight, tide = current_insight()
    if insight["n_days"] == 0:
        st.warning("Pick a wind direction and hour with historic data on the venue map first.")
        return
    brief = engine.briefing(insight, tide, st.session_state.boat_class)
    st.session_state.plan = {"sector": insight["sector"], "low": insight["speed_low"],
                             "high": insight["speed_high"], "side": insight["side"]}

    top, view = st.columns([3, 1])
    top.markdown("## Race-day briefing")
    top.caption("Drafted from the venue map, the historic data and your files. Ready for the 08:00 team briefing.")
    mode = view.segmented_control("View", ["Coach view", "Sailor view"], key="brief_view",
                                  label_visibility="hidden")
    left, right = st.columns([2, 1], gap="medium")

    with left, st.container(border=True):
        if mode == "Coach view":
            for column, (label, value) in zip(st.columns(3), brief["cards"].items()):
                column.markdown(f'<div class="la-stat"><div class="la-small">{esc(label)}</div>'
                                f'<div class="v">{esc(value)}</div></div>', unsafe_allow_html=True)
        editing = st.session_state.get("editing", False)
        for number, (question, answer) in enumerate(answers(brief), 1):
            if editing:
                new = st.text_area(question, answer, key=f"edit_{number}")
                st.session_state.edits[question] = new
            else:
                title = "" if mode == "Sailor view" else f'<div class="t">{esc(question)}</div>'
                st.markdown(f'<div class="la-q"><div class="n">{number}</div><div>{title}'
                            f'{esc(answer)}</div></div>', unsafe_allow_html=True)
        b1, b2, b3, _ = st.columns([1, 1.2, 0.8, 1.6])
        b1.download_button("Export", briefing_text(brief), on_click="ignore",
                           file_name=f"briefing_{st.session_state.race_day}.txt", type="primary")
        b2.download_button("Share with sailors", briefing_text(brief, sailor=True), on_click="ignore",
                           file_name=f"sailor_briefing_{st.session_state.race_day}.txt")
        if b3.button("Done" if editing else "Edit"):
            st.session_state.editing = not editing
            st.rerun()

    with right:
        with st.container(border=True):
            st.markdown('#### Challenger AI <span class="la-warn">Tries to disprove the plan</span>',
                        unsafe_allow_html=True)
            for finding, action in brief["challenger"]:
                st.markdown(f'<div class="la-card">{esc(finding)}<br>'
                            f'<b style="color:{ORANGE if "risk" in action or "Check" in action else "#2f7a3e"}">'
                            f'{esc(action)}</b></div>', unsafe_allow_html=True)
            st.markdown(f"Plan confidence: **{brief['confidence']}**")
        st.button("Start live monitoring →", type="primary", width="stretch",
                  on_click=go, args=(STEPS[3],))


def page_live():
    plan = st.session_state.get("plan")
    if not plan:
        st.warning("Generate the briefing first, so live data has a plan to compare with.")
        st.button("Go to briefing", on_click=go, args=(STEPS[2],))
        return
    day = live_data()[live_data()["date"] == st.session_state.race_day]
    hours = day[day["hour"].between(9, 18)].to_dict("records")
    if not hours:
        st.error("No replay data for this race day.")
        return
    st.session_state.setdefault("live_index", 1)
    last = min(st.session_state.live_index, len(hours) - 1)

    def check(index):
        return engine.live_check(plan["sector"], plan["low"], plan["high"],
                                 hours[index], hours[index + 1:index + 3])

    top, sim = st.columns([3, 1])
    top.markdown("## Live strategy check")
    top.caption("Weather pulled every hour and compared with this morning's briefing. "
                "Hackathon mode: replaying June 2026 data as if live.")
    if sim.button("Simulate next hour ▸", type="primary", width="stretch", disabled=last >= len(hours) - 1):
        st.session_state.live_index = last + 1
        st.session_state.selected_hour = last + 1
        st.rerun()
    selected = min(st.session_state.get("selected_hour", last), last)

    snap_col, main = st.columns([1, 2.6], gap="medium")
    with snap_col, st.container(border=True):
        st.markdown("#### Hourly snapshots")
        for index in range(last, -1, -1):
            result = check(index)
            mood = "on plan" if result["status"] == "Plan holds" else result["status"].lower()
            label = f"{hours[index]['time']:%d %b %H:%M} · {engine.sector(hours[index]['dir'])} " \
                    f"{hours[index]['speed']:.0f} kt · {mood}"
            if st.button(label, key=f"snap_{index}", width="stretch",
                         type="primary" if index == selected else "secondary"):
                st.session_state.selected_hour = index
                st.rerun()

    with main:
        now = hours[selected]
        upcoming = hours[selected + 1:selected + 3]
        result = check(selected)
        next_speeds = [row["speed"] for row in upcoming] or [now["speed"]]
        cards = [("Wind now", f"{engine.sector(now['dir'])} {now['speed']:.0f} kt"),
                 ("Next 2 h", f"{min(next_speeds):.0f}–{max(next_speeds):.0f} kt"),
                 ("Sky", engine.sky(now["cloud"]))]
        for column, (label, value) in zip(st.columns(3), cards):
            column.markdown(f'<div class="la-card"><div class="la-small">{label}</div>'
                            f'<div style="font-size:1.6rem;font-weight:800;color:{NAVY}">{value}</div></div>',
                            unsafe_allow_html=True)
        badge = {"Plan holds": "la-ok", "Change coming": "la-warn", "Change": "la-bad"}[result["status"]]
        st.markdown(f'<div class="la-card"><b>AI insight</b> <span class="{badge}">{result["status"]}</span>'
                    f'<p style="margin:8px 0 0">{esc(result["message"])}</p>'
                    '<div class="la-small">Rule engine v0.1: compares live wind with the briefing window '
                    f'({plan["sector"]} {plan["low"]:.0f}–{plan["high"]:.0f} kt).</div></div>',
                    unsafe_allow_html=True)
        if result["warning"]:
            st.warning(result["warning"], icon="📣")

        view_col, map_col = st.columns([1, 2.2])
        with view_col:
            offset = st.segmented_control("Map time", [0, 1, 2], default=0, key="live_offset",
                                          format_func=lambda h: "T0" if h == 0 else f"T+{h}")
            shown = hours[min(selected + (offset or 0), len(hours) - 1)]
            _, tide = current_insight()
            st.markdown(f'<div class="la-dark"><div class="la-small">{shown["time"]:%H:%M} · from '
                        f'{engine.sector(shown["dir"])}</div><div class="big">{shown["speed"]:.0f} kt</div>'
                        f'Gusts {shown["gust"]:.0f} kt</div>', unsafe_allow_html=True)
        map_col.markdown(venue_svg(shown["dir"], shown["speed"], plan["side"],
                                   ["Wind", "Pressure", "Terrain effects"], tide["state"]),
                         unsafe_allow_html=True)

        st.markdown("#### Insight notifications")
        feed = [(index, check(index)) for index in range(last, -1, -1)]
        feed = [(index, r) for index, r in feed if r["status"] != "Plan holds"]
        if not feed:
            st.caption("No changes yet. New strategy suggestions appear here when the weather moves off plan.")
        for index, r in feed:
            icon = "🔁" if r["status"] == "Change" else "⏰"
            st.info(f"**{hours[index]['time']:%H:%M}** — {r['message']}"
                    + (f"\n\n{r['warning']}" if r["warning"] else ""), icon=icon)


# ---------- main ----------

def main():
    st.set_page_config(page_title="Location Agent", page_icon="⛵", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    defaults = {
        "step": STEPS[0], "venue": list(engine.VENUES)[0], "race_day": dt.date(2026, 6, 15),
        "time_of_day": "Midday", "wind_sector": "SSW", "map_hour": 13,
        "layers": ["Wind", "Pressure", "Terrain effects"], "brief_view": "Coach view",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    classes = engine.VENUES[st.session_state.venue]["classes"]
    if st.session_state.get("boat_class") not in classes:
        st.session_state.boat_class = classes[0]
    # Re-assigning detaches the keys from their widgets, so choices survive page switches.
    for key in [*defaults, "boat_class"]:
        st.session_state[key] = st.session_state[key]
    if st.session_state.get("_last_tod") != st.session_state.time_of_day and st.session_state.time_of_day:
        st.session_state.map_hour = engine.TIME_OF_DAY[st.session_state.time_of_day]
        st.session_state._last_tod = st.session_state.time_of_day
    # segmented controls return None when the active option is clicked again
    for key in ("wind_sector", "map_hour", "brief_view", "step"):
        if st.session_state.get(key) is None:
            st.session_state[key] = st.session_state.get(f"_prev_{key}", defaults[key])
        st.session_state[f"_prev_{key}"] = st.session_state[key]

    st.markdown(
        f'<div class="la-bar"><b>⛵ Location Agent</b><span>{esc(st.session_state.venue.split(" (")[0])} · '
        f'{st.session_state.race_day:%d %b %Y} · {esc(st.session_state.boat_class)}</span></div>',
        unsafe_allow_html=True)
    st.segmented_control("Step", STEPS, key="step", label_visibility="collapsed")

    {STEPS[0]: page_upload, STEPS[1]: page_venue_map,
     STEPS[2]: page_briefing, STEPS[3]: page_live}[st.session_state.step]()


if __name__ == "__main__":
    main()
