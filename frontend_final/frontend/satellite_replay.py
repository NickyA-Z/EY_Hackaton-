"""Optional satellite GPS replay. No existing application files need changing.

Integration (next to the existing speed_replay_map call)::

    from frontend_final.frontend.satellite_replay import render_satellite_replay

    render_satellite_replay(speed_track_points(rows, model, horizon), index)

Requires pydeck>=0.9 (included by Streamlit). Set MAPBOX_API_KEY in the
process environment or Streamlit secrets to a public, browser-safe pk.* token.
Mapbox imagery requires network access and a valid token. No token is stored.

Input: existing speed_track_points() dictionaries; optional heading_deg uses
clockwise degrees from north. Without heading, course over ground is derived
from adjacent recorded coordinates (not a measured boat heading).
This is a pitched satellite map, not photorealistic Google Earth terrain.
"""

import json
import math
import os
from urllib.parse import quote

import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components

_BOAT = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<path d="M32 3 Q51 35 43 55 Q32 64 21 55 Q13 35 32 3Z" fill="#00378A" stroke="white" stroke-width="3"/>
<path d="M32 12 L32 46 L47 43Z" fill="white" stroke="#374151"/>
<path d="M29 20 L18 44 L29 46Z" fill="#FF6900"/>
</svg>"""


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _prepare_points(points):
    """Copy and validate observations without reordering or editing source data."""
    result = []
    for point in points:
        row = dict(point)
        if not all(_finite(row.get(key)) for key in ("lat", "lng", "time_epoch", "speed_kt")):
            raise ValueError("GPS points require finite lat, lng, time_epoch and speed_kt.")
        if not -90 <= row["lat"] <= 90 or not -180 <= row["lng"] <= 180:
            raise ValueError("GPS coordinates are outside latitude/longitude bounds.")
        if result and row["time_epoch"] <= result[-1]["time_epoch"]:
            raise ValueError("GPS timestamps must be strictly increasing; duplicate times need resolving upstream.")
        colour = row.get("colour")
        if (
            not isinstance(colour, (list, tuple))
            or len(colour) != 3
            or not all(_finite(channel) and 0 <= channel <= 255 for channel in colour)
        ):
            raise ValueError("Each GPS point requires its existing RGB colour (three values from 0 to 255).")
        # Optional prediction fields can be missing; never serialize NaN into JS.
        for key in (
            "predicted_lat",
            "predicted_lng",
            "predicted_speed_kt",
            "prediction_low_kt",
            "prediction_high_kt",
            "actual_future_speed_kt",
            "heading_deg",
        ):
            if not _finite(row.get(key)):
                row[key] = None
        result.append(
            {
                key: row[key]
                for key in (
                    "lat",
                    "lng",
                    "time_epoch",
                    "speed_kt",
                    "colour",
                    "heading_deg",
                    "predicted_lat",
                    "predicted_lng",
                    "predicted_speed_kt",
                    "prediction_low_kt",
                    "prediction_high_kt",
                    "actual_future_speed_kt",
                )
            }
        )
    previous_course = 0.0
    for index, row in enumerate(result):
        if row["heading_deg"] is not None:
            row["heading_source"] = "Heading"
            row["heading_deg"] %= 360
            continue
        other = result[min(index + 1, len(result) - 1)]
        start = row
        if index == len(result) - 1 and index:
            start, other = result[index - 1], row
        lat1, lat2 = math.radians(start["lat"]), math.radians(other["lat"])
        delta = math.radians(other["lng"] - start["lng"])
        east = math.sin(delta) * math.cos(lat2)
        north = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta)
        if abs(east) + abs(north) > 1e-12:
            previous_course = math.degrees(math.atan2(east, north)) % 360
        row["heading_deg"] = previous_course
        row["heading_source"] = "GPS course (derived)"
    return result


def build_satellite_replay_html(points, token, start_frame=0):
    """Build a self-contained replay document, also usable for isolated previews."""
    points = _prepare_points(points)
    if not points:
        raise ValueError("No recorded GPS points to replay.")
    if not isinstance(token, str) or not token.startswith("pk."):
        raise ValueError("Configure MAPBOX_API_KEY with a public Mapbox token starting with pk.")
    start_frame = max(0, min(int(start_frame), len(points) - 1))
    segments = [
        {
            "source": [a["lng"], a["lat"]],
            "target": [b["lng"], b["lat"]],
            "colour": b["colour"],
            "speed_kt": b["speed_kt"],
        }
        for a, b in zip(points, points[1:])
    ]
    longitudes, latitudes = [p["lng"] for p in points], [p["lat"] for p in points]
    span = max(max(longitudes) - min(longitudes), (max(latitudes) - min(latitudes)) * 1.6, 0.002)
    route = pdk.Layer(
        "LineLayer",
        segments,
        id="recorded-route",
        get_source_position="source",
        get_target_position="target",
        get_color="colour",
        get_width=4,
        pickable=True,
    )
    view = pdk.ViewState(
        longitude=(min(longitudes) + max(longitudes)) / 2,
        latitude=(min(latitudes) + max(latitudes)) / 2,
        zoom=max(2, min(16, math.log2(180 / span) - 1)),
        pitch=55,
        bearing=-20,
    )
    spec = pdk.Deck(
        layers=[route],
        initial_view_state=view,
        map_provider="mapbox",
        map_style="mapbox://styles/mapbox/satellite-streets-v12",
    )
    payload = {
        "spec": json.loads(spec.to_json()),
        "points": points,
        "start": start_frame,
        "token": token,
        "icon": "data:image/svg+xml;charset=utf-8," + quote(_BOAT),
    }
    return _HTML.replace("__PAYLOAD__", json.dumps(payload, allow_nan=False).replace("<", "\\u003c"))


def render_satellite_replay(points, start_frame=0, height=560):
    """Drop-in optional Streamlit view. Replay stays inside its isolated iframe."""
    token = os.environ.get("MAPBOX_API_KEY") or os.environ.get("MapboxAccessToken")  # noqa: SIM112 -- PyDeck convention
    if not token:
        try:
            token = st.secrets.get("MAPBOX_API_KEY")
        except st.errors.StreamlitSecretNotFoundError:
            token = None
    if not token:
        st.info(
            "Satellite replay: set MAPBOX_API_KEY to a public Mapbox token in your environment or Streamlit secrets."
        )
        return
    try:
        document = build_satellite_replay_html(points, token, start_frame)
    except ValueError as error:
        st.warning(str(error))
        return
    components.html(document, height=height, scrolling=False)


_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://api.mapbox.com/mapbox-gl-js/v3.2.0/mapbox-gl.js"></script>
<link href="https://api.mapbox.com/mapbox-gl-js/v3.2.0/mapbox-gl.css" rel="stylesheet">
<script src="https://unpkg.com/deck.gl@9.1.0/dist.min.js"></script>
<style>
*{box-sizing:border-box}html,body,#map{margin:0;width:100%;height:100%;background:#102334}
body{font-family:'Hanken Grotesk',system-ui,sans-serif;color:white}
.panel{position:absolute;z-index:5;background:rgba(12,27,43,.9);border:1px solid #ffffff35;
backdrop-filter:blur(8px);border-radius:12px;padding:12px;font-size:12px}
#controls{left:12px;right:12px;bottom:38px}#metrics{top:12px;left:12px;max-width:290px;line-height:1.65}
button,select{background:#00378a;color:white;border:1px solid #ffffff65;border-radius:6px;padding:6px;cursor:pointer}
input{width:100%;accent-color:#ff6900}#time{font-variant-numeric:tabular-nums}#status{color:#ffc58c}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:5px}.legend i{display:inline-block;width:9px;height:9px;margin-right:3px}
#help{font-size:11px;color:#d5dce4;margin-top:4px}#error{display:none;top:12px;right:12px;max-width:240px}
</style></head><body><div id="map"></div>
<div id="metrics" class="panel"><b>SAILING · SATELLITE REPLAY</b><div id="time"></div>
<div id="speed"></div><div id="heading"></div><div id="prediction"></div><div id="range"></div>
<div id="actual"></div><div id="status"></div></div>
<div id="error" class="panel" role="alert"></div>
<div id="controls" class="panel"><button id="play" aria-label="Play replay">Play</button>
<label> Speed <select id="rate"><option>1</option><option>10</option><option selected>30</option><option>60</option></select>×</label>
<button id="reset">Reset view</button> <span id="frame"></span>
<input id="timeline" type="range" min="0" step="1" aria-label="Recorded GPS timeline">
<div class="legend"><span><i style="background:rgb(49,54,149)"></i>0–2 kt</span>
<span><i style="background:rgb(41,120,185)"></i>2–4 kt</span><span><i style="background:rgb(46,179,126)"></i>4–6 kt</span>
<span><i style="background:rgb(253,174,97)"></i>6–8 kt</span><span><i style="background:rgb(215,48,39)"></i>8+ kt</span></div>
<div id="help">Drag to pan · right-drag to rotate/tilt · scroll to zoom · orange = model projection</div></div>
<script>
const data=__PAYLOAD__, points=data.points, spec=data.spec;
const el=id=>document.getElementById(id), first=points[0].time_epoch, last=points.at(-1).time_epoch;
let index=data.start, clock=points[index].time_epoch, playing=false, previous=null;
const fail=message=>{el('error').style.display='block';el('error').textContent=message;};
try {
const routeSpec=spec.layers[0];
const route=new deck.LineLayer({...routeSpec, data:routeSpec.data,
  getSourcePosition:d=>d.source,getTargetPosition:d=>d.target,getColor:d=>d.colour,getWidth:4});
const icon={url:data.icon,width:64,height:64,anchorX:32,anchorY:32};
const viewer=new deck.DeckGL({container:'map',mapboxApiAccessToken:data.token,mapStyle:spec.mapStyle,
 initialViewState:spec.initialViewState,controller:true,
 getTooltip:({object})=>object && Number.isFinite(object.speed_kt)?`Recorded speed: ${object.speed_kt.toFixed(1)} kt`:null,
 onError:()=>fail('Map failed to load. Check network access and Mapbox token configuration.')});
// Keep route data/layer stable; only the small moving overlays change during playback.
function render(){
 const p=points[index], next=points[Math.min(index+1,points.length-1)], gap=next.time_epoch-p.time_epoch;
 const blend=gap>0 && gap<=60?Math.max(0,Math.min(1,(clock-p.time_epoch)/gap)):0;
 const dlng=((next.lng-p.lng+540)%360)-180;
 const position=[((p.lng+dlng*blend+540)%360)-180,p.lat+(next.lat-p.lat)*blend];
 const heading=p.heading_deg+(((next.heading_deg-p.heading_deg+540)%360)-180)*blend;
 const boat=new deck.IconLayer({id:'boat',data:[{position}],getPosition:d=>d.position,
   getIcon:()=>icon,getSize:42,billboard:false,getAngle:-heading,pickable:false});
 const layers=[route,boat];
 if(Number.isFinite(p.predicted_lat)&&Number.isFinite(p.predicted_lng)){
   const target=[p.predicted_lng,p.predicted_lat];
   layers.push(new deck.LineLayer({id:'projection',data:[{source:[p.lng,p.lat],target}],
     getSourcePosition:d=>d.source,getTargetPosition:d=>d.target,getColor:[255,105,0],getWidth:2}));
   layers.push(new deck.ScatterplotLayer({id:'predicted-position',data:[target],getPosition:d=>d,
     getFillColor:[255,105,0],getRadius:6,radiusUnits:'pixels',stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:1}));
 }
 viewer.setProps({layers});
 el('timeline').value=index;
 el('frame').textContent=`${index+1} / ${points.length}`;
 el('time').textContent=new Date(clock*1000).toISOString().replace('T',' ').replace('.000Z',' UTC');
 const speed=value=>Number.isFinite(value)?`${value.toFixed(1)} kt`:'Unavailable';
 el('speed').textContent=`Recorded speed: ${speed(p.speed_kt)}`;
 el('heading').textContent=`${p.heading_source}: ${((heading+360)%360).toFixed(0)}°`;
 el('prediction').textContent=`Model speed: ${speed(p.predicted_speed_kt)}`;
 el('range').textContent=`Model range: ${speed(p.prediction_low_kt)} – ${speed(p.prediction_high_kt)}`;
 el('actual').textContent=`Recorded future speed: ${speed(p.actual_future_speed_kt)}`;
 el('status').textContent=gap>60?'GPS gap >60 s; position held until next observation':
   blend>0?'Interpolated position · telemetry from preceding observation':'Recorded GPS position';
}
function setPlaying(value){playing=value;previous=null;el('play').textContent=value?'Pause':'Play';
 el('play').setAttribute('aria-label',value?'Pause replay':'Play replay');}
el('timeline').max=points.length-1;
el('play').disabled=points.length<2;
el('play').onclick=()=>{if(clock>=last){index=0;clock=first;}setPlaying(!playing);render();};
el('timeline').oninput=()=>{setPlaying(false);index=Number(el('timeline').value);clock=points[index].time_epoch;render();};
el('reset').onclick=()=>viewer.setProps({initialViewState:{...spec.initialViewState}});
document.addEventListener('visibilitychange',()=>{previous=null;});
let lastDraw=0;
function tick(now){
 if(playing && !document.hidden){
   if(previous!==null)clock=Math.min(last,clock+(now-previous)/1000*Number(el('rate').value));
   previous=now;
   while(index<points.length-1 && points[index+1].time_epoch<=clock)index++;
   if(now-lastDraw>=33 || clock>=last){render();lastDraw=now;}
   if(clock>=last)setPlaying(false);
 }
 requestAnimationFrame(tick);
}
render();requestAnimationFrame(tick);
} catch(error){fail('Satellite map unavailable. Check browser WebGL support and network access.');}
</script></body></html>"""
