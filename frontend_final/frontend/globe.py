"""Preparation landing page: a spinning globe with live and upcoming events.

Picking a venue dives into it (camera zoom), then hands over to the dashboard.
Two-way component (st.components.v2): Python passes events + the shared selection,
JS sends back `entered` (venue chosen, dive finished) and `picked` (globe clicked).
"""

import datetime as dt
import json

import streamlit as st

from backend import strategy

OLYMPIC_DAYS = ("2028-07-16", "2028-07-28")

# shortcut: demo calendar for the globe only; backend data covers the LA28 venues. Swap for an events feed.
DEMO_EVENTS = [
    ("Puerto Vallarta ILCA Worlds", "Puerto Vallarta, Mexico", 20.65, -105.32, ["ILCA 7", "ILCA 6"], "2026-11-04", "2026-11-12"),
    ("Rio Skiff & Multihull Cup", "Rio de Janeiro, Brazil", -22.88, -43.15, ["49er", "49erFX", "Nacra 17"], "2026-12-02", "2026-12-08"),
    ("Sydney Harbour Foiling Series", "Sydney, Australia", -33.853, 151.238, ["iQFoil men", "iQFoil women"], "2026-12-14", "2026-12-19"),
    ("Bay of Cádiz 470 Europeans", "Cádiz, Spain", 36.548, -6.28, ["470 mixed"], "2027-02-10", "2027-02-16"),
    ("Semaine Olympique · Kite", "Hyères, France", 43.05, 6.17, ["Formula Kite men", "Formula Kite women"], "2027-04-20", "2027-04-26"),
    ("Medemblik Regatta", "Medemblik, Netherlands", 52.78, 5.16, ["ILCA 7", "ILCA 6", "470 mixed"], "2027-05-25", "2027-05-30"),
    ("Enoshima 49er Worlds", "Enoshima, Japan", 35.30, 139.48, ["49er", "49erFX"], "2027-09-08", "2027-09-14"),
]
def boat_type(boat_class):
    """Pin icon for a class."""
    for prefix, kind in (("ILCA", "dinghy"), ("470", "470"), ("49er", "skiff"), ("Nacra", "cat"),
                         ("iQFoil", "windfoil"), ("Formula Kite", "kite")):
        if boat_class.startswith(prefix):
            return kind
    return "dinghy"


LA_OFFSETS = (-56, 56, 0)  # px, so the three LA28 areas don't stack on one pin


def globe_events():
    """LA28 venues (enterable, from backend.strategy) + demo events (preview only)."""
    events = [
        {"id": name, "name": name.split(" (")[0], "place": "Los Angeles, USA", "lat": spot["lat"],
         "lon": spot["lon"], "classes": spot["classes"], "start": OLYMPIC_DAYS[0], "end": OLYMPIC_DAYS[1],
         "enterable": True, "dx": offset}
        for (name, spot), offset in zip(strategy.VENUES.items(), LA_OFFSETS)
    ]
    events += [
        {"id": name, "name": name, "place": place, "lat": lat, "lon": lon, "classes": classes,
         "start": start, "end": end, "enterable": False, "dx": 0}
        for name, place, lat, lon, classes, start, end in DEMO_EVENTS
    ]
    for event in events:
        event["icon"] = boat_type(event["classes"][0])
    return events


def render_globe(selection, returning, key, on_entered, on_picked):
    """Mount the globe. `selection`: venue id, class, day, time and shared lat/lon."""
    data = {"events": globe_events(), "selected": selection, "returning": returning,
            "today": dt.date.today().isoformat()}
    return _globe_component(key=key, data=json.loads(json.dumps(data, default=str)),
                            on_entered_change=on_entered, on_picked_change=on_picked)


