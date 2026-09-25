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
            key = (exposure["osm"]["type"], str(exposure["osm"]["id"]), exposure["osm"]["version"])
            exposed[key] = {"type": "Feature", "geometry": exposure["infrastructure_geometry"],
                            "properties": {"category": exposure["category"], "display_name": exposure["display_name"],
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
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\">
<style>html,body,#map{{height:100%;margin:0}}#panel{{position:absolute;z-index:1000;top:12px;left:52px;background:#fff;padding:10px 12px;border-radius:6px;box-shadow:0 1px 8px #0005;font:14px system-ui;max-width:360px}}#timeline{{width:220px}}.legend i{{display:inline-block;width:12px;height:12px;margin-right:5px}} .muted{{color:#555;font-size:12px}}</style>
</head><body><div id=\"map\"></div><div id=\"panel\"><strong>Civil Infrastructure Danger Forecast</strong><br>
<label>Observation <span id=\"idx\">0</span> <input id=\"timeline\" type=\"range\" min=\"0\" max=\"{max_index}\" value=\"0\"></label>
<div id=\"time\" class=\"muted\"></div><div class=\"legend\"><i style=\"background:#e6b800\"></i>likely <i style=\"background:#ef8a62\"></i>possible <i style=\"background:#d73027\"></i>danger area</div>
<div class=\"muted\">Analytical overlays are fixed artifacts. © OpenStreetMap contributors.</div></div>
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script><script>
const DATA={payload};
const map=L.map('map'); L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,attribution:'© OpenStreetMap contributors'}}).addTo(map);
const dynamic=L.layerGroup().addTo(map), observations=L.geoJSON(DATA.layers['observations.geojson'],{{pointToLayer:(f,ll)=>L.circleMarker(ll,{{radius:5,color:'#1167b1'}}),onEachFeature:(f,l)=>l.bindTooltip(`${{f.properties.timestamp}} · ${{f.properties.altitude}} m`)}}).addTo(map);
const infra=L.geoJSON(DATA.layers['exposed_infrastructure.geojson'],{{style:{{color:'#2266aa',weight:2,fillOpacity:.12}},pointToLayer:(f,ll)=>L.circleMarker(ll,{{radius:7,color:'#2266aa'}}),onEachFeature:(f,l)=>l.bindTooltip(`${{f.properties.category}} · ${{f.properties.display_name||'unnamed'}}`)}}).addTo(map);
function render(index){{dynamic.clearLayers();document.getElementById('idx').textContent=index;const snapshot=DATA.result.snapshots[index];if(!snapshot)return;document.getElementById('time').textContent=snapshot.as_of+' · '+snapshot.classification.mobility_profile;
for(const f of DATA.layers['centerlines.geojson'].features.filter(x=>x.properties.observation_index===index))L.geoJSON(f,{{style:{{color:'#222',weight:3}}}}).addTo(dynamic);
for(const f of DATA.layers['corridors.geojson'].features.filter(x=>x.properties.observation_index===index))L.geoJSON(f,{{style:{{color:f.properties.band==='likely'?'#e6b800':'#ef8a62',weight:2,fillOpacity:f.properties.band==='likely'?.25:.12}}}}).addTo(dynamic);
for(const f of DATA.layers['danger_areas.geojson'].features.filter(x=>x.properties.observation_index===index))L.geoJSON(f,{{style:{{color:'#d73027',weight:2,fillOpacity:.55}},onEachFeature:(g,l)=>l.bindTooltip(`${{g.properties.urgency}} · ${{g.properties.category}} · entry +${{g.properties.first_entry_offset_s}}s`)}}).addTo(dynamic);}}
document.getElementById('timeline').addEventListener('input',e=>render(Number(e.target.value)));render(0);
const bounds=observations.getBounds();if(bounds.isValid())map.fitBounds(bounds.pad(.35));else map.setView([0,0],2);
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
