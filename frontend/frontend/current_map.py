"""Leaflet/canvas renderer for dynamic regional marine fields."""

import json

import streamlit as st


def render_current_map(payload, height=650):
    """Render an animated vector field or scalar colour field."""
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


CURRENT_MAP_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
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
    .readout {
      position: absolute; z-index: 800; left: 16px; bottom: 20px; color: #bcd0d3; background: rgba(3,18,27,.78);
      border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 8px 10px; font: 600 10px/1.45 ui-monospace, monospace;
    }
    .leaflet-popup-content-wrapper, .leaflet-popup-tip { background: #071c27; color: #eaf8f6; }
    .leaflet-popup-content { font: 600 11px/1.6 ui-monospace, monospace; }
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
  <div class="legend"><span id="legendTitle">VALUE</span><div class="gradient"></div><div class="legend-values"><span id="legendMin">0</span><span id="legendMax">1.0</span></div></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const field = __CURRENT_DATA__;
    const bounds = field.bounds;
    const rows = field.rows;
    const columns = field.columns;
    const latitudes = field.latitudes;
    const longitudes = field.longitudes;
    const frames = field.frames;
    let frameIndex = Math.max(0, frames.length - 1);
    let playing = true;
    let lastFrameAdvance = performance.now();
    function getLoadedDataBounds() {
      let south = Infinity;
      let north = -Infinity;
      let west = Infinity;
      let east = -Infinity;

      frames.forEach((frame) => {
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
      });

      if (![south, north, west, east].every(Number.isFinite)) {
        return L.latLngBounds(
          [bounds.south, bounds.west],
          [bounds.north, bounds.east]
        );
      }

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
      return L.latLngBounds([south, west], [north, east]);
    }

    const loadedDataBounds = getLoadedDataBounds();
    const map = L.map('map', {
      zoomControl: true,
      preferCanvas: true,
      zoomSnap: 0.01,
      zoomDelta: 0.5,
      minZoom: 1,
      maxZoom: 12
    });
    let fallbackTilesLoaded = false;
    const oceanTiles = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 12,
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
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 12, pane: 'overlayPane' }
    ).addTo(map);

    // Leaflet's fitBounds uses a "contain" fit: it shows every edge of the
    // data rectangle, but leaves empty bands whenever its aspect ratio differs
    // from the map panel. Use the inverse, "cover" fit so every visible part
    // of the map falls within the extent of the loaded model data.
    let dataCoverZoom = map.getMinZoom();
    function getDataCoverZoom() {
      const size = map.getSize();
      const northWest = map.project(loadedDataBounds.getNorthWest(), 0);
      const southEast = map.project(loadedDataBounds.getSouthEast(), 0);
      const dataWidth = Math.max(1, Math.abs(southEast.x - northWest.x));
      const dataHeight = Math.max(1, Math.abs(southEast.y - northWest.y));
      const scale = Math.max(size.x / dataWidth, size.y / dataHeight);
      return Math.min(
        map.getMaxZoom(),
        Math.max(map.getMinZoom(), Math.log2(scale))
      );
    }
    function scopeMapToLoadedData(force = false) {
      const wasAtDataExtent = Math.abs(map.getZoom() - dataCoverZoom) < 0.05;
      dataCoverZoom = getDataCoverZoom();
      if (force || wasAtDataExtent) {
        map.setView(loadedDataBounds.getCenter(), dataCoverZoom, { animate: false });
      }
    }
    scopeMapToLoadedData(true);

    const scalarCanvas = L.DomUtil.create('canvas', 'scalar-canvas', map.getPanes().overlayPane);
    const scalarContext = scalarCanvas.getContext('2d');
    const canvas = L.DomUtil.create('canvas', 'current-canvas', map.getPanes().overlayPane);
    const context = canvas.getContext('2d');
    const slider = document.getElementById('timeSlider');
    const timeLabel = document.getElementById('timeLabel');
    const hourLabel = document.getElementById('hourLabel');
    const playButton = document.getElementById('playButton');
    const readout = document.getElementById('readout');
    const minimumValue = Number(field.minimum_value ?? 0);
    const maximumValue = Number(field.maximum_value ?? 0);
    document.getElementById('layerTitle').textContent = `${field.title} FIELD`.toUpperCase();
    document.getElementById('legendTitle').textContent = `${field.legend_label} · ${field.unit}`;
    document.getElementById('legendMin').textContent = minimumValue.toFixed(1);
    document.getElementById('legendMax').textContent = maximumValue.toFixed(1);
    slider.max = Math.max(0, frames.length - 1);
    slider.value = frameIndex;

    function formatTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value.replace('T', ' ');
      return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
    }
    function updateTimeUi() {
      const timestamp = frames[frameIndex]?.time || '';
      timeLabel.textContent = formatTime(timestamp);
      hourLabel.textContent = timestamp.includes('T') ? timestamp.split('T')[1] : `${frameIndex}:00`;
      slider.value = frameIndex;
    }
    updateTimeUi();

    function colorForValue(value, opacity = .9) {
      const range = Math.max(.0001, maximumValue - minimumValue);
      const ratio = Math.max(0, Math.min(1, (value - minimumValue) / range));
      const stops = [[97,229,220],[182,233,75],[255,194,71],[255,107,70]];
      const scaled = ratio * (stops.length - 1);
      const index = Math.min(stops.length - 2, Math.floor(scaled));
      const blend = scaled - index;
      const color = stops[index].map((value, channel) => Math.round(value + (stops[index + 1][channel] - value) * blend));
      return `rgba(${color[0]},${color[1]},${color[2]},${opacity})`;
    }

    function sampleField(latitude, longitude) {
      if (latitude < bounds.south || latitude > bounds.north || longitude < bounds.west || longitude > bounds.east) return null;
      const x = (longitude - bounds.west) / (bounds.east - bounds.west) * (columns - 1);
      const y = (latitude - bounds.south) / (bounds.north - bounds.south) * (rows - 1);
      const x0 = Math.max(0, Math.min(columns - 2, Math.floor(x)));
      const y0 = Math.max(0, Math.min(rows - 2, Math.floor(y)));
      const tx = x - x0;
      const ty = y - y0;
      const indices = [y0 * columns + x0, y0 * columns + x0 + 1, (y0 + 1) * columns + x0, (y0 + 1) * columns + x0 + 1];
      const weights = [(1-tx)*(1-ty), tx*(1-ty), (1-tx)*ty, tx*ty];
      const frame = frames[frameIndex];
      let u = 0, v = 0, value = 0, weight = 0;
      indices.forEach((index, position) => {
        const hasValue = frame.value[index] !== null;
        const hasVector = field.mode === 'scalar' || (frame.u[index] !== null && frame.v[index] !== null);
        if (hasValue && hasVector) {
          if (field.mode !== 'scalar') {
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

    let particles = [];
    function resetParticle(particle, randomAge = true) {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        particle.lat = bounds.south + Math.random() * (bounds.north - bounds.south);
        particle.lon = bounds.west + Math.random() * (bounds.east - bounds.west);
        if (sampleField(particle.lat, particle.lon)) break;
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
      particles = field.mode === 'scalar' ? [] : Array.from({ length: particleCount }, () => resetParticle({}, true));
      context.clearRect(0, 0, size.x, size.y);
      scalarContext.clearRect(0, 0, size.x, size.y);
      fieldDirty = true;
    }
    let fieldDirty = true;
    resizeCanvas();

    function drawScalarField() {
      const size = map.getSize();
      scalarContext.clearRect(0, 0, size.x, size.y);
      const frame = frames[frameIndex];
      for (let row = 0; row < rows - 1; row += 1) {
        for (let column = 0; column < columns - 1; column += 1) {
          const indices = [row * columns + column, row * columns + column + 1, (row + 1) * columns + column, (row + 1) * columns + column + 1];
          const values = indices.map(index => frame.value[index]).filter(value => value !== null);
          if (!values.length) continue;
          const value = values.reduce((sum, item) => sum + item, 0) / values.length;
          const topLeft = map.latLngToContainerPoint([latitudes[row + 1], longitudes[column]]);
          const bottomRight = map.latLngToContainerPoint([latitudes[row], longitudes[column + 1]]);
          scalarContext.fillStyle = colorForValue(value, .58);
          scalarContext.fillRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x + 1, bottomRight.y - topLeft.y + 1);
        }
      }
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

      if (field.mode === 'scalar') {
        context.clearRect(0, 0, size.x, size.y);
        if (fieldDirty) drawScalarField();
        requestAnimationFrame(animate);
        return;
      }

      scalarContext.clearRect(0, 0, size.x, size.y);
      context.globalCompositeOperation = 'destination-out';
      context.fillStyle = 'rgba(0,0,0,.075)';
      context.fillRect(0, 0, size.x, size.y);
      context.globalCompositeOperation = 'source-over';
      context.lineWidth = 1.15;

      particles.forEach((particle) => {
        const vector = sampleField(particle.lat, particle.lon);
        if (!vector || vector.value < .001 || particle.age > 115) {
          resetParticle(particle, false);
          return;
        }
        const previous = map.latLngToContainerPoint([particle.lat, particle.lon]);
        const visualScale = .00155;
        const latitudeRadians = particle.lat * Math.PI / 180;
        particle.lat += vector.v * visualScale;
        particle.lon += vector.u * visualScale / Math.max(.35, Math.cos(latitudeRadians));
        particle.age += 1;
        const next = map.latLngToContainerPoint([particle.lat, particle.lon]);
        if (next.x < 0 || next.y < 0 || next.x > size.x || next.y > size.y) {
          resetParticle(particle, false);
          return;
        }
        context.beginPath();
        context.moveTo(previous.x, previous.y);
        context.lineTo(next.x, next.y);
        context.strokeStyle = colorForValue(vector.value);
        context.stroke();
      });
      requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);

    map.on('move zoom', () => resizeCanvas());
    map.on('resize', () => {
      scopeMapToLoadedData();
      resizeCanvas();
    });
    map.on('mousemove', (event) => {
      const sample = sampleField(event.latlng.lat, event.latlng.lng);
      if (!sample) { readout.textContent = 'No model data at this point'; return; }
      const position = `${event.latlng.lat.toFixed(3)}°, ${event.latlng.lng.toFixed(3)}°`;
      if (field.mode === 'scalar') {
        readout.textContent = `${position}  ·  ${sample.value.toFixed(2)} ${field.unit}`;
      } else {
        const direction = (Math.atan2(sample.u, sample.v) * 180 / Math.PI + 360) % 360;
        readout.textContent = `${position}  ·  ${sample.value.toFixed(2)} ${field.unit}  ·  ${direction.toFixed(0)}°`;
      }
    });
    map.on('click', (event) => {
      const sample = sampleField(event.latlng.lat, event.latlng.lng);
      if (!sample) return;
      let content = `<b>${sample.value.toFixed(2)} ${field.unit}</b>`;
      if (field.mode !== 'scalar') {
        const direction = (Math.atan2(sample.u, sample.v) * 180 / Math.PI + 360) % 360;
        content += `<br>${direction.toFixed(0)}° toward`;
      }
      content += `<br>${formatTime(frames[frameIndex].time)}`;
      L.popup().setLatLng(event.latlng).setContent(content).openOn(map);
    });
    slider.addEventListener('input', () => { frameIndex = Number(slider.value); lastFrameAdvance = performance.now(); fieldDirty = true; updateTimeUi(); });
    playButton.addEventListener('click', () => {
      playing = !playing;
      playButton.textContent = playing ? 'PAUSE' : 'PLAY';
      lastFrameAdvance = performance.now();
    });
  </script>
</body>
</html>
"""
