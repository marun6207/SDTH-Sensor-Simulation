from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .snapshot import canonical_json


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def build_geojson_artifacts(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observations = []
    centerlines = []
    corridors = []
    exposed = {}
    dangers = []
    raw_observations = result["observations"]
    for index, observation in enumerate(raw_observations):
        observations.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [observation["long"], observation["lat"]]},
                             "properties": {"observation_index": index, "timestamp": observation["timestamp"],
                                            "altitude": observation["altitude"], "speed": observation.get("speed"),
                                            "type": observation.get("type")}})
    for snapshot in result["snapshots"]:
        index = snapshot["observation_index"]
        centerlines.append({"type": "Feature", "geometry": snapshot["forecast"]["centerline"],
                            "properties": {"observation_index": index, "as_of": snapshot["as_of"]}})
        for band in ("likely", "possible"):
            corridors.append({"type": "Feature", "geometry": snapshot["forecast"][f"{band}_corridor"],
                              "properties": {"observation_index": index, "as_of": snapshot["as_of"], "band": band}})
        for exposure in snapshot["exposures"]:
            key = (index, exposure["osm"]["type"], str(exposure["osm"]["id"]), exposure["osm"]["version"])
            exposed[key] = {"type": "Feature", "geometry": exposure["infrastructure_geometry"],
                            "properties": {"observation_index": index, "category": exposure["category"],
                                           "display_name": exposure["display_name"],
                                           "osm": exposure["osm"], "source_tags": exposure["source_tags"]}}
            dangers.append({"type": "Feature", "geometry": exposure["danger_geometry"],
                            "properties": {"observation_index": index, "exposure_id": exposure["exposure_id"],
                                           "category": exposure["category"], "display_name": exposure["display_name"],
                                           "band": exposure["band"], "urgency": exposure["urgency"],
                                           "first_entry_offset_s": exposure["first_entry_offset_s"]}})
    return {
        "observations.geojson": _collection(observations),
        "centerlines.geojson": _collection(centerlines),
        "corridors.geojson": _collection(corridors),
        "exposed_infrastructure.geojson": _collection(list(exposed.values())),
        "danger_areas.geojson": _collection(dangers),
    }


