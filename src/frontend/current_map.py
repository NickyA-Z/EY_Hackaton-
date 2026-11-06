"""Leaflet/canvas renderer for dynamic regional marine fields."""

import json

import streamlit as st


def render_current_map(payload, height=650):
    """Render an animated vector field or scalar colour field.

    Payload key `style`: "tracker" (default, YB-tracker look) or "classic" (the original dark map).
    """
    payload = {"style": "tracker", **payload}
    encoded_payload = json.dumps(payload, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    html = CURRENT_MAP_HTML.replace("__CURRENT_DATA__", encoded_payload)
    st.iframe(
        html,
        width="stretch",
        height=height,
        alt=f"Regional marine map showing {payload['title']}"
    )


def combine_layers(grids, **options):
    """One payload that overlays several single-layer grids (same bounds, same hours).

    Options: start_frame (hour index to open on) and autoplay (False = start paused).
    """
    shared = {key: grids[0][key] for key in
              ("bounds", "latitudes", "longitudes", "rows", "columns", "requested_location")}
    return {**shared, "title": " + ".join(grid["title"] for grid in grids), "layers": grids, **options}


CURRENT_MAP_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap">
  <style>
    * { box-sizing: border-box; }
    html, body, #map { width: 100%; height: 100%; margin: 0; background: #06151f; }
    body { font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
    #map { border-radius: 16px; overflow: hidden; border: 1px solid rgba(122, 190, 199, .22); }
    .leaflet-container { background: #06151f; }
    .leaflet-tile-pane {
      filter: brightness(.52) contrast(1.14) saturate(.78);
    }
    .leaflet-control-attribution { background: rgba(3, 17, 25, .74) !important; color: #8fa5ac; }
    .leaflet-control-attribution a { color: #8edfe1; }
    .scalar-canvas { position: absolute; inset: 0; pointer-events: none; z-index: 430; }
    .current-canvas { position: absolute; inset: 0; pointer-events: none; z-index: 450; }
    .hud {
      position: absolute; z-index: 800; left: 16px; top: 16px; width: min(430px, calc(100% - 32px));
      color: #eaf8f6; background: rgba(3, 18, 27, .82); border: 1px solid rgba(125, 209, 208, .22);
      border-radius: 12px; padding: 13px 14px; backdrop-filter: blur(12px); box-shadow: 0 12px 35px rgba(0,0,0,.2);
    }
    .hud-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .kicker { color: #65d5d1; font: 700 10px/1.2 ui-monospace, monospace; letter-spacing: .12em; }
    .time { margin-top: 4px; font-size: 17px; font-weight: 650; letter-spacing: -.02em; }
    .play { border: 1px solid rgba(101,213,209,.35); background: rgba(101,213,209,.1); color: #cffffb; border-radius: 999px; padding: 7px 11px; cursor: pointer; font: 700 10px ui-monospace, monospace; }
    .play:hover { background: rgba(101,213,209,.2); }
    .slider-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; margin-top: 11px; }
    input[type=range] { width: 100%; accent-color: #6ce1db; cursor: pointer; }
    .hour { min-width: 45px; text-align: right; color: #b7cbd0; font: 600 11px ui-monospace, monospace; }
    .legend {
      position: absolute; z-index: 800; right: 14px; bottom: 22px; color: #d8e6e8;
      background: rgba(3,18,27,.78); border: 1px solid rgba(255,255,255,.13); border-radius: 9px; padding: 9px 10px;
      font: 600 9px ui-monospace, monospace; backdrop-filter: blur(10px);
    }
    .gradient { width: 150px; height: 7px; border-radius: 5px; margin: 6px 0 4px; background: linear-gradient(90deg,#61e5dc,#b6e94b,#ffc247,#ff6b46); }
    .legend-values { display: flex; justify-content: space-between; color: #91a6ac; }
    .legend-row + .legend-row { margin-top: 9px; }
    .swatch { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    .gps-metrics { display:none;position:absolute;z-index:800;right:14px;top:16px;width:220px;
      color:#eaf8f6;background:rgba(3,18,27,.82);border:1px solid rgba(125,209,208,.22);
      border-radius:12px;padding:11px 13px;backdrop-filter:blur(12px);box-shadow:0 12px 35px rgba(0,0,0,.2); }
    .gps-metrics-title { color:#65d5d1;font:700 10px ui-monospace,monospace;letter-spacing:.1em;
      padding-bottom:7px;border-bottom:1px solid rgba(255,255,255,.12); }
    .gps-metric { display:flex;justify-content:space-between;gap:10px;padding:7px 0;
      border-bottom:1px solid rgba(255,255,255,.09);font-size:10px;color:#b9cdd0; }
    .gps-metric:last-child { border-bottom:0; }
    .gps-metric strong { color:#fff;font-size:13px;white-space:nowrap; }
    .readout {
      position: absolute; z-index: 800; left: 16px; bottom: 20px; color: #bcd0d3; background: rgba(3,18,27,.78);
      border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 8px 10px; font: 600 10px/1.45 ui-monospace, monospace;
      white-space: pre;
    }
    .leaflet-popup-content-wrapper, .leaflet-popup-tip { background: #071c27; color: #eaf8f6; }
    .leaflet-popup-content { font: 600 11px/1.6 ui-monospace, monospace; }
    /* ---------- Tracker style (YB race-viewer look) ---------- */
    #timeline, .tb, .tpanel { display: none; }
    body.tracker { font-family: Figtree, 'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif; color: #323552; }
    body.tracker #map { border-radius: 14px; }
    body.tracker .leaflet-container { font-family: inherit; }
    body.tracker .leaflet-control-zoom { display: none; }
    body.tracker .leaflet-control-attribution { background: rgba(255,255,255,.55) !important; color: #323552; }
    body.tracker .leaflet-control-attribution a { color: #323552; }
    .glass { background: rgba(255,255,255,.55); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
      border-radius: 8px; color: #323552; box-shadow: 0 2px 14px rgba(30,40,70,.14); }
    body.tracker .hud { left: 12px; top: 12px; width: auto; padding: 8px 12px; color: #323552; border: 0;
      background: rgba(255,255,255,.55); backdrop-filter: blur(8px); border-radius: 8px; box-shadow: 0 2px 14px rgba(30,40,70,.14); }
    body.tracker .hud .slider-row, body.tracker .legend { display: none; }
    body.tracker .kicker { color: #323552; font: 700 12px/1.2 Figtree, sans-serif; letter-spacing: .02em; text-transform: none; }
    body.tracker .readout { left: 12px; bottom: 112px; color: #323552; border: 0; background: rgba(255,255,255,.55);
      backdrop-filter: blur(8px); font: 500 11px/1.45 'DM Mono', ui-monospace, monospace; }
    body.tracker .gps-metrics { top: 70px; right: 12px; color: #323552; border: 0; background: rgba(255,255,255,.55);
      backdrop-filter: blur(8px); border-radius: 8px; box-shadow: 0 2px 14px rgba(30,40,70,.14); }
    body.tracker .gps-metrics-title { color: #323552; font: 700 13px Figtree, sans-serif; letter-spacing: 0; border-color: rgba(50,53,82,.15); }
    body.tracker .gps-metric { color: #4b4e6a; font-size: 12px; border-color: rgba(50,53,82,.1); }
    body.tracker .gps-metric strong { color: #323552; font: 600 14px 'DM Mono', monospace; }
    /* top-right round buttons */
    body.tracker .tb { display: flex; gap: 10px; position: absolute; z-index: 900; top: 12px; right: 12px; }
    .tb button { width: 46px; height: 46px; border-radius: 999px; border: 0; background: #f1f3f4; color: #3c4043;
      display: grid; place-items: center; cursor: pointer; box-shadow: 0 2px 8px rgba(30,40,70,.18); position: relative; }
    .tb button.on { background: radial-gradient(at 50% 10%, #fefac5 0%, #fae816 100%); }
    .tb button:hover::after { content: attr(data-tip); position: absolute; top: 54px; right: 0; white-space: nowrap;
      background: #1f2233; color: #fff; font: 600 12px Figtree, sans-serif; padding: 6px 10px; border-radius: 6px; }
    .tb svg, .tile svg, .tp-head svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.6;
      stroke-linecap: round; stroke-linejoin: round; }
    /* panels (weather overlay / map settings) */
    body.tracker .tpanel.open { display: block; }
    .tpanel { position: absolute; z-index: 880; left: 12px; top: 12px; width: min(360px, calc(100% - 24px)); overflow: hidden; }
    .tp-head { display: flex; align-items: center; gap: 10px; padding: 12px 14px; font: 700 17px Figtree, sans-serif;
      background: rgba(255,255,255,.25); }
    .tp-head .x { margin-left: auto; border: 0; background: none; font-size: 22px; line-height: 1; color: #323552; cursor: pointer; }
    .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 12px 14px; }
    .tile { border: 0; border-radius: 8px; background: rgba(255,255,255,.6); color: #323552; padding: 12px 4px 10px;
      display: grid; justify-items: center; gap: 3px; cursor: pointer; font: 600 13px Figtree, sans-serif; }
    .tile small { font: 400 11px Figtree, sans-serif; opacity: .8; }
    .tile i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; }
    .tp-legend .legend-row + .legend-row { margin-top: 10px; }
    .tp-legend .legend-row > span { font: 600 13px Figtree, sans-serif; }
    .tp-legend .gradient { width: 100%; height: 14px; border-radius: 4px; }
    .tp-legend .legend-values { color: #323552; font: 500 11px 'DM Mono', monospace; }
    .tile.on { background: #2f5bd8; color: #fff; box-shadow: 0 2px 10px rgba(47,91,216,.35); }
    .tile:not(.on):hover { background: rgba(255,255,255,.85); }
    .tp-legend { padding: 10px 14px 12px; border-top: 1px solid rgba(50,53,82,.08); }
    .tp-legend h4 { margin: 0 0 8px; font: 600 14px Figtree, sans-serif; }
    .tp-bar { height: 20px; border-radius: 4px; }
    .tp-ticks { display: flex; justify-content: space-between; margin-top: 5px; font: 500 11px 'DM Mono', monospace; }
    .tp-src { margin-top: 8px; font: 400 11px Figtree, sans-serif; opacity: .8; }
    .srow { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; cursor: pointer;
      font: 500 14px Figtree, sans-serif; border-top: 1px solid rgba(50,53,82,.08); }
    .srow i { width: 24px; height: 24px; border-radius: 50%; border: 1.6px solid #323552; display: grid; place-items: center; font-style: normal; font-size: 13px; }
    .srow:not(.on) i { opacity: .35; }
    /* bottom timeline */
    body.tracker #timeline { display: block; position: absolute; z-index: 870; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px 12px; }
    .tl-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    body.tracker #timeLabel { margin: 0; font: 600 18px 'DM Mono', ui-monospace, monospace; letter-spacing: .01em; color: #323552; }
    body.tracker #playButton { border: 0; background: #fff; color: #323552; border-radius: 999px; padding: 7px 14px;
      font: 600 13px Figtree, sans-serif; box-shadow: 0 1px 6px rgba(30,40,70,.15); }
    .tl-bar { position: relative; height: 28px; border-radius: 999px; background: rgba(140,142,158,.42); overflow: visible; }
    #tlTicks span { position: absolute; top: 50%; transform: translateY(-50%); padding-left: 5px; white-space: nowrap;
      border-left: 1px solid rgba(255,255,255,.75); font: 500 11px 'DM Mono', monospace; color: #3c3f5c; }
    body.tracker #timeSlider { -webkit-appearance: none; appearance: none; position: absolute; inset: 0; width: 100%;
      height: 100%; margin: 0; background: transparent; }
    body.tracker #timeSlider::-webkit-slider-thumb { -webkit-appearance: none; width: 26px; height: 26px; border-radius: 50%;
      background: #fff; border: 2px solid #323552; box-shadow: 0 1px 5px rgba(0,0,0,.25); }
    /* markers */
    .pin { transform: translate(-50%, -100%); width: 26px; }
    .coord, .btag { position: absolute; left: 16px; top: -34px; white-space: nowrap; padding: 3px 7px; border-radius: 4px;
      font: 500 11px 'DM Mono', monospace; background: rgba(255,255,255,.75); color: #323552; }
    .boat { position: absolute; transform: translate(-50%, -50%); }
    .btag { left: 12px; top: -30px; font: 600 11px Figtree, sans-serif; color: #fff; }
    @media (max-width: 600px) {
      .hud { left: 10px; top: 10px; width: calc(100% - 20px); }
      .legend { right: 10px; bottom: 14px; }
      .readout { display: none; }
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="hud">
    <div class="hud-top">
      <div><div class="kicker" id="layerTitle">MARINE FIELD</div><div class="time" id="timeLabel">Loading field…</div></div>
      <button class="play" id="playButton">PAUSE</button>
    </div>
    <div class="slider-row"><input id="timeSlider" type="range" min="0" step="1"><span class="hour" id="hourLabel">—</span></div>
  </div>
  <div class="readout" id="readout">Move over the map · click for details</div>
  <div class="legend" id="legend"></div>
  <div class="gps-metrics" id="gpsMetrics">
    <div class="gps-metrics-title">GPS SPEED · SELECTED FRAME</div>
    <div class="gps-metric"><span>Speed now</span><strong id="gpsSpeedNow">—</strong></div>
    <div class="gps-metric"><span>In 30 seconds</span><strong id="gpsSpeedPredicted">—</strong></div>
    <div class="gps-metric"><span>80% range</span><strong id="gpsSpeedRange">—</strong></div>
    <div class="gps-metric"><span>Replay actual</span><strong id="gpsSpeedActual">—</strong></div>
  </div>
  <div class="tb">
    <button id="tbReset" data-tip="Reset map"><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 14-5.3M20 4v4h-4M20 12a8 8 0 0 1-14 5.3M4 20v-4h4"/></svg></button>
    <button id="tbSettings" data-tip="Map settings"><svg viewBox="0 0 24 24"><path d="M12 3 2 8l10 5 10-5-10-5zM2 12.5l10 5 10-5M2 17l10 5 10-5"/></svg></button>
    <button id="tbOverlay" data-tip="Weather overlay"><svg viewBox="0 0 24 24"><path d="M7 18h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 11.5 3.3 3.3 0 0 0 7 18zM12 13l-2 3h4l-2 3"/></svg></button>
    <button id="tbFull" data-tip="Full screen" aria-label="Full screen"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg></button>
  </div>
  <div class="tpanel glass" id="overlayPanel">
    <div class="tp-head"><svg viewBox="0 0 24 24"><path d="M7 18h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 11.5 3.3 3.3 0 0 0 7 18zM12 13l-2 3h4l-2 3"/></svg>Weather Overlay<button class="x" data-close>×</button></div>
    <div class="tiles" id="tiles"></div>
    <div class="tp-legend" id="tpLegend"></div>
  </div>
  <div class="tpanel glass" id="settingsPanel">
    <div class="tp-head"><svg viewBox="0 0 24 24"><path d="M12 3 2 8l10 5 10-5-10-5zM2 12.5l10 5 10-5M2 17l10 5 10-5"/></svg>Map Settings<button class="x" data-close>×</button></div>
    <div id="settingsRows"></div>
  </div>
  <div id="timeline" class="glass">
    <div class="tl-head"><div id="tlTime"></div><div id="tlPlay"></div></div>
    <div class="tl-bar"><div id="tlTicks"></div><div id="tlTrack"></div></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const field = __CURRENT_DATA__;
    const bounds = field.bounds;
    const rows = field.rows;
    const columns = field.columns;
    const latitudes = field.latitudes;
    const longitudes = field.longitudes;
    // One layer per grid; a plain single grid is a one-layer overlay. All layers share bounds and hours.
    const layers = field.layers && field.layers.length ? field.layers : [field];
    const multi = layers.length > 1;
    const frames = layers[0].frames;
    const gpsTrack = field.gps_track || [];
    const gpsOverlay = field.gps_overlay || [];
    const gpsMode = gpsTrack.length > 0;
    const locationOnly = Boolean(field.location_only);
    function setSpeedLegend() {
      document.getElementById('legend').innerHTML =
        '<span>SPEED · KNOTS</span><div class="gradient"></div>' +
        '<div class="legend-values"><span>0</span><span>8+</span></div>';
    }
    // Optional payload keys: start_frame (open on this hour) and autoplay (false = start paused).
    let frameIndex = Math.min(Math.max(0, field.start_frame ?? frames.length - 1), Math.max(0, frames.length - 1));
    let playing = field.autoplay ?? true;
    let lastFrameAdvance = performance.now();
    function getLoadedDataBounds() {
      if (gpsMode) {
        const trackBounds = L.latLngBounds(gpsTrack.map(point => [point.lat,point.lng]));
        gpsTrack.forEach(point => trackBounds.extend([point.predicted_lat,point.predicted_lng]));
        return trackBounds.pad(.12);
      }
      if (locationOnly) {
        const areaBounds = L.latLngBounds(
          [bounds.south, bounds.west],
          [bounds.north, bounds.east]
        );
        gpsOverlay.forEach(point => {
          areaBounds.extend([point.lat,point.lng]);
          areaBounds.extend([point.predicted_lat,point.predicted_lng]);
        });
        return areaBounds;
      }
      let south = Infinity;
      let north = -Infinity;
      let west = Infinity;
      let east = -Infinity;

      layers.forEach((layer) => layer.frames.forEach((frame) => {
        (frame.value || []).forEach((value, index) => {
          if (value === null || value === undefined || !Number.isFinite(Number(value))) return;
          const row = Math.floor(index / columns);
          const column = index % columns;
          const latitude = Number(latitudes[row]);
          const longitude = Number(longitudes[column]);
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
          south = Math.min(south, latitude);
          north = Math.max(north, latitude);
          west = Math.min(west, longitude);
          east = Math.max(east, longitude);
        });
      }));

      let dataBounds;
      if (![south, north, west, east].every(Number.isFinite)) {
        dataBounds = L.latLngBounds(
          [bounds.south, bounds.west],
          [bounds.north, bounds.east]
        );
      } else {
        // Leaflet cannot fit a zero-area bound, so give a single row/column
        // half a grid cell of breathing room.
        const latitudeStep = Math.abs(Number(latitudes[1]) - Number(latitudes[0])) || 0.02;
        const longitudeStep = Math.abs(Number(longitudes[1]) - Number(longitudes[0])) || 0.02;
        if (south === north) {
          south -= latitudeStep / 2;
          north += latitudeStep / 2;
        }
        if (west === east) {
          west -= longitudeStep / 2;
          east += longitudeStep / 2;
        }
        dataBounds = L.latLngBounds([south, west], [north, east]);
      }
      gpsOverlay.forEach(point => {
        dataBounds.extend([point.lat,point.lng]);
        dataBounds.extend([point.predicted_lat,point.predicted_lng]);
      });
      return dataBounds;
    }

    const loadedDataBounds = getLoadedDataBounds();
    const map = L.map('map', {
      zoomControl: true,
      preferCanvas: true,
      zoomSnap: 0.01,
      zoomDelta: 0.5,
      minZoom: 1,
      maxZoom: 18
    });
    const tracker = field.style !== 'classic';
    if (tracker) document.body.classList.add('tracker');
    const T = { hidden: new Set(), showParticles: true, showLabels: true };  // hidden = layer indexes switched off in the panel
    let labelTiles = null;
    let fallbackTilesLoaded = false;
    const oceanTiles = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
      {
        maxNativeZoom: 12,
        maxZoom: 18,
        attribution: 'Tiles &copy; Esri &mdash; Esri, GEBCO, NOAA'
      }
    );
    oceanTiles.on('tileerror', () => {
      if (fallbackTilesLoaded) return;
      fallbackTilesLoaded = true;
      map.removeLayer(oceanTiles);
      L.tileLayer('https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors, Tiles HOT'
      }).addTo(map);
    });
    oceanTiles.addTo(map);
    labelTiles = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
      { maxNativeZoom: 12, maxZoom: 18, pane: 'overlayPane' }
    ).addTo(map);
    const locationMarker = field.location_marker;
    function degMin(value, positive, negative) {
      const a = Math.abs(value);
      return `${Math.floor(a)}° ${((a % 1) * 60).toFixed(2)} ${value >= 0 ? positive : negative}`;
    }
    if (locationMarker && tracker) {
      L.circle([locationMarker.lat, locationMarker.lng], {
        radius: locationMarker.radius_m || 1000, color: '#323552', weight: 1.5,
        fillColor: '#323552', fillOpacity: .04, dashArray: '6 6', interactive: false
      }).addTo(map);
      L.marker([locationMarker.lat, locationMarker.lng], { interactive: false, icon: L.divIcon({
        className: '', iconSize: [0, 0],
        html: '<div class="pin"><svg viewBox="0 0 26 36" width="26" height="36"><path d="M13 35C13 35 2 21 2 13a11 11 0 0 1 22 0c0 8-11 22-11 22z" fill="#fae816" stroke="#8a7f00" stroke-width="1"/><circle cx="13" cy="13" r="4.5" fill="#fff"/></svg></div>' +
              `<div class="coord">${locationMarker.name} · ${degMin(locationMarker.lat, 'N', 'S')}, ${degMin(locationMarker.lng, 'E', 'W')}</div>`
      })}).addTo(map);
    } else if (locationMarker) {
      map.createPane('locationPane');
      map.getPane('locationPane').style.zIndex = 650;
      map.getPane('locationPane').style.pointerEvents = 'none';
      L.circle([locationMarker.lat, locationMarker.lng], {
        pane: 'locationPane', radius: locationMarker.radius_m || 1000,
        color: '#65d5d1', weight: 2, fillColor: '#65d5d1',
        fillOpacity: .08, dashArray: '7 6'
      }).addTo(map);
      L.circleMarker([locationMarker.lat, locationMarker.lng], {
        radius: 8, color: '#fff', weight: 2,
        fillColor: '#ff6900', fillOpacity: 1
      }).addTo(map).bindTooltip(
        `${locationMarker.name}<br>${locationMarker.lat.toFixed(3)}, ${locationMarker.lng.toFixed(3)}`
      );
    }

    // Fit the complete loaded extent inside the panel. Ocean tiles stop at
    // native zoom 12, but Leaflet can over-zoom those same tiles for detailed
    // local sailing views without changing the Live basemap.
    let dataFitZoom = map.getMinZoom();
    function getDataFitZoom() {
      return Math.min(
        map.getMaxZoom(),
        map.getBoundsZoom(loadedDataBounds, false, L.point(48, 48))
      );
    }
    function scopeMapToLoadedData(force = false) {
      const wasAtDataExtent = Math.abs(map.getZoom() - dataFitZoom) < 0.05;
      dataFitZoom = getDataFitZoom();
      if (force || wasAtDataExtent) {
        map.setView(loadedDataBounds.getCenter(), dataFitZoom, { animate: false });
      }
    }
    scopeMapToLoadedData(true);

    // ---------- Tracker helpers ----------
    const ICONS = {
      'Wind': '<path d="M3 8h10a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7"/>',
      'Waves': '<path d="M2 11c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3M2 17c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3"/>',
      'Wind waves': '<path d="M3 6h9a2.5 2.5 0 1 0-2.5-2.5M2 15c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3M2 20c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2"/>',
      'Swell': '<path d="M2 16c3 0 4-9 9.5-9S17 16 22 16M2 20h20"/>',
      'Ocean currents': '<path d="M4 8h13m-3-3 3 3-3 3M20 16H7m3-3-3 3 3 3"/>',
    };
    const $ = (id) => document.getElementById(id);

    function openPanel(id) {
      ['overlayPanel', 'settingsPanel'].forEach((panel) => {
        const open = panel === id && !$(panel).classList.contains('open');
        $(panel).classList.toggle('open', open);
        $(panel === 'overlayPanel' ? 'tbOverlay' : 'tbSettings').classList.toggle('on', open);
      });
    }
    function renderSettings(onChange) {
      const rows = [['showParticles', 'Show moving particles'], ['showLabels', 'Show place names']];
      $('settingsRows').innerHTML = rows.map(([key, label]) =>
        `<div class="srow ${T[key] ? 'on' : ''}" data-key="${key}">${label}<i>✓</i></div>`).join('');
      $('settingsRows').querySelectorAll('.srow').forEach((row) => row.addEventListener('click', () => {
        T[row.dataset.key] = !T[row.dataset.key];
        if (labelTiles) T.showLabels ? labelTiles.addTo(map) : map.removeLayer(labelTiles);
        renderSettings(onChange);
        onChange();
      }));
    }
    function setTicks(count, labelAt) {
      const n = Math.min(count, 8);
      $('tlTicks').innerHTML = count < 2 ? '' : Array.from({ length: n }, (_, k) => {
        const i = Math.round(k * (count - 1) / Math.max(1, n - 1));
        return `<span style="left:calc(${(i / (count - 1) * 100).toFixed(2)}% * .93)">${labelAt(i)}</span>`;
      }).join('');
    }
    // Hull-shaped boat with a name tag, pointing along its last few GPS fixes.
    let boatMarker = null;
    function placeBoat(track, index) {
      if (!tracker || !track.length) return;
      const point = track[index], prev = track[Math.max(0, index - 3)];
      const dx = (point.lng - prev.lng) * Math.cos(point.lat * Math.PI / 180), dy = point.lat - prev.lat;
      const heading = (dx || dy) ? Math.atan2(dx, dy) * 180 / Math.PI : 0;
      const html = `<div class="boat" style="transform:translate(-50%,-50%) rotate(${heading}deg)">` +
        '<svg viewBox="0 0 12 30" width="12" height="30"><path d="M6 0C10 8 11 18 10 30H2C1 18 2 8 6 0z" fill="#ff6900" stroke="#1d2340" stroke-width=".8"/></svg></div>' +
        `<div class="btag" style="background:#ff6900">${field.boat_label || 'Boat'} · ${point.speed_kt.toFixed(1)} kt</div>`;
      const icon = L.divIcon({ className: '', iconSize: [0, 0], html });
      if (!boatMarker) boatMarker = L.marker([point.lat, point.lng], { icon, interactive: false, zIndexOffset: 1000 }).addTo(map);
      else boatMarker.setLatLng([point.lat, point.lng]).setIcon(icon);
    }
    if (tracker) {
      $('tlTime').appendChild($('timeLabel'));
      $('tlPlay').appendChild($('playButton'));
      $('tlTrack').appendChild($('timeSlider'));
      // The existing code writes PLAY/PAUSE; show it as the tracker's Playback pill.
      const playButton = $('playButton');
      new MutationObserver(() => {
        const label = playButton.textContent === 'PAUSE' ? '❚❚ Pause' : playButton.textContent === 'PLAY' ? '▷ Playback' : null;
        if (label) playButton.textContent = label;
      }).observe(playButton, { childList: true, characterData: true, subtree: true });
      $('tbReset').addEventListener('click', () => scopeMapToLoadedData(true));
      // Full screen: the map lives in a same-origin iframe, so fullscreen its frame in the app page.
      const frame = window.frameElement, host = frame ? frame.ownerDocument : document;
      const showFull = (on) => {
        $('tbFull').classList.toggle('on', on);
        $('tbFull').dataset.tip = on ? 'Exit full screen' : 'Full screen';
        setTimeout(() => map.invalidateSize(), 50);
      };
      const overlayOn = () => frame && frame.style.position === 'fixed';
      const setOverlay = (on) => {  // fallback when the browser refuses the Fullscreen API
        if (!frame) return;
        Object.assign(frame.style, on
          ? { position: 'fixed', inset: '0', width: '100vw', height: '100vh', zIndex: '999999', background: '#fff' }
          : { position: '', inset: '', width: '', height: '', zIndex: '', background: '' });
        showFull(on);
      };
      $('tbFull').addEventListener('click', () => {
        if (host.fullscreenElement) return host.exitFullscreen();
        if (overlayOn()) return setOverlay(false);
        const target = frame || document.documentElement;
        (target.requestFullscreen ? target.requestFullscreen() : Promise.reject()).catch(() => setOverlay(true));
      });
      host.addEventListener('fullscreenchange', () => showFull(!!host.fullscreenElement));
      document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && overlayOn()) setOverlay(false); });
      $('tbSettings').addEventListener('click', () => openPanel('settingsPanel'));
      $('tbOverlay').addEventListener('click', () => openPanel('overlayPanel'));
      document.querySelectorAll('[data-close]').forEach((button) =>
        button.addEventListener('click', () => openPanel(null)));
      renderSettings(() => { fieldDirtyHook(); });
    }
    let fieldDirtyHook = () => {};

    let overlayGpsIndex = Math.max(0, Math.min(
      gpsOverlay.length - 1,
      Number(field.gps_overlay_index ?? gpsOverlay.length - 1)
    ));
    let overlayGpsPlaying = false;
    let overlayTrail = null;
    let overlayMarker = null;
    let overlayProjection = null;
    let overlayPredictedMarker = null;
    if (gpsOverlay.length) {
      map.createPane('gpsOverlayPane');
      map.getPane('gpsOverlayPane').style.zIndex = 620;
      overlayTrail = L.layerGroup().addTo(map);
      overlayProjection = L.polyline([], {
        pane:'gpsOverlayPane',color:'#ff6900',weight:3,dashArray:'7 6'
      }).addTo(map);
      overlayMarker = L.circleMarker([0,0], {
        pane:'gpsOverlayPane',radius:8,color:'#fff',weight:2,
        fillColor:'#071c2c',fillOpacity:1
      }).addTo(map);
      overlayPredictedMarker = L.circleMarker([0,0], {
        pane:'gpsOverlayPane',radius:7,color:'#fff',weight:2,
        fillColor:'#ff6900',fillOpacity:1
      }).addTo(map);
    }
    function renderGpsOverlay(index) {
      if (!gpsOverlay.length) return;
      overlayGpsIndex=Math.max(0,Math.min(gpsOverlay.length - 1,Number(index)));
      overlayTrail.clearLayers();
      for (let i=1;i<=overlayGpsIndex;i++) {
        const colour=gpsOverlay[i].colour;
        L.polyline(
          [[gpsOverlay[i-1].lat,gpsOverlay[i-1].lng],
           [gpsOverlay[i].lat,gpsOverlay[i].lng]],
          {pane:'gpsOverlayPane',color:`rgb(${colour.join(',')})`,weight:4,opacity:.9}
        ).addTo(overlayTrail).bindTooltip(`${gpsOverlay[i].speed_kt.toFixed(1)} kt`);
      }
      const point=gpsOverlay[overlayGpsIndex];
      placeBoat(gpsOverlay, overlayGpsIndex);
      overlayMarker.setLatLng([point.lat,point.lng])
        .bindTooltip(`Selected GPS: ${point.speed_kt.toFixed(1)} kt`);
      overlayPredictedMarker.setLatLng([point.predicted_lat,point.predicted_lng])
        .bindTooltip(`Predicted: ${point.predicted_speed_kt.toFixed(1)} kt`);
      overlayProjection.setLatLngs([
        [point.lat,point.lng],[point.predicted_lat,point.predicted_lng]
      ]);
      const timestamp=new Date(point.time_epoch*1000).toLocaleTimeString('en-US', {
        timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',second:'2-digit'
      });
      document.getElementById('timeSlider').value=overlayGpsIndex;
      document.getElementById('timeLabel').textContent=`GPS replay · ${timestamp}`;
      document.getElementById('hourLabel').textContent=
        `${overlayGpsIndex+1}/${gpsOverlay.length}`;
      document.getElementById('readout').textContent=
        'Recorded GPS route · marine field fixed at selected forecast hour';
      document.getElementById('gpsSpeedNow').textContent=`${point.speed_kt.toFixed(1)} kt`;
      document.getElementById('gpsSpeedPredicted').textContent=
        `${point.predicted_speed_kt.toFixed(1)} kt`;
      document.getElementById('gpsSpeedRange').textContent=
        `${point.prediction_low_kt.toFixed(1)}–${point.prediction_high_kt.toFixed(1)} kt`;
      document.getElementById('gpsSpeedActual').textContent=point.actual_future_speed_kt===null
        ?'Not available':`${point.actual_future_speed_kt.toFixed(1)} kt`;
    }
    function enableGpsOverlayControls() {
      const slider=document.getElementById('timeSlider');
      const playButton=document.getElementById('playButton');
      slider.max=gpsOverlay.length - 1;
      document.getElementById('gpsMetrics').style.display='block';
      if (tracker) {
        overlayMarker.setStyle({opacity:0,fillOpacity:0});
        overlayProjection.setStyle({color:'#d9473f'});
        setTicks(gpsOverlay.length, (i) => new Date(gpsOverlay[i].time_epoch*1000).toLocaleTimeString('en-GB',
          {timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit'}));
      }
      slider.addEventListener('input',() => {
        overlayGpsPlaying=false;
        playButton.textContent='PLAY';
        renderGpsOverlay(slider.value);
      });
      playButton.addEventListener('click',() => {
        overlayGpsPlaying=!overlayGpsPlaying;
        playButton.textContent=overlayGpsPlaying?'PAUSE':'PLAY';
      });
      setInterval(() => {
        if (!overlayGpsPlaying) return;
        renderGpsOverlay((overlayGpsIndex+1)%gpsOverlay.length);
      },350);
      playButton.textContent='PLAY';
      renderGpsOverlay(overlayGpsIndex);
    }

    if (gpsMode || locationOnly) document.getElementById('tbOverlay').style.display = 'none';
    if (locationOnly && !gpsOverlay.length) document.getElementById('timeline').style.display = 'none';
    if (gpsMode) {
      const slider = document.getElementById('timeSlider');
      const timeLabel = document.getElementById('timeLabel');
      const hourLabel = document.getElementById('hourLabel');
      const playButton = document.getElementById('playButton');
      const readout = document.getElementById('readout');
      const gpsMetrics = document.getElementById('gpsMetrics');
      const trail = L.layerGroup().addTo(map);
      const projection = L.polyline([], {color:'#ff6900',weight:3,dashArray:'7 6'}).addTo(map);
      const current = L.circleMarker([0,0], {radius:9,color:'#fff',weight:2,fillColor:'#071c2c',fillOpacity:1}).addTo(map);
      const predicted = L.circleMarker([0,0], {radius:7,color:'#fff',weight:2,fillColor:'#ff6900',fillOpacity:1}).addTo(map);
      let gpsIndex = Math.min(Math.max(0,field.start_frame ?? 0),gpsTrack.length - 1);
      let gpsPlaying = field.autoplay ?? false;
      slider.max = gpsTrack.length - 1;
      document.getElementById('layerTitle').textContent='ILCA 7 · GPS MOVEMENT REPLAY';
      if (tracker) {
        current.setStyle({opacity:0,fillOpacity:0});
        projection.setStyle({color:'#d9473f'});
        setTicks(gpsTrack.length, (i) => new Date(gpsTrack[i].time_epoch*1000).toLocaleTimeString('en-GB',
          {timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit'}));
      }
      setSpeedLegend();
      gpsMetrics.style.display='block';

      function renderGps(index) {
        gpsIndex=Math.max(0,Math.min(gpsTrack.length - 1,Number(index)));
        slider.value=gpsIndex;
        trail.clearLayers();
        for (let i=1;i<=gpsIndex;i++) {
          const colour=gpsTrack[i].colour;
          L.polyline([[gpsTrack[i-1].lat,gpsTrack[i-1].lng],[gpsTrack[i].lat,gpsTrack[i].lng]],
            {color:`rgb(${colour.join(',')})`,weight:5,opacity:.95}).addTo(trail)
            .bindTooltip(`${gpsTrack[i].speed_kt.toFixed(1)} kt`);
        }
        const point=gpsTrack[gpsIndex];
        placeBoat(gpsTrack, gpsIndex);
        current.setLatLng([point.lat,point.lng]).bindTooltip(`Current: ${point.speed_kt.toFixed(1)} kt`);
        predicted.setLatLng([point.predicted_lat,point.predicted_lng])
          .bindTooltip(`Predicted: ${point.predicted_speed_kt.toFixed(1)} kt`);
        projection.setLatLngs([[point.lat,point.lng],[point.predicted_lat,point.predicted_lng]]);
        const timestamp=new Date(point.time_epoch*1000).toLocaleTimeString('en-US', {
          timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',second:'2-digit'
        });
        timeLabel.textContent=`GPS replay · ${timestamp}`;
        hourLabel.textContent=`${gpsIndex+1}/${gpsTrack.length}`;
        readout.textContent='Recorded GPS route · simulated 30-second projection';
        document.getElementById('gpsSpeedNow').textContent=`${point.speed_kt.toFixed(1)} kt`;
        document.getElementById('gpsSpeedPredicted').textContent=`${point.predicted_speed_kt.toFixed(1)} kt`;
        document.getElementById('gpsSpeedRange').textContent=
          `${point.prediction_low_kt.toFixed(1)}–${point.prediction_high_kt.toFixed(1)} kt`;
        document.getElementById('gpsSpeedActual').textContent=point.actual_future_speed_kt===null
          ?'Not available':`${point.actual_future_speed_kt.toFixed(1)} kt`;
      }
      slider.addEventListener('input',() => {gpsPlaying=false;playButton.textContent='PLAY';renderGps(slider.value);});
      playButton.addEventListener('click',() => {gpsPlaying=!gpsPlaying;playButton.textContent=gpsPlaying?'PAUSE':'PLAY';});
      setInterval(() => {if (!gpsPlaying) return;renderGps((gpsIndex+1)%gpsTrack.length);},350);
      playButton.textContent=gpsPlaying?'PAUSE':'PLAY';
      renderGps(gpsIndex);
    } else if (locationOnly) {
      if (gpsOverlay.length) {
        document.getElementById('layerTitle').textContent='SAILING AREA · GPS MOVEMENT REPLAY';
        setSpeedLegend();
        enableGpsOverlayControls();
      } else {
        document.querySelector('.hud').style.display='none';
        document.querySelector('.legend').style.display='none';
        document.getElementById('readout').style.display='none';
      }
    } else {

    const scalarCanvas = L.DomUtil.create('canvas', 'scalar-canvas', map.getPanes().overlayPane);
    const scalarContext = scalarCanvas.getContext('2d');
    const canvas = L.DomUtil.create('canvas', 'current-canvas', map.getPanes().overlayPane);
    const context = canvas.getContext('2d');
    const slider = document.getElementById('timeSlider');
    const timeLabel = document.getElementById('timeLabel');
    const hourLabel = document.getElementById('hourLabel');
    const playButton = document.getElementById('playButton');
    const readout = document.getElementById('readout');
    layers.forEach((layer) => {
      layer.min = Number(layer.minimum_value ?? 0);
      layer.max = Number(layer.maximum_value ?? 0);
      layer.rgb = layer.color || [97, 229, 220];
      layer.particles = [];
    });
    document.getElementById('layerTitle').textContent =
      `${layers.map((layer) => layer.title).join(' + ')} ${multi ? 'OVERLAY' : 'FIELD'}`.toUpperCase();
    function renderOverlayPanel() {
      $('tiles').innerHTML = layers.map((layer, i) => {
        const [r, g, b] = layer.rgb;
        return `<button class="tile ${T.hidden.has(i) ? '' : 'on'}" data-i="${i}"><svg viewBox="0 0 24 24">${ICONS[layer.title] || ICONS.Waves}</svg>` +
          `<span><i style="background:rgb(${r},${g},${b})"></i>${layer.title}</span><small>(${layer.unit})</small></button>`;
      }).join('');
      $('tiles').querySelectorAll('.tile').forEach((tile) => tile.addEventListener('click', () => {
        const i = Number(tile.dataset.i);
        T.hidden.has(i) ? T.hidden.delete(i) : T.hidden.add(i);  // several on at once = overlapping arrows
        renderOverlayPanel();
        fieldDirty = true;
      }));
      $('tpLegend').innerHTML = document.getElementById('legend').innerHTML + '<div class="tp-src">Data provided by Open-Meteo</div>';
    }
    if (tracker && !gpsOverlay.length) {
      setTicks(frames.length, (i) => (frames[i].time.split('T')[1] || `${i}:00`));
    }
    fieldDirtyHook = () => { fieldDirty = true; };
    // Single layer: the classic speed ramp. Several layers: each keeps its own hue, brightness = magnitude.
    document.getElementById('legend').innerHTML = layers.map((layer) => {
      const [r, g, b] = layer.rgb;
      const gradient = multi
        ? `linear-gradient(90deg, rgba(${r},${g},${b},.3), rgb(${r},${g},${b}))`
        : 'linear-gradient(90deg,#61e5dc,#b6e94b,#ffc247,#ff6b46)';
      const swatch = multi ? `<i class="swatch" style="background:rgb(${r},${g},${b})"></i>` : '';
      return `<div class="legend-row"><span>${swatch}${layer.legend_label} · ${layer.unit}</span>` +
        `<div class="gradient" style="background:${gradient}"></div>` +
        `<div class="legend-values"><span>${layer.min.toFixed(1)}</span><span>${layer.max.toFixed(1)}</span></div></div>`;
    }).join('');
    if (gpsMode || gpsOverlay.length) {
      document.getElementById('gpsMetrics').style.display = 'block';
    }
    if (tracker && !gpsOverlay.length) {
      renderOverlayPanel();
      if (window.innerHeight >= 520) openPanel('overlayPanel');  // small maps start with the panel closed
    }
    slider.max = gpsOverlay.length ? gpsOverlay.length - 1 : Math.max(0, frames.length - 1);
    slider.value = gpsOverlay.length ? overlayGpsIndex : frameIndex;

    function formatTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value.replace('T', ' ');
      return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
    }
    function updateTimeUi() {
      const timestamp = frames[frameIndex]?.time || '';
      timeLabel.textContent = formatTime(timestamp);
      if (tracker) {
        const [day, clock] = timestamp.split('T');
        const date = new Date(`${day}T00:00:00`);
        if (clock && !Number.isNaN(date.getTime())) {
          timeLabel.textContent = `${date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} ${clock} local`;
        }
      }
      hourLabel.textContent = timestamp.includes('T') ? timestamp.split('T')[1] : `${frameIndex}:00`;
      slider.value = frameIndex;
    }
    if (!gpsOverlay.length) updateTimeUi();

    function colorForValue(layer, value, opacity = .9) {
      const range = Math.max(.0001, layer.max - layer.min);
      const ratio = Math.max(0, Math.min(1, (value - layer.min) / range));
      if (multi) {
        const [r, g, b] = layer.rgb;
        return `rgba(${r},${g},${b},${opacity * (.3 + .7 * ratio)})`;
      }
      const stops = [[97,229,220],[182,233,75],[255,194,71],[255,107,70]];
      const scaled = ratio * (stops.length - 1);
      const index = Math.min(stops.length - 2, Math.floor(scaled));
      const blend = scaled - index;
      const color = stops[index].map((value, channel) => Math.round(value + (stops[index + 1][channel] - value) * blend));
      return `rgba(${color[0]},${color[1]},${color[2]},${opacity})`;
    }

    function sampleField(latitude, longitude, layer) {
      if (latitude < bounds.south || latitude > bounds.north || longitude < bounds.west || longitude > bounds.east) return null;
      const x = (longitude - bounds.west) / (bounds.east - bounds.west) * (columns - 1);
      const y = (latitude - bounds.south) / (bounds.north - bounds.south) * (rows - 1);
      const x0 = Math.max(0, Math.min(columns - 2, Math.floor(x)));
      const y0 = Math.max(0, Math.min(rows - 2, Math.floor(y)));
      const tx = x - x0;
      const ty = y - y0;
      const indices = [y0 * columns + x0, y0 * columns + x0 + 1, (y0 + 1) * columns + x0, (y0 + 1) * columns + x0 + 1];
      const weights = [(1-tx)*(1-ty), tx*(1-ty), (1-tx)*ty, tx*ty];
      const frame = layer.frames[Math.min(frameIndex, layer.frames.length - 1)];
      let u = 0, v = 0, value = 0, weight = 0;
      indices.forEach((index, position) => {
        const hasValue = frame.value[index] !== null;
        const hasVector = layer.mode === 'scalar' || (frame.u[index] !== null && frame.v[index] !== null);
        if (hasValue && hasVector) {
          if (layer.mode !== 'scalar') {
            u += frame.u[index] * weights[position];
            v += frame.v[index] * weights[position];
          }
          value += frame.value[index] * weights[position];
          weight += weights[position];
        }
      });
      if (weight < .45) return null;
      return { u: u / weight, v: v / weight, value: value / weight };
    }

    function resetParticle(particle, layer, randomAge = true) {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        particle.lat = bounds.south + Math.random() * (bounds.north - bounds.south);
        particle.lon = bounds.west + Math.random() * (bounds.east - bounds.west);
        if (sampleField(particle.lat, particle.lon, layer)) break;
      }
      particle.age = randomAge ? Math.floor(Math.random() * 100) : 0;
      return particle;
    }
    function resizeCanvas() {
      const size = map.getSize();
      const ratio = Math.min(2, window.devicePixelRatio || 1);
      [scalarCanvas, canvas].forEach((target) => {
        target.width = size.x * ratio;
        target.height = size.y * ratio;
        target.style.width = `${size.x}px`;
        target.style.height = `${size.y}px`;
      });
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      scalarContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      const particleCount = Math.max(350, Math.min(1100, Math.round(size.x * size.y / 750)));
      const perLayer = Math.max(300, Math.round(particleCount / layers.length));
      layers.forEach((layer) => {
        layer.particles = layer.mode === 'scalar'
          ? []
          : Array.from({ length: perLayer }, () => resetParticle({}, layer, true));
      });
      context.clearRect(0, 0, size.x, size.y);
      scalarContext.clearRect(0, 0, size.x, size.y);
      fieldDirty = true;
    }
    let fieldDirty = true;
    resizeCanvas();

    function drawScalarField() {
      const size = map.getSize();
      scalarContext.clearRect(0, 0, size.x, size.y);
      layers.filter((layer, i) => layer.mode === 'scalar' && !T.hidden.has(i)).forEach((layer) => {
        const frame = layer.frames[Math.min(frameIndex, layer.frames.length - 1)];
        for (let row = 0; row < rows - 1; row += 1) {
          for (let column = 0; column < columns - 1; column += 1) {
            const indices = [row * columns + column, row * columns + column + 1, (row + 1) * columns + column, (row + 1) * columns + column + 1];
            const values = indices.map(index => frame.value[index]).filter(value => value !== null);
            if (!values.length) continue;
            const value = values.reduce((sum, item) => sum + item, 0) / values.length;
            const topLeft = map.latLngToContainerPoint([latitudes[row + 1], longitudes[column]]);
            const bottomRight = map.latLngToContainerPoint([latitudes[row], longitudes[column + 1]]);
            scalarContext.fillStyle = colorForValue(layer, value, .58);
            scalarContext.fillRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x + 1, bottomRight.y - topLeft.y + 1);
          }
        }
      });
      fieldDirty = false;
    }

    function animate(now) {
      const size = map.getSize();
      if (playing && now - lastFrameAdvance > 1500 && frames.length > 1) {
        frameIndex = (frameIndex + 1) % frames.length;
        lastFrameAdvance = now;
        updateTimeUi();
        fieldDirty = true;
      }
      if (fieldDirty) drawScalarField();

      const vectorLayers = T.showParticles
        ? layers.filter((layer, i) => layer.mode !== 'scalar' && !T.hidden.has(i)) : [];
      if (!vectorLayers.length) {
        context.clearRect(0, 0, size.x, size.y);
        requestAnimationFrame(animate);
        return;
      }

      context.globalCompositeOperation = 'destination-out';
      context.fillStyle = 'rgba(0,0,0,.075)';  // tracker: short white streaks
      context.fillRect(0, 0, size.x, size.y);
      context.globalCompositeOperation = 'source-over';
      context.lineWidth = 1.15;

      vectorLayers.forEach((layer) => layer.particles.forEach((particle) => {
        const vector = sampleField(particle.lat, particle.lon, layer);
        if (!vector || vector.value < .001 || particle.age > 115) {
          resetParticle(particle, layer, false);
          return;
        }
        const previous = map.latLngToContainerPoint([particle.lat, particle.lon]);
        const visualScale = .00155 * (layer.visual_scale ?? 1);
        const latitudeRadians = particle.lat * Math.PI / 180;
        particle.lat += vector.v * visualScale;
        particle.lon += vector.u * visualScale / Math.max(.35, Math.cos(latitudeRadians));
        particle.age += 1;
        const next = map.latLngToContainerPoint([particle.lat, particle.lon]);
        if (next.x < 0 || next.y < 0 || next.x > size.x || next.y > size.y) {
          resetParticle(particle, layer, false);
          return;
        }
        context.beginPath();
        context.moveTo(previous.x, previous.y);
        context.lineTo(next.x, next.y);
        context.strokeStyle = colorForValue(layer, vector.value);
        context.stroke();
      }));
      requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);

    map.on('move zoom', () => resizeCanvas());
    map.on('resize', () => {
      scopeMapToLoadedData();
      resizeCanvas();
    });

    // Value (and direction, for vector layers) of every layer at one point.
    function samplesAt(latlng) {
      return layers
        .map((layer) => ({ layer, sample: sampleField(latlng.lat, latlng.lng, layer) }))
        .filter((entry) => entry.sample)
        .map(({ layer, sample }) => ({
          layer,
          value: `${sample.value.toFixed(2)} ${layer.unit}`,
          direction: layer.mode === 'scalar' ? null : (Math.atan2(sample.u, sample.v) * 180 / Math.PI + 360) % 360,
        }));
    }
    map.on('mousemove', (event) => {
      const samples = samplesAt(event.latlng);
      if (!samples.length) { readout.textContent = 'No model data at this point'; return; }
      const position = `${event.latlng.lat.toFixed(3)}°, ${event.latlng.lng.toFixed(3)}°`;
      const line = (entry) => `${entry.value}${entry.direction === null ? '' : `  ·  ${entry.direction.toFixed(0)}°`}`;
      readout.textContent = multi
        ? [position, ...samples.map((entry) => `${entry.layer.title}: ${line(entry)}`)].join('\n')
        : `${position}  ·  ${line(samples[0])}`;
    });
    map.on('click', (event) => {
      const samples = samplesAt(event.latlng);
      if (!samples.length) return;
      const content = samples.map((entry) => {
        const [r, g, b] = entry.layer.rgb;
        const dot = multi ? `<span style="color:rgb(${r},${g},${b})">●</span> ${entry.layer.title}: ` : '';
        const direction = entry.direction === null ? '' : `<br>${entry.direction.toFixed(0)}° toward`;
        return `${dot}<b>${entry.value}</b>${direction}`;
      }).join('<br>');
      L.popup().setLatLng(event.latlng)
        .setContent(`${content}<br>${formatTime(frames[frameIndex].time)}`).openOn(map);
    });
    if (gpsOverlay.length) {
      playing=false;
      setSpeedLegend();
      enableGpsOverlayControls();
    } else {
      playButton.textContent = playing ? 'PAUSE' : 'PLAY';
      slider.addEventListener('input', () => { frameIndex = Number(slider.value); lastFrameAdvance = performance.now(); fieldDirty = true; updateTimeUi(); });
      playButton.addEventListener('click', () => {
        playing = !playing;
        playButton.textContent = playing ? 'PAUSE' : 'PLAY';
        lastFrameAdvance = performance.now();
      });
    }
    }
  </script>
</body>
</html>
"""
