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
    .finish-panel { display:none;position:absolute;z-index:800;right:14px;top:190px;width:310px;
      color:#eaf8f6;background:rgba(3,18,27,.92);border:1px solid #7dd1d038;border-radius:12px;padding:12px; }
    .race-lanes {position:relative;display:grid;grid-template-columns:repeat(4,1fr);height:250px;
      margin-top:12px;background:linear-gradient(180deg,#164b4b,#0d383c);border-radius:8px;overflow:hidden;}
    .race-lanes::after {content:"FIRST BUOY";position:absolute;left:0;right:0;bottom:31px;
      border-top:3px solid #ffbd6e;color:#ffd7a7;text-align:center;font:700 9px ui-monospace,monospace;
      letter-spacing:.1em;padding-top:3px;pointer-events:none;}
    .race-lane {position:relative;border-right:1px solid #ffffff26;text-align:center;}
    .race-lane:last-child {border-right:0;}
    .race-lane-name {position:absolute;top:7px;left:2px;right:2px;font:700 10px ui-monospace,monospace;}
    .race-lane-line {position:absolute;top:33px;bottom:48px;left:50%;border-left:2px dashed #ffffff55;}
    .race-boat {position:absolute;left:50%;transform:translate(-50%,-50%);font-size:25px;
      filter:drop-shadow(0 2px 2px #001);transition:top .25s linear;}
    .race-boat.stale {opacity:.55;}
    .race-lane-value {position:absolute;bottom:5px;left:1px;right:1px;font:600 9px ui-monospace,monospace;}
    .finish-row {padding:8px 0;border-bottom:1px solid #ffffff18;font-size:11px;}
    .finish-row strong {float:right;font-size:13px;}
    .finish-row.agent {color:#ffb676;}
    .finish-note {font-size:10px;color:#b9cdd0;line-height:1.4;margin-top:7px;}
    @media(max-width:600px) {.gps-metrics{display:none!important}.finish-panel{top:125px;width:190px;right:10px;}}
    body.race-replay .hud {top:auto;bottom:18px;left:16px;width:calc(100% - 32px);}
    body.race-replay .play {background:#2bd4a4;color:#071c2c;border:0;padding:11px 18px;
      font:700 14px ui-sans-serif,system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.35);}
    body.race-replay .play:hover {background:#75ebc9;}
    body.race-replay .readout, body.race-replay .legend {display:none;}
    body.race-replay .finish-panel {width:280px;top:185px;}
    body.race-replay .race-lanes {height:200px;}
    body.race-replay .race-lane-value {font-size:9px;}
    @media(max-width:600px) {body.race-replay .finish-panel{top:16px;width:190px;}
      body.race-replay .race-lanes{height:180px;}}
    .readout {
      position: absolute; z-index: 800; left: 16px; bottom: 20px; color: #bcd0d3; background: rgba(3,18,27,.78);
      border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 8px 10px; font: 600 10px/1.45 ui-monospace, monospace;
      white-space: pre;
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
      <button class="play" id="playButton" type="button" aria-label="Play replay">▶ Play</button>
    </div>
    <div class="slider-row"><input id="timeSlider" aria-label="Replay timeline" type="range" min="0" step="1"><span class="hour" id="hourLabel">—</span></div>
  </div>
  <div class="readout" id="readout">Move over the map · click for details</div>
  <div class="legend" id="legend"></div>
  <div class="gps-metrics" id="gpsMetrics">
    <div class="gps-metrics-title">FOCUS BOAT · SPEED FORECAST</div>
    <div class="gps-metric"><span>Speed now</span><strong id="gpsSpeedNow">—</strong></div>
    <div class="gps-metric"><span>In 30 seconds</span><strong id="gpsSpeedPredicted">—</strong></div>
    <div class="gps-metric"><span>80% range</span><strong id="gpsSpeedRange">—</strong></div>
    <div class="gps-metric"><span>Replay actual</span><strong id="gpsSpeedActual">—</strong></div>
  </div>

  <div class="finish-panel" id="finishPanel" aria-live="polite">
    <div class="gps-metrics-title">DISTANCE TO FIRST BUOY</div>
    <div id="finishRace" class="finish-note"></div><div id="finishRows"></div>
    <div class="finish-note" id="comparisonNote">Estimated GPS progress · faded boat = old GPS fix</div>
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
    const selectedRace=(field.race_progress || [])[0];
    const scopedReplay=gpsMode && Boolean(field.replay_phase) && Boolean(selectedRace);
    const focusSynthetic=scopedReplay && field.replay_phase==='first_beat' &&
      selectedRace.tracks.some(track=>track.synthetic && track.name===field.focus_boat);
    if(scopedReplay)document.body.classList.add('race-replay');
    const raceColours=['#65d5d1','#c4adff','#ffd36a','#ff9f50'];
    const comparisonTracks=new Map();
    const replayTimes=scopedReplay?[...new Set([selectedRace.gun,
      ...visibleTracks(selectedRace).flatMap(track=>track.points.map(point=>point[0])),
      ...visibleTracks(selectedRace).filter(track=>track.synthetic).flatMap(track=>
        Array.from({length:Math.ceil((track.arrival-track.recorded_until)/5)},
          (_,index)=>Math.min(track.arrival,track.recorded_until+(index+1)*5))),
      ...gpsTrack.map(point=>point.time_epoch)])].sort((a,b)=>a-b):
      gpsTrack.map(point=>point.time_epoch);
    function visibleTracks(race){
      return race.tracks.filter(track=>!track.agent || field.compare_agent!==false)
        .map(track=>({...track,points:field.replay_phase==='full_race'?(track.full_points||track.points):track.points}));
    }
    function elapsed(timestamp,gun){
      const seconds=Math.max(0,Math.floor(timestamp-gun));
      return `+${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
    }
    function raceFix(track,timestamp){
      const points=track.points;
      let lo=0,hi=points.length;
      while(lo<hi){const mid=(lo+hi)>>1;if(points[mid][0]<timestamp)lo=mid+1;else hi=mid;}
      const after=points[lo],before=points[lo-1];
      if(after && after[0]===timestamp)return {position:[after[1],after[2]],age:0,index:lo};
      if(before && after && (track.synthetic || after[0]-before[0]<=30)){
        const f=(timestamp-before[0])/(after[0]-before[0]);
        return {position:[before[1]+f*(after[1]-before[1]),before[2]+f*(after[2]-before[2])],age:0,index:lo-1};
      }
      return before?{position:[before[1],before[2]],age:timestamp-before[0],index:lo-1}:null;
    }
    function firstBeatLanes(race,timestamp,container){
      const lanes=document.createElement('div');lanes.className='race-lanes';
      lanes.style.gridTemplateColumns=`repeat(${visibleTracks(race).length},1fr)`;
      const target=L.latLng(race.mark1);
      visibleTracks(race).forEach((track,number)=>{
        const lane=document.createElement('div');lane.className='race-lane';
        const name=document.createElement('div');name.className='race-lane-name';
        name.textContent=track.agent?'AGENT':`${number+1}. ${track.name.split(' ')[0].toUpperCase()}`;
        name.style.color=raceColours[number];
        const line=document.createElement('div');line.className='race-lane-line';
        const boat=document.createElement('div');boat.className='race-boat';boat.textContent='⛵';
        const value=document.createElement('div');value.className='race-lane-value';
        const fix=raceFix(track,timestamp),points=track.points;
        if(fix && points.length){
          const first=points.find(point=>point[0]>=race.gun)||points[0];
          const startDistance=target.distanceTo(L.latLng(first[1],first[2]));
          let best=startDistance;
          for(let i=0;i<=fix.index;i++){
            if(points[i][0]>=race.gun)best=Math.min(best,target.distanceTo(L.latLng(points[i][1],points[i][2])));
          }
          best=Math.min(best,target.distanceTo(L.latLng(fix.position)));
          const reached=track.arrival!=null && timestamp>=track.arrival;
          const progress=reached?1:Math.max(0,Math.min(1,1-best/startDistance));
          boat.style.top=`${40+progress*112}px`;
          if(fix.age>30 && !reached && !track.synthetic){
            boat.style.display='none';
            value.textContent='GPS gap';
            value.title=`Last recorded fix ${Math.ceil(fix.age/60)} minutes ago, ${Math.round(best)} m from buoy`;
          }
          else value.textContent=reached?elapsed(track.arrival,race.gun):`${Math.round(best)} m`;
          if(reached)value.title='Estimated arrival since start';
        } else {boat.style.display='none';value.textContent='No GPS';}
        lane.append(name,line,boat,value);lanes.append(lane);
      });
      container.append(lanes);
    }
    function updateRaceProgress(timestamp) {
      const races=field.race_progress || [],panel=document.getElementById('finishPanel');
      if(!races.length)return;
      panel.style.display='block';
      const race=races.find(r=>timestamp>=r.gun && timestamp<=r.end);
      const firstBeat=race && (field.replay_phase==='first_beat' ||
        (!field.replay_phase && timestamp<=race.first_beat_end));
      panel.querySelector('.gps-metrics-title').textContent=firstBeat?'FIRST BUOY · ESTIMATED PROGRESS':'RECORDED BOATS';
      document.getElementById('finishRace').textContent=race?`Race ${race.race} · ${elapsed(timestamp,race.gun)} since start`:'Outside race replay';
      document.getElementById('comparisonNote').textContent=firstBeat
        ?(race.tracks.some(track=>track.synthetic)
          ?'Dashed segments estimate GPS gaps to the buoy · solid paths are recorded GPS'
          :'Estimated GPS progress · arrival times from start · faded boat = old fix')
        :'Recorded replay · finish times unavailable';
      const container=document.getElementById('finishRows');container.replaceChildren();
      if(!race)return;
      visibleTracks(race).forEach((track,number)=>{
        const overlay=comparisonTracks.get(track.name),fix=raceFix(track,timestamp);
        if(overlay && !fix){
          overlay.marker.setStyle({opacity:0,fillOpacity:0});
          overlay.trail.setLatLngs([]);
          overlay.estimate.setLatLngs([]);
        }
        if(overlay && fix){
          overlay.marker.setLatLng(fix.position).setStyle({opacity:fix.age>30&&!track.synthetic?0:1,
            fillOpacity:fix.age>30&&!track.synthetic?0:1});
          const points=track.points.slice(0,fix.index+1).map(p=>[p[1],p[2]]);
          if(track.synthetic){
            const recorded=track.points.filter(p=>p[0]<=track.recorded_until).map(p=>[p[1],p[2]]);
            overlay.trail.setLatLngs(timestamp<=track.recorded_until?
              [...points,fix.position]:recorded);
            overlay.estimate.setLatLngs(timestamp>track.recorded_until?
              [recorded.at(-1),fix.position]:[]);
          } else {
            points.push(fix.position);overlay.trail.setLatLngs(points);
          }
        }
      });
      if(firstBeat){firstBeatLanes(race,timestamp,container);return;}
      visibleTracks(race).forEach((track,number)=>{
        const row=document.createElement('div');row.className='finish-row';
        const name=document.createElement('span');name.textContent=track.name;name.style.color=raceColours[number];
        const value=document.createElement('strong'),fix=raceFix(track,timestamp);
        value.textContent=!fix?'No fix':fix.age>30?'GPS gap':'Recorded';
        row.append(name,value);container.append(row);
      });
    }

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
        if(scopedReplay){
          selectedRace.start_line.forEach(point=>trackBounds.extend(point));
          trackBounds.extend(selectedRace.mark1);
          visibleTracks(selectedRace).forEach(track=>track.points.forEach(p=>trackBounds.extend([p[1],p[2]])));
          if(field.replay_phase==='full_race'){
            (selectedRace.other_marks||[]).forEach(point=>trackBounds.extend(point));
            if(selectedRace.finish)trackBounds.extend(selectedRace.finish);
          }
        }
        return trackBounds.pad(.18);
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
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
      { maxNativeZoom: 12, maxZoom: 18, pane: 'overlayPane' }
    ).addTo(map);
    const locationMarker = field.location_marker;
    if (locationMarker) {
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
        if(scopedReplay){
          map.fitBounds(loadedDataBounds,{animate:false,paddingTopLeft:[35,35],
            paddingBottomRight:[window.innerWidth>600?300:200,110]});
          dataFitZoom=map.getZoom();
          return;
        }
        map.setView(loadedDataBounds.getCenter(), dataFitZoom, { animate: false });
      }
    }
    scopeMapToLoadedData(true);

    if (field.race_progress && field.race_progress.length) {
      field.race_progress.forEach(race=>{
        if(race.start_line)L.polyline(race.start_line,{color:'#fff',weight:3,dashArray:'6 4'})
          .addTo(map).bindTooltip(`Race ${race.race} · estimated start line`);
        if(scopedReplay){
          visibleTracks(race).forEach((track,number)=>{
            comparisonTracks.set(track.name,{
              trail:L.polyline([],{color:raceColours[number],weight:2,opacity:.65}).addTo(map),
              estimate:L.polyline([],{color:raceColours[number],weight:2,opacity:.8,
                dashArray:'6 6'}).addTo(map),
              marker:L.circleMarker(race.start_line[0],{radius:5,color:raceColours[number],fillColor:raceColours[number],fillOpacity:0,opacity:0})
                .addTo(map).bindTooltip(`${track.name}${track.agent?' · simulated':' · recorded'}`)
            });
          });
          if(field.replay_phase==='full_race') (race.other_marks||[]).forEach((point,index)=>
            L.circleMarker(point,{radius:5,color:'#fff',fillColor:'#ffd36a',fillOpacity:1})
              .addTo(map).bindTooltip(index===0?'Estimated second windward mark':'Estimated leeward gate'));
        }
        L.circleMarker(race.mark1,{radius:6,color:'#fff',weight:2,fillColor:'#ff6900',fillOpacity:1})
          .addTo(map).bindTooltip(`Race ${race.race} · estimated first buoy (${race.mark1_method})`);
        if(race.finish && (!scopedReplay || field.replay_phase==='full_race'))L.circleMarker(race.finish,{radius:6,color:'#fff',weight:2,fillColor:'#65d5d1',fillOpacity:1})
          .addTo(map).bindTooltip(`Race ${race.race} · estimated finish area`);
      });
    }

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
      updateRaceProgress(point.time_epoch);
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
      let gpsIndex = Math.min(Math.max(0,field.start_frame ?? 0),replayTimes.length - 1);
      let gpsPlaying = field.autoplay ?? false;
      function updatePlayButton() {
        playButton.textContent=gpsPlaying?'❚❚ Pause':'▶ Play';
        playButton.setAttribute('aria-label',gpsPlaying?'Pause replay':'Play replay');
        playButton.setAttribute('aria-pressed',String(gpsPlaying));
      }
      slider.max = replayTimes.length - 1;
      document.getElementById('layerTitle').textContent=scopedReplay
        ?`RACE ${selectedRace.race} · ${field.replay_phase==='first_beat'?'START → FIRST BUOY':'FULL RACE · ESTIMATED WINDOW'}`
        :'ILCA 7 · RECORDED GPS REPLAY';
      setSpeedLegend();
      gpsMetrics.style.display='block';

      function renderGps(index) {
        gpsIndex=Math.max(0,Math.min(replayTimes.length - 1,Number(index)));
        slider.value=gpsIndex;
        const replayTime=replayTimes[gpsIndex];
        let pointIndex=0;
        while(pointIndex<gpsTrack.length-1 && gpsTrack[pointIndex+1].time_epoch<=replayTime)pointIndex++;
        const point=gpsTrack[pointIndex];
        const hasFocus=!focusSynthetic && point.time_epoch<=replayTime && replayTime-point.time_epoch<=30;
        trail.clearLayers();
        for(let i=1;!focusSynthetic && i<=pointIndex;i++){
          if(gpsTrack[i].time_epoch>replayTime)break;
          if(gpsTrack[i].time_epoch-gpsTrack[i-1].time_epoch>30)continue;
          const colour=gpsTrack[i].colour;
          L.polyline([[gpsTrack[i-1].lat,gpsTrack[i-1].lng],[gpsTrack[i].lat,gpsTrack[i].lng]],
            {color:`rgb(${colour.join(',')})`,weight:5,opacity:.95}).addTo(trail)
            .bindTooltip(`${gpsTrack[i].speed_kt.toFixed(1)} kt`);
        }
        updateRaceProgress(replayTime);
        current.setStyle({opacity:hasFocus?1:0,fillOpacity:hasFocus?1:0});
        predicted.setStyle({opacity:hasFocus?1:0,fillOpacity:hasFocus?1:0});
        projection.setStyle({opacity:hasFocus?1:0});
        if(hasFocus){
          current.setLatLng([point.lat,point.lng]).bindTooltip(`Recorded: ${point.speed_kt.toFixed(1)} kt`);
          predicted.setLatLng([point.predicted_lat,point.predicted_lng])
            .bindTooltip(`Predicted: ${point.predicted_speed_kt.toFixed(1)} kt`);
          projection.setLatLngs([[point.lat,point.lng],[point.predicted_lat,point.predicted_lng]]);
        }
        const timestamp=new Date(replayTime*1000).toLocaleTimeString('en-US',{
          timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',second:'2-digit'
        });
        timeLabel.textContent=scopedReplay?`${elapsed(replayTime,selectedRace.gun)} since start · ${timestamp} local`:
          `GPS replay · ${timestamp}`;
        hourLabel.textContent=scopedReplay?elapsed(replayTimes.at(-1),selectedRace.gun):
          `${gpsIndex+1}/${replayTimes.length}`;
        readout.textContent='Recorded GPS route · model forecast 30 seconds ahead';
        document.getElementById('gpsSpeedNow').textContent=hasFocus?`${point.speed_kt.toFixed(1)} kt`:
          focusSynthetic?'Illustrated path':'No GPS fix';
        document.getElementById('gpsSpeedPredicted').textContent=hasFocus?`${point.predicted_speed_kt.toFixed(1)} kt`:'Unavailable';
        document.getElementById('gpsSpeedRange').textContent=hasFocus?
          `${point.prediction_low_kt.toFixed(1)}–${point.prediction_high_kt.toFixed(1)} kt`:'Unavailable';
        document.getElementById('gpsSpeedActual').textContent=hasFocus && point.actual_future_speed_kt!==null?
          `${point.actual_future_speed_kt.toFixed(1)} kt`:'Not available';
      }
      slider.addEventListener('input',() => {gpsPlaying=false;updatePlayButton();renderGps(slider.value);});
      playButton.addEventListener('click',() => {
        if(!gpsPlaying && gpsIndex===replayTimes.length-1)renderGps(0);
        gpsPlaying=!gpsPlaying;updatePlayButton();
      });
      setInterval(() => {
        if(!gpsPlaying)return;
        renderGps(Math.min(gpsIndex+1,replayTimes.length-1));
        if(gpsIndex===replayTimes.length-1){gpsPlaying=false;updatePlayButton();}
      },350);
      updatePlayButton();
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
      layers.filter((layer) => layer.mode === 'scalar').forEach((layer) => {
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

      const vectorLayers = layers.filter((layer) => layer.mode !== 'scalar');
      if (!vectorLayers.length) {
        context.clearRect(0, 0, size.x, size.y);
        requestAnimationFrame(animate);
        return;
      }

      context.globalCompositeOperation = 'destination-out';
      context.fillStyle = 'rgba(0,0,0,.075)';
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