GLOBE_HTML = """
<div class="lg-root">
  <div class="lg-stage"><div class="lg-globe"></div>
    <svg class="lg-rings" viewBox="0 0 400 400" aria-hidden="true">
      <g><ellipse cx="200" cy="200" rx="196" ry="44" transform="rotate(-6 200 200)" stroke-dasharray="560 70"/></g>
      <g><ellipse cx="200" cy="200" rx="186" ry="60" transform="rotate(64 200 200)" stroke-dasharray="520 90"/></g>
      <g><ellipse cx="200" cy="200" rx="190" ry="52" transform="rotate(-62 200 200)" stroke-dasharray="600 60"/></g>
    </svg>
  </div>
  <section class="lg-hero">
    <div class="lg-eyebrow">Race preparation</div>
    <h1>Where are we <b>racing next?</b></h1>
    <p>Spin the globe, pick a live or upcoming event, and dive into the venue.</p>
  </section>
  <button class="lg-ghost lg-spin" aria-pressed="true">Pause rotation</button>
  <aside class="lg-events" aria-label="Events">
    <h2>Live &amp; upcoming events</h2>
    <div class="lg-chips"></div>
    <div class="lg-list"></div>
    <div class="lg-note">LA 2028 venues from the backend · other events are demo previews</div>
  </aside>
  <div class="lg-card"></div>
  <div class="lg-veil"></div>
</div>
"""