def render_html(result: dict[str, Any]) -> str:
    data = build_geojson_artifacts(result)
    payload = json.dumps({"result": result, "layers": data}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    max_index = max(0, len(result.get("snapshots", [])) - 1)
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Civil Infrastructure Danger Forecast</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/maplibre-gl@5.12.0/dist/maplibre-gl.css\">
<style>html,body,#map{{height:100%;margin:0}}#map{{background:#eef2f5}}#panel{{position:absolute;z-index:1000;top:12px;left:52px;background:#fff;padding:10px 12px;border-radius:6px;box-shadow:0 1px 8px #0005;font:14px system-ui;max-width:360px}}#timeline{{width:220px}}.legend i{{display:inline-block;width:12px;height:12px;margin-right:5px}} .muted{{color:#555;font-size:12px}}.maplibregl-popup-content{{white-space:pre-line;font:13px system-ui;line-height:1.35}}</style>
</head><body><div id=\"map\"></div><div id=\"panel\"><strong>Civil Infrastructure Danger Forecast</strong><br>
<label>Time +<span id=\"idx\">0</span> s <input id=\"timeline\" type=\"range\" min=\"0\" max=\"{max_index}\" step=\"1\" value=\"0\"></label>
<div id=\"time\" class=\"muted\"></div><div class=\"legend\"><i style=\"background:#d73027\"></i>affected infrastructure <i style=\"background:#e6b800\"></i>likely area <i style=\"background:#ef8a62\"></i>possible area</div>
<div id=\"coordinates\" class=\"muted\">Move the pointer over the map for coordinates.</div>
<div class=\"muted\">Basemap: OpenFreeMap. Infrastructure data: © OpenStreetMap contributors.</div></div>
<script src=\"https://unpkg.com/maplibre-gl@5.12.0/dist/maplibre-gl.js\"></script><script>
const DATA={payload};
const observationFeatures=DATA.layers['observations.geojson'].features;
const firstCoordinate=observationFeatures[0]?.geometry?.coordinates||[0,0];
const observationTimes=observationFeatures.map(feature=>Date.parse(feature.properties.timestamp));
const firstTime=observationTimes[0]||0,lastTime=observationTimes.at(-1)||firstTime;
const timeline=document.getElementById('timeline');timeline.max=String(Math.max(0,(lastTime-firstTime)/1000));
const map=new maplibregl.Map({{container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:firstCoordinate,zoom:8,attributionControl:false}});
map.addControl(new maplibregl.NavigationControl(),'top-left');
map.addControl(new maplibregl.ScaleControl({{unit:'metric'}}));
map.addControl(new maplibregl.AttributionControl({{compact:true,customAttribution:'Analytical infrastructure: © OpenStreetMap contributors'}}));
map.on('mousemove',e=>document.getElementById('coordinates').textContent=`${{e.lngLat.lat.toFixed(5)}}, ${{e.lngLat.lng.toFixed(5)}}`);
const observationFilter=index=>['==',['get','observation_index'],index];
const corridorFilter=(band,index)=>['all',['==',['get','band'],band],observationFilter(index)];
const geometryObservationFilter=(geometry,index)=>['all',['==',['geometry-type'],geometry],observationFilter(index)];
const popup=new maplibregl.Popup({{closeButton:false,closeOnClick:false,offset:10}});
function parseObject(value){{if(!value)return {{}};if(typeof value==='object')return value;try{{return JSON.parse(value)}}catch{{return {{}}}}}}
function pretty(value){{return String(value||'unknown').replaceAll('_',' ').replace(/\\b\\w/g,c=>c.toUpperCase())}}
function describeInfrastructure(properties){{
  const tags=parseObject(properties.source_tags),osm=parseObject(properties.osm);
  const lines=[properties.display_name||pretty(properties.category),`Category: ${{pretty(properties.category)}}`];
  for(const key of ['description','operator','amenity','power','man_made','industrial','emergency','aeroway','harbour','public_transport'])if(tags[key])lines.push(`${{pretty(key)}}: ${{tags[key]}}`);
  if(osm.type&&osm.id!==undefined)lines.push(`OSM: ${{osm.type}}/${{osm.id}}`);
  return lines.join('\\n');
}}
function describeObservation(properties){{
  const speed=properties.speed===null||properties.speed===undefined?'not reported':`${{Number(properties.speed).toFixed(2)}} m/s`;
  const title=properties.interpolated?`Interpolated position (${{properties.segment}})`:`Observation ${{properties.observation_index}}`;
  return [title,properties.timestamp,`Altitude: ${{Number(properties.altitude).toFixed(1)}} m`,`Speed: ${{speed}}`,`Type: ${{properties.type||'not reported'}}`].join('\\n');
}}
function describeDanger(properties){{return [properties.display_name||pretty(properties.category),`Danger area: ${{properties.band}} band`,`Urgency: ${{pretty(properties.urgency)}}`,`First entry: +${{properties.first_entry_offset_s}} s`].join('\\n')}}
function bindHover(layerId,describe){{
  map.on('mousemove',layerId,event=>{{const feature=event.features?.[0];if(!feature)return;map.getCanvas().style.cursor='pointer';popup.setLngLat(event.lngLat).setText(describe(feature.properties||{{}})).addTo(map)}});
  map.on('mouseleave',layerId,()=>{{map.getCanvas().style.cursor='';popup.remove()}});
}}
function render(elapsedSeconds){{
  const selectedTime=Math.min(lastTime,firstTime+Number(elapsedSeconds)*1000);
  let index=Math.max(0,observationTimes.findIndex(time=>time>selectedTime)-1);
  if(index<0||selectedTime>=lastTime)index=Math.max(0,observationFeatures.length-1);
  const nextIndex=Math.min(index+1,observationFeatures.length-1),startTime=observationTimes[index],endTime=observationTimes[nextIndex];
  const fraction=nextIndex===index||endTime===startTime?0:Math.max(0,Math.min(1,(selectedTime-startTime)/(endTime-startTime)));
  const start=observationFeatures[index],end=observationFeatures[nextIndex],startProperties=start.properties,endProperties=end.properties;
  const interpolate=(first,second)=>Number(first)+(Number(second)-Number(first))*fraction;
  const activeType=DATA.result.snapshots[index]?.classification?.reported_type||startProperties.type||null;
  const currentFeature={{type:'Feature',geometry:{{type:'Point',coordinates:[interpolate(start.geometry.coordinates[0],end.geometry.coordinates[0]),interpolate(start.geometry.coordinates[1],end.geometry.coordinates[1])]}},properties:{{observation_index:index,timestamp:new Date(selectedTime).toISOString(),altitude:interpolate(startProperties.altitude,endProperties.altitude),speed:startProperties.speed===null||endProperties.speed===null?startProperties.speed:interpolate(startProperties.speed,endProperties.speed),type:activeType,interpolated:fraction>0&&nextIndex!==index,segment:`observation ${{index}} → ${{nextIndex}} · ${{Math.round(fraction*100)}}%`}}}};
  document.getElementById('idx').textContent=Number(elapsedSeconds).toFixed(0);
  const snapshot=DATA.result.snapshots[index];if(!snapshot)return;
  document.getElementById('time').textContent=currentFeature.properties.timestamp+' · '+snapshot.classification.mobility_profile+` · forecast basis: observation ${{index}}`;
  if(!map.getLayer('centerlines'))return;
  map.getSource('observations').setData({{type:'FeatureCollection',features:[currentFeature]}});
  map.setFilter('centerlines',observationFilter(index));
  map.setFilter('likely-fill',corridorFilter('likely',index));
  map.setFilter('likely-line',corridorFilter('likely',index));
  map.setFilter('possible-fill',corridorFilter('possible',index));
  map.setFilter('possible-line',corridorFilter('possible',index));
  map.setFilter('infrastructure-fill',geometryObservationFilter('Polygon',index));
  map.setFilter('infrastructure-line',geometryObservationFilter('LineString',index));
  map.setFilter('infrastructure-point',geometryObservationFilter('Point',index));
}}
map.on('load',()=>{{
  map.addSource('observations',{{type:'geojson',data:{{type:'FeatureCollection',features:[]}}}});
  map.addSource('infrastructure',{{type:'geojson',data:DATA.layers['exposed_infrastructure.geojson']}});
  map.addSource('centerlines',{{type:'geojson',data:DATA.layers['centerlines.geojson']}});
  map.addSource('corridors',{{type:'geojson',data:DATA.layers['corridors.geojson']}});
  map.addLayer({{id:'possible-fill',type:'fill',source:'corridors',filter:corridorFilter('possible',0),paint:{{'fill-color':'#ef8a62','fill-opacity':.16}}}});
  map.addLayer({{id:'possible-line',type:'line',source:'corridors',filter:corridorFilter('possible',0),paint:{{'line-color':'#d95f3f','line-width':2}}}});
  map.addLayer({{id:'likely-fill',type:'fill',source:'corridors',filter:corridorFilter('likely',0),paint:{{'fill-color':'#e6b800','fill-opacity':.28}}}});
  map.addLayer({{id:'likely-line',type:'line',source:'corridors',filter:corridorFilter('likely',0),paint:{{'line-color':'#b38f00','line-width':2}}}});
  map.addLayer({{id:'centerlines',type:'line',source:'centerlines',filter:observationFilter(0),paint:{{'line-color':'#222','line-width':3}}}});
  map.addLayer({{id:'infrastructure-fill',type:'fill',source:'infrastructure',filter:geometryObservationFilter('Polygon',0),paint:{{'fill-color':'#d73027','fill-opacity':.72,'fill-outline-color':'#8c0000'}}}});
  map.addLayer({{id:'infrastructure-line',type:'line',source:'infrastructure',filter:geometryObservationFilter('LineString',0),paint:{{'line-color':'#d73027','line-width':4}}}});
  map.addLayer({{id:'infrastructure-point',type:'circle',source:'infrastructure',filter:geometryObservationFilter('Point',0),paint:{{'circle-radius':4,'circle-color':'#d73027','circle-stroke-color':'#8c0000','circle-stroke-width':1.5}}}});
  map.moveLayer('infrastructure-fill');
  map.moveLayer('infrastructure-line');
  map.moveLayer('infrastructure-point');
  map.addLayer({{id:'observations',type:'circle',source:'observations',paint:{{'circle-radius':5,'circle-color':'#fff','circle-stroke-color':'#1167b1','circle-stroke-width':3}}}});
  for(const layer of ['infrastructure-fill','infrastructure-line','infrastructure-point'])bindHover(layer,describeInfrastructure);
  bindHover('observations',describeObservation);
  if(observationFeatures.length){{const bounds=new maplibregl.LngLatBounds();for(const feature of observationFeatures)bounds.extend(feature.geometry.coordinates);map.fitBounds(bounds,{{padding:80,maxZoom:12,duration:0}});}}
  render(Number(document.getElementById('timeline').value));
}});
document.getElementById('timeline').addEventListener('input',e=>render(Number(e.target.value)));
</script></body></html>"""


def write_artifacts(result: dict[str, Any], output_directory: str | Path) -> dict[str, Any]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    files["snapshots.jsonl"] = b"".join(canonical_json(item) + b"\n" for item in result["snapshots"])
    files["result.json"] = canonical_json(result) + b"\n"
    for name, collection in build_geojson_artifacts(result).items():
        files[name] = canonical_json(collection) + b"\n"
    files["map.html"] = render_html(result).encode("utf-8")
    hashes = {}
    for name, content in files.items():
        _atomic_write(output / name, content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    manifest = {"schema": "hazard-artifact-manifest/v1", "track_id": result["track_id"],
                "snapshot": result["snapshot"], "profile_catalog_version": result["profile_catalog_version"],
                "files": hashes}
    _atomic_write(output / "manifest.json", canonical_json(manifest) + b"\n")
    return manifest