GLOBE_CSS = """
.lg-root{position:relative;height:calc(100vh - 240px);min-height:540px;border-radius:20px;overflow:hidden;background:#02050b;color:#fff;
  font-family:'Hanken Grotesk',system-ui,sans-serif;--cyan:#5fd0ea;--orange:#FF6600;--glass:rgba(10,22,40,.62);--line:rgba(255,255,255,.12)}
.lg-root button{font:inherit}
.lg-stage{position:absolute;inset:0;transition:transform 1.4s cubic-bezier(.6,0,.9,.4),filter 1.4s}
.lg-stage.diving{transform:scale(2.4);filter:blur(6px) brightness(1.4)}
.lg-globe{position:absolute;inset:0}
.lg-rings{position:absolute;left:50%;top:50%;height:66%;aspect-ratio:1;transform:translate(-50%,-50%);pointer-events:none;transition:opacity .5s}
.lg-rings ellipse{fill:none;stroke:var(--cyan);stroke-width:5;stroke-linecap:round;filter:drop-shadow(0 0 6px rgba(95,208,234,.7));opacity:.9}
.lg-rings g{transform-origin:200px 200px;animation:lg-spin 60s linear infinite}
.lg-rings g:nth-child(2){animation-duration:85s;animation-direction:reverse}
.lg-rings g:nth-child(3){animation-duration:110s}
@keyframes lg-spin{to{transform:rotate(360deg)}}
.lg-root.no-rings .lg-rings{opacity:0}
.lg-hero{position:absolute;left:32px;top:32px;max-width:360px;pointer-events:none}
.lg-eyebrow{font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:var(--cyan)}
.lg-hero h1{font-weight:300;font-size:clamp(32px,3.6vw,52px);line-height:1.04;margin:12px 0 14px;letter-spacing:-.02em;color:#fff}
.lg-hero h1 b{font-weight:700}
.lg-hero p{opacity:.65;line-height:1.5;margin:0}
.lg-ghost{position:absolute;top:24px;right:24px;background:var(--glass);border:1px solid var(--line);color:#fff;border-radius:999px;padding:9px 16px;cursor:pointer}
.lg-ghost:hover{border-color:var(--cyan);color:var(--cyan)}
.lg-events{position:absolute;left:24px;bottom:24px;width:340px;max-height:46%;display:flex;flex-direction:column;
  background:var(--glass);backdrop-filter:blur(18px);border:1px solid var(--line);border-radius:18px;overflow:hidden}
.lg-events h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;opacity:.7;margin:16px 18px 10px;color:#fff}
.lg-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 18px 12px}
.lg-chip{border:1px solid var(--line);background:transparent;color:#fff;border-radius:999px;padding:4px 10px;font-size:12px;cursor:pointer}
.lg-chip.on{background:#fff;color:#071c2c;border-color:#fff}
.lg-list{overflow:auto;padding:0 8px 8px}
.lg-ev{display:flex;align-items:center;gap:12px;padding:10px;border-radius:12px;cursor:pointer;border:0;background:none;color:#fff;width:100%;text-align:left}
.lg-ev:hover,.lg-ev.hl{background:rgba(255,255,255,.08)}
.lg-ico{width:40px;height:40px;flex:none;border-radius:10px;background:rgba(255,255,255,.92);display:grid;place-items:center}
.lg-ico svg{width:34px;height:34px}
.lg-t{font-weight:600;font-size:14px}.lg-s{font-size:12px;opacity:.6}
.lg-when{margin-left:auto;font-size:12px;text-align:right;white-space:nowrap}
.lg-live{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--orange);margin-right:5px;animation:lg-pulse 1.6s infinite}
@keyframes lg-pulse{70%{box-shadow:0 0 0 8px rgba(255,102,0,0)}0%{box-shadow:0 0 0 0 rgba(255,102,0,.7)}}
.lg-note{font-size:10px;letter-spacing:.1em;text-transform:uppercase;opacity:.45;padding:0 18px 12px}
.lg-marker{position:relative;transform:translate(-50%,-100%);pointer-events:auto;cursor:pointer;display:flex;flex-direction:column;align-items:center;transition:opacity .25s;font-family:'Hanken Grotesk',system-ui,sans-serif}
.lg-bubble{width:52px;height:52px;border-radius:50%;background:rgba(255,255,255,.95);display:grid;place-items:center;
  box-shadow:0 6px 22px rgba(0,0,0,.45),0 0 0 3px rgba(255,255,255,.25);transition:transform .2s}
.lg-bubble svg{width:44px;height:44px}
.lg-marker.live .lg-bubble{box-shadow:0 6px 22px rgba(0,0,0,.45),0 0 0 3px var(--orange)}
.lg-marker.sel .lg-bubble{box-shadow:0 6px 22px rgba(0,0,0,.45),0 0 0 3px var(--cyan)}
.lg-stem{width:2px;height:14px;background:linear-gradient(#fff,transparent)}
.lg-label{position:absolute;bottom:72px;white-space:nowrap;font-size:13px;font-weight:600;padding:5px 10px;border-radius:999px;color:#fff;
  background:rgba(2,5,11,.7);backdrop-filter:blur(8px);border:1px solid var(--line);opacity:0;transform:translateY(4px);transition:.2s}
.lg-marker:hover .lg-bubble,.lg-marker.hl .lg-bubble{transform:scale(1.15)}
.lg-marker:hover .lg-label,.lg-marker.hl .lg-label,.lg-marker.live .lg-label,.lg-marker.sel .lg-label{opacity:1;transform:none}
.lg-marker.dim{opacity:.18!important;pointer-events:none}
.lg-card{position:absolute;right:24px;bottom:24px;width:320px;background:#f4f7f5;color:#071c2c;border-radius:18px;padding:18px 20px;box-shadow:0 30px 80px rgba(0,0,0,.5)}
.lg-card .cap{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#6b7a86}
.lg-card .name{font-size:18px;font-weight:700;margin:6px 0 4px;color:#00378A}
.lg-card .meta{font-size:13px;color:#5a6b78;line-height:1.5}
.lg-card button{width:100%;margin-top:14px;border-radius:10px;padding:11px 14px;cursor:pointer;font-weight:700;border:0;background:var(--orange);color:#fff}
.lg-card button:hover{background:#00378A}
.lg-veil{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none;transition:opacity .7s}
.lg-veil.on{opacity:1}
@media (max-width:1100px){.lg-hero{display:none}}
@media (max-width:760px){.lg-events{right:16px;left:16px;width:auto;bottom:150px;max-height:34%}.lg-card{left:16px;right:16px;width:auto;bottom:16px}}
@media (prefers-reduced-motion:reduce){.lg-root *{animation:none!important;transition:none!important}}
"""

GLOBE_JS = r"""
const HULL = (c='#e2483a') => `<path d="M6 46 54 41 47 51 13 54Z" fill="#f4f6f9"/><path d="M13 54 47 51 45 55 15 57Z" fill="${c}"/><path d="M6 46 13 54 15 57 8 49Z" fill="#c9d3df"/>`;
const ICONS = {
  dinghy: `<svg viewBox="0 0 64 64">${HULL()}<path d="M31 6v39" stroke="#8a6a3c" stroke-width="2"/><path d="M32 7 32 43 50 41Z" fill="#fff"/><path d="M32 7 32 43 36 42Z" fill="#dfe6ee"/><path d="M33 16h7M33 22h10" stroke="#e2483a" stroke-width="2.5"/></svg>`,
  '470':  `<svg viewBox="0 0 64 64">${HULL('#3976BE')}<path d="M30 6v39" stroke="#8a6a3c" stroke-width="2"/><path d="M31 7 31 43 47 41Z" fill="#fff"/><path d="M29 10 29 43 14 45Z" fill="#dfe6ee"/><path d="M32 18h8" stroke="#3976BE" stroke-width="2.5"/></svg>`,
  skiff:  `<svg viewBox="0 0 64 64">${HULL('#FF6600')}<path d="M30 4v41" stroke="#555" stroke-width="2"/><path d="M31 5 31 43 46 41Z" fill="#fff"/><path d="M29 8C14 16 8 30 9 45L29 43Z" fill="#FF6600"/><path d="M29 8C20 18 16 30 17 44L29 43Z" fill="#ff8a3d"/></svg>`,
  cat:    `<svg viewBox="0 0 64 64"><path d="M4 44 40 40 36 45 8 48Z" fill="#f4f6f9"/><path d="M8 48 36 45 35 47 10 50Z" fill="#e2483a"/><path d="M20 50 58 46 54 51 24 54Z" fill="#f4f6f9"/><path d="M24 54 54 51 53 53 26 56Z" fill="#e2483a"/><path d="M12 46 50 44" stroke="#9aa8b8" stroke-width="3"/><path d="M32 5v41" stroke="#555" stroke-width="2"/><path d="M33 6 33 44 52 42Z" fill="#fff"/><path d="M31 12 31 44 17 46Z" fill="#3976BE"/></svg>`,
  windfoil:`<svg viewBox="0 0 64 64"><path d="M10 48C20 44 44 41 56 44L52 49C40 52 20 54 12 52Z" fill="#f2c27b"/><path d="M12 52C20 54 40 52 52 49L51 51C40 54 22 56 13 54Z" fill="#e2483a"/><path d="M34 50v8M28 58h12" stroke="#2a3a4a" stroke-width="2"/><path d="M33 47 28 6" stroke="#666" stroke-width="2"/><path d="M28 7C44 12 50 28 46 44L33 46Z" fill="#fff"/><path d="M29 8C36 12 40 20 41 28L31 30Z" fill="#dfe6ee"/><path d="M38 14l6 4M41 22l6 3" stroke="#e2483a" stroke-width="2.5"/></svg>`,
  kite:   `<svg viewBox="0 0 64 64"><path d="M6 20C14 6 50 6 58 20L50 22C44 14 20 14 14 22Z" fill="#FF6600"/><path d="M14 22C20 14 44 14 50 22L46 23C40 18 24 18 18 23Z" fill="#00378A"/><path d="M14 22 31 46M50 22 33 46" stroke="#9aa8b8" stroke-width="1"/><path d="M20 50C26 47 40 46 46 48L44 52C38 53 26 54 21 53Z" fill="#f4f6f9"/><path d="M21 53C26 54 38 53 44 52L43 54C38 56 26 56 22 55Z" fill="#3976BE"/><circle cx="32" cy="43" r="3" fill="#2a3a4a"/><path d="M32 46v4M33 55v6" stroke="#2a3a4a" stroke-width="2"/></svg>`,
};
const TEXTURES = 'https://unpkg.com/three-globe/example/img/';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmt = d => new Date(d).toLocaleDateString('en-GB', {day: '2-digit', month: 'short', year: 'numeric'});
const short = c => c.replace(/ (men|women)$/, '');
const wait = ms => new Promise(r => setTimeout(r, ms));

function createGlobe(root) {
  const s = {root, data: null, filter: 'All', preview: null, busy: false, world: null, lastSel: null};
  const q = sel => root.querySelector(sel);
  const isLive = e => s.today >= new Date(e.start) && s.today <= new Date(e.end);
  const daysTo = e => Math.ceil((new Date(e.start) - s.today) / 864e5);
  const matches = e => s.filter === 'All' || e.classes.some(c => c.startsWith(s.filter));
  const spinning = () => q('.lg-spin').getAttribute('aria-pressed') === 'true';

  function markerEl(e) {
    const el = document.createElement('div');
    el.className = 'lg-marker' + (isLive(e) ? ' live' : '');
    el.dataset.i = e.i;
    if (e.dx) el.style.marginLeft = e.dx + 'px';
    const label = `${e.place.split(',').pop().trim()} · ${short(e.classes[0])} · ${new Date(e.start).toLocaleDateString('en-GB', {day: '2-digit', month: '2-digit'})}`;
    el.innerHTML = `<div class="lg-label">${isLive(e) ? '<span class="lg-live"></span>' : ''}${esc(label)}</div><div class="lg-bubble">${ICONS[e.icon]}</div><div class="lg-stem"></div>`;
    el.title = e.name;
    el.onclick = ev => { ev.stopPropagation(); choose(e); };
    el.onmouseenter = () => highlight(e.i, true);
    el.onmouseleave = () => highlight(e.i, false);
    return el;
  }
  function highlight(i, on) {
    root.querySelectorAll(`[data-i="${i}"]`).forEach(n => n.classList.toggle('hl', on));
    if (s.world) s.world.controls().autoRotate = !on && spinning();
  }
  function flyTo(p, altitude, ms) {
    if (!s.world) return;
    s.world.controls().autoRotate = false;
    s.world.pointOfView({lat: p.lat, lng: p.lon, altitude}, ms);
  }
  function choose(e) {
    if (e.enterable) { s.preview = null; dive(e); }
    else { s.preview = e; renderCard(); flyTo(e, 1.4, 1500); }
  }
  async function dive(e) {
    if (s.busy) return;
    s.busy = true;
    root.classList.add('no-rings');
    flyTo(e, 1.3, 1300); await wait(1300);
    s.world.pointOfView({lat: e.lat, lng: e.lon, altitude: 0.06}, 1800);
    await wait(700); q('.lg-stage').classList.add('diving');
    await wait(900); q('.lg-veil').classList.add('on');
    await wait(400);
    s.trigger('entered', {id: e.id, at: Date.now()});
  }
  function renderList() {
    const rows = s.events.filter(matches).sort((a, b) => new Date(a.start) - new Date(b.start));
    q('.lg-list').innerHTML = rows.map(e => `<button class="lg-ev" data-i="${e.i}">
        <span class="lg-ico">${ICONS[e.icon]}</span>
        <span><div class="lg-t">${esc(e.name)}</div><div class="lg-s">${esc(e.classes.slice(0, 3).join(' · '))}</div></span>
        <span class="lg-when">${isLive(e) ? '<span class="lg-live"></span>Live' : 'in ' + daysTo(e) + ' d'}<div class="lg-s">${fmt(e.start)}</div></span>
      </button>`).join('');
    root.querySelectorAll('.lg-marker').forEach(m => m.classList.toggle('dim', !matches(s.events[m.dataset.i])));
  }
  function renderCard() {
    const sel = s.data.selected, e = s.preview;
    q('.lg-card').innerHTML = e
      ? `<div class="cap">Preview · ${isLive(e) ? 'live now' : 'in ' + daysTo(e) + ' days'}</div><div class="name">${esc(e.name)}</div>
         <div class="meta">${esc(e.place)} · ${esc(e.classes.join(', '))}<br>${fmt(e.start)} – ${fmt(e.end)}<br>No venue data yet: the agents cover the LA 2028 venues.</div>`
      : `<div class="cap">Selected venue</div><div class="name">${esc(sel.name)}</div>
         <div class="meta">${esc(sel.boat_class)} · ${esc(sel.race_day)} · ${esc(sel.time_of_day)}<br>${(+sel.lat).toFixed(3)}, ${(+sel.lon).toFixed(3)}</div>
         <button type="button">Enter venue →</button>`;
    const btn = q('.lg-card button');
    if (btn) btn.onclick = () => dive({...s.events.find(ev => ev.id === sel.venue), lat: +sel.lat, lon: +sel.lon});
  }
  function setup() {
    q('.lg-chips').onclick = ev => {
      const f = ev.target.dataset.f; if (!f) return;
      s.filter = f;
      root.querySelectorAll('.lg-chip').forEach(c => c.classList.toggle('on', c.dataset.f === f));
      renderList();
    };
    const row = ev => ev.target.closest('.lg-ev');
    q('.lg-list').onclick = ev => { const b = row(ev); if (b) choose(s.events[b.dataset.i]); };
    q('.lg-list').onmouseover = ev => { const b = row(ev); if (b) { highlight(b.dataset.i, true); flyTo(s.events[b.dataset.i], 1.9, 1200); } };
    q('.lg-list').onmouseout = ev => { const b = row(ev); if (b) highlight(b.dataset.i, false); };
    q('.lg-spin').onclick = () => {
      const on = !spinning();
      q('.lg-spin').setAttribute('aria-pressed', on);
      q('.lg-spin').textContent = on ? 'Pause rotation' : 'Resume rotation';
      if (s.world) s.world.controls().autoRotate = on;
    };
  }
  async function start() {
    const {default: Globe} = await import('https://esm.sh/globe.gl@2');
    const el = q('.lg-globe');
    const world = new Globe(el)
      .width(el.clientWidth).height(el.clientHeight)
      .globeImageUrl(TEXTURES + 'earth-blue-marble.jpg')
      .bumpImageUrl(TEXTURES + 'earth-topology.png')
      .backgroundImageUrl(TEXTURES + 'night-sky.png')
      .atmosphereColor('#7fd3ff').atmosphereAltitude(0.18)
      .htmlElementsData(s.events).htmlLat('lat').htmlLng('lon').htmlAltitude(0.01)
      .htmlElement(markerEl)
      .onGlobeClick(({lat, lng}) => s.trigger('picked', {lat: +lat.toFixed(3), lon: +lng.toFixed(3)}));
    if (world.htmlElementVisibilityModifier) world.htmlElementVisibilityModifier((m, v) => { m.style.opacity = v ? '' : 0; m.style.pointerEvents = v ? '' : 'none'; });
    new ResizeObserver(() => world.width(el.clientWidth).height(el.clientHeight)).observe(el);
    const ctl = world.controls();
    ctl.autoRotate = true; ctl.autoRotateSpeed = 0.35; ctl.enableDamping = true;
    const sel = s.data.selected;
    if (s.data.returning) {  // coming back from the dashboard: zoom out of the venue
      world.pointOfView({lat: +sel.lat, lng: +sel.lon, altitude: 0.1});
      world.pointOfView({lat: +sel.lat, lng: +sel.lon, altitude: 2.4}, 2200);
    } else {
      world.pointOfView({lat: 15, lng: -60, altitude: 2.4});
    }
    s.world = world;
    s.lastSel = `${sel.lat},${sel.lon}`;
    update(s.data);
  }
  function update(data) {
    const first = !s.data;
    s.data = data;
    if (first) {
      s.today = new Date(data.today);
      s.events = data.events.map((e, i) => ({...e, i}));
      const filters = ['All', ...new Set(s.events.flatMap(e => e.classes.map(short)))];
      q('.lg-chips').innerHTML = filters.map(f => `<button class="lg-chip${f === 'All' ? ' on' : ''}" data-f="${esc(f)}">${esc(f)}</button>`).join('');
      setup(); renderList(); renderCard(); start();
      return;
    }
    if (!s.world) return;
    const sel = data.selected, key = `${sel.lat},${sel.lon}`;
    if (key !== s.lastSel) { s.preview = null; s.lastSel = key; flyTo({lat: +sel.lat, lon: +sel.lon}, 1.4, 1500); }
    root.querySelectorAll('.lg-marker').forEach(m => m.classList.toggle('sel', s.events[m.dataset.i].id === sel.venue));
    renderCard();
  }
  s.update = update;
  return s;
}

export default function (component) {
  const {data, parentElement, setTriggerValue} = component;
  const root = parentElement.querySelector('.lg-root');
  root.__globe = root.__globe || createGlobe(root);
  root.__globe.trigger = setTriggerValue;
  root.__globe.update(data);
}
"""

_globe_component = st.components.v2.component(
    "prep_globe", html=GLOBE_HTML, css=GLOBE_CSS, js=GLOBE_JS,
)
