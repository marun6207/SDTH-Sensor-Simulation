from __future__ import annotations

import base64
import json
import math
import re
import time
from copy import deepcopy
from typing import Any

import dash_leaflet as dl
from dash import ALL, MATCH, Dash, Input, Output, State, ctx, dcc, html, no_update
from pydantic import ValidationError

from simulator.demo import build_demo_scenario
from simulator.engine import _eligible, contact_state_at, extrapolate_waypoint, generate_outputs, relative_timestamp
from simulator.models import (
    AisSensor,
    CctvSensor,
    Contact,
    EoirSensor,
    EwSensor,
    FusionSensor,
    Radar2DSensor,
    Radar3DSensor,
    SarSensor,
    Scenario,
    Waypoint,
)


SENSOR_CLASSES = {
    "radar_2d": Radar2DSensor,
    "radar_3d": Radar3DSensor,
    "eoir": EoirSensor,
    "ew": EwSensor,
    "cctv": CctvSensor,
    "ais": AisSensor,
    "sar": SarSensor,
    "fusion": FusionSensor,
}
PALETTE = [
    ("radar_2d", "2D Radar", "sensor"),
    ("radar_3d", "3D Radar", "sensor"),
    ("eoir", "EO / IR", "sensor"),
    ("ew", "EW DF", "sensor"),
    ("cctv", "Coastal CCTV", "sensor"),
    ("ais", "AIS Receiver", "sensor"),
    ("sar", "Satellite SAR", "sensor"),
    ("fusion", "AIS + SAR", "sensor"),
    ("air", "Hostile Air", "contact"),
    ("surface", "Hostile Vessel", "contact"),
]
TARGET_RANGE_TYPES = ["radar_2d", "radar_3d", "eoir", "ew", "cctv", "ais", "sar"]


def scenario_dict() -> dict[str, Any]:
    return build_demo_scenario().model_dump(mode="json")


app = Dash(__name__, title="Joint Sensor Simulator", suppress_callback_exceptions=True)
server = app.server


def palette_button(kind: str, label: str, category: str) -> html.Button:
    return html.Button(label, id={"type": "palette", "kind": kind}, n_clicks=0,
                       className=f"palette-btn {category}", title=f"Place {label}")


def tactical_map() -> dl.Map:
    return dl.Map(
        [
            dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                         attribution="© OpenStreetMap contributors"),
            dl.LayerGroup(id="static-map-layers"),
            dl.LayerGroup(id="dynamic-map-layers"),
            dl.ScaleControl(position="bottomleft", imperial=False, metric=True),
        ],
        id="tactical-map",
        center=[1.33, 103.89],
        zoom=10,
        minZoom=3,
        maxZoom=18,
        preferCanvas=True,
        zoomControl=True,
        style={"width": "100%", "height": "100%"},
    )


app.layout = html.Div(
    [
        dcc.Store(id="scenario-store", storage_type="local", data=scenario_dict()),
        dcc.Store(id="placement-mode", storage_type="memory"),
        dcc.Store(id="playback-store", storage_type="memory", data={"time_s": 0, "playing": False, "speed": 1}),
        dcc.Store(id="outputs-store", storage_type="memory", data={}),
        dcc.Interval(id="playback-interval", interval=500, disabled=True),
        dcc.Download(id="scenario-download"),
        html.Div(id="all-download-sink", style={"display": "none"}),
        html.Header(
            [
                html.Div([html.Div("⌖", className="brand-mark"), html.Div([
                    html.H1("JOINT SENSOR SIMULATOR"), html.P("Synthetic air and maritime operational picture")
                ])], className="brand"),
                html.Div("● SIMULATION READY", className="status-pill"),
            ], className="topbar"
        ),
        html.Main(
            [
                html.Aside(
                    [
                        html.Div("Place entity", className="panel-title"),
                        html.Div([palette_button(*item) for item in PALETTE], className="palette-grid"),
                        html.P("Choose an entity, then click the map. The placement tool stays active for rapid authoring.", className="hint"),
                        html.Hr(style={"borderColor": "#203946", "margin": "18px 0"}),
                        html.Div("Scenario", className="panel-title"),
                        html.Label("Name"), dcc.Input(id="scenario-name", className="field"),
                        html.Div(className="form-row", children=[
                            html.Div([html.Label("Duration (s)"), dcc.Input(id="scenario-duration", type="number", min=1, className="field")]),
                            html.Div([html.Label("Random seed"), dcc.Input(id="scenario-seed", type="number", className="field")]),
                        ]),
                        html.Div([
                            html.Button("Save settings", id="save-scenario", className="btn btn-primary"),
                            html.Button("Reset demo", id="reset-demo", className="btn"),
                        ], className="button-row"),
                        dcc.Upload(id="scenario-upload", children=html.Button("Import scenario", className="btn"),
                                   accept="application/json", className="upload"),
                        html.Button("Export scenario", id="export-scenario", className="btn"),
                    ], className="panel"
                ),
                html.Section(
                    [
                        tactical_map(),
                        html.Div(id="placement-banner", className="map-mode"),
                        html.Div([
                            html.Span([html.I(className="legend-swatch sensor-legend"), "Sensor"]),
                            html.Span([html.I(className="legend-swatch air-legend"), "Air target"]),
                            html.Span([html.I(className="legend-swatch surface-legend"), "Surface target"]),
                            html.Span([html.I(className="legend-line"), "Detectable"]),
                        ], className="map-legend"),
                    ],
                    className="map-wrap",
                ),
                html.Aside(
                    [
                        html.Div("Entity inspector", className="panel-title"),
                        dcc.Dropdown(id="entity-select", clearable=True, placeholder="Select a sensor or contact"),
                        html.Div(id="entity-heading", style={"margin": "14px 0 8px", "fontSize": "12px"}),
                        html.Div([
                            html.Div("Target emissions & detectability", className="panel-title"),
                            html.Label("EMCON mode"),
                            dcc.Dropdown(id="target-emcon", options=[
                                {"label": "Active — RF emissions enabled", "value": "active"},
                                {"label": "Passive — no EW emitter", "value": "passive"},
                                {"label": "Silent — no EW or AIS", "value": "silent"},
                            ], clearable=False),
                            html.P("Maximum range at which each sensor type can detect this target. Blank uses the sensor's full configured range; 0 makes it undetectable.", className="hint"),
                            html.Div([
                                html.Div([
                                    html.Label(sensor_type.replace("_", " ")),
                                    dcc.Input(id=f"target-range-{sensor_type}", type="number", min=0, step=.1,
                                              placeholder="Sensor range", className="field"),
                                ]) for sensor_type in TARGET_RANGE_TYPES
                            ], className="target-range-grid"),
                            html.Div([
                                html.Button("Add waypoint on map", id="add-waypoint", className="btn"),
                                html.Button("Apply target settings", id="apply-target-settings", className="btn btn-primary"),
                            ], className="button-row"),
                        ], id="target-controls", className="target-controls"),
                        html.Label("Validated entity JSON"),
                        dcc.Textarea(id="entity-json", spellCheck=False),
                        html.Div([
                            html.Button("Apply changes", id="save-entity", className="btn btn-primary"),
                            html.Button("Delete", id="delete-entity", className="btn btn-danger"),
                        ], className="button-row"),
                        html.Div(id="notice", className="alert"),
                        html.P("Edit waypoints, sensor limits, refresh rates, probabilities, emitter events, and AIS events directly. Invalid changes are rejected without altering the scenario.", className="hint"),
                    ], className="panel"
                ),
            ], className="workspace"
        ),
        html.Footer(
            [
                html.Section([
                    html.Div("Simulation timeline", className="panel-title"),
                    html.Div([
                        html.Button("▶", id="play", className="btn btn-primary", title="Play"),
                        html.Button("Ⅱ", id="pause", className="btn", title="Pause"),
                        html.Button("↺", id="restart", className="btn", title="Restart"),
                        html.Div(id="time-readout", className="time-readout"),
                        dcc.Dropdown(id="playback-speed", options=[{"label": f"{value}×", "value": value} for value in (.5, 1, 2, 5, 10)],
                                     value=1, clearable=False, style={"width": "78px"}),
                    ], className="transport"),
                    dcc.Slider(id="timeline", min=0, max=300, value=0, step=1, tooltip={"placement": "bottom"}),
                    html.Div(id="event-log", className="event-log"),
                ], className="timeline-panel"),
                html.Section([
                    html.Div("Generated sensor files", className="panel-title"),
                    html.Div([
                        html.Button("Generate outputs", id="generate", className="btn btn-primary"),
                        html.Button("Download all JSON", id="download-all", className="btn"),
                    ], className="button-row"),
                    dcc.Loading(html.Div(id="export-list"), id="generation-loading", type="circle", color="#4de2df"),
                ], className="export-panel"),
            ], className="bottom-dock"
        ),
    ], className="app-shell"
)


@app.callback(
    Output("placement-mode", "data"),
    Input({"type": "palette", "kind": ALL}, "n_clicks"),
    Input("add-waypoint", "n_clicks"),
    State("entity-select", "value"),
    prevent_initial_call=True,
)
def choose_placement(_: list[int], _add_waypoint: int, selected_id: str | None) -> str:
    triggered = ctx.triggered_id
    if triggered == "add-waypoint":
        return f"waypoint:{selected_id}" if selected_id else no_update
    return triggered["kind"] if isinstance(triggered, dict) else no_update


@app.callback(Output("placement-banner", "children"), Input("placement-mode", "data"))
def placement_banner(mode: str | None) -> str:
    if not mode:
        return "SELECT A PALETTE ITEM TO PLACE"
    if mode.startswith("waypoint:"):
        return f"WAYPOINT MODE · {mode.split(':', 1)[1]} · CLICK MAP"
    return f"PLACEMENT ACTIVE · {mode.replace('_', ' ').upper()} · CLICK MAP"


@app.callback(
    Output("scenario-store", "data"),
    Output("notice", "children"),
    Output("notice", "className"),
    Input("tactical-map", "clickData"),
    Input("save-entity", "n_clicks"),
    Input("apply-target-settings", "n_clicks"),
    Input("delete-entity", "n_clicks"),
    Input("save-scenario", "n_clicks"),
    Input("reset-demo", "n_clicks"),
    Input("scenario-upload", "contents"),
    Input({"type": "entity-marker", "id": ALL}, "position"),
    State("scenario-store", "data"),
    State("placement-mode", "data"),
    State("entity-select", "value"),
    State("entity-json", "value"),
    State("target-emcon", "value"),
    State("target-range-radar_2d", "value"),
    State("target-range-radar_3d", "value"),
    State("target-range-eoir", "value"),
    State("target-range-ew", "value"),
    State("target-range-cctv", "value"),
    State("target-range-ais", "value"),
    State("target-range-sar", "value"),
    State("scenario-name", "value"),
    State("scenario-duration", "value"),
    State("scenario-seed", "value"),
    prevent_initial_call=True,
)
def mutate_scenario(click_data, _save, _apply_target, _delete, _settings, _reset, upload_contents, _positions,
                    raw_scenario, placement_mode, selected_id, entity_json, emcon_mode,
                    radar_2d_range, radar_3d_range, eoir_range, ew_range, cctv_range, ais_range, sar_range,
                    scenario_name, duration, seed):
    trigger = ctx.triggered_id
    try:
        if trigger == "reset-demo":
            return scenario_dict(), "Demonstration scenario restored.", "alert"
        if trigger == "scenario-upload":
            if not upload_contents:
                return no_update, no_update, no_update
            encoded = upload_contents.split(",", 1)[1]
            parsed = json.loads(base64.b64decode(encoded).decode("utf-8"))
            loaded = Scenario.model_validate(parsed)
            return loaded.model_dump(mode="json"), f"Imported {loaded.name}.", "alert"

        scenario = Scenario.model_validate(raw_scenario)
        if trigger == "save-scenario":
            updated = scenario.model_copy(update={"name": scenario_name, "duration_s": int(duration), "random_seed": int(seed)})
            updated = Scenario.model_validate(updated.model_dump())
            return updated.model_dump(mode="json"), "Scenario settings saved.", "alert"
        if trigger == "save-entity":
            if not selected_id:
                raise ValueError("Select an entity first.")
            candidate = json.loads(entity_json)
            payload = scenario.model_dump(mode="json")
            collection = "sensors" if any(item["sensor_id"] == selected_id for item in payload["sensors"]) else "contacts"
            id_field = "sensor_id" if collection == "sensors" else "contact_id"
            index = next(index for index, item in enumerate(payload[collection]) if item[id_field] == selected_id)
            payload[collection][index] = candidate
            updated = Scenario.model_validate(payload)
            return updated.model_dump(mode="json"), f"Saved {candidate[id_field]}.", "alert"
        if trigger == "apply-target-settings":
            if not selected_id:
                raise ValueError("Select a target first.")
            payload = scenario.model_dump(mode="json")
            contact = next((item for item in payload["contacts"] if item["contact_id"] == selected_id), None)
            if contact is None:
                raise ValueError("EMCON and target detectability apply to contacts, not sensors.")
            contact["emcon_mode"] = emcon_mode
            range_values = [radar_2d_range, radar_3d_range, eoir_range, ew_range, cctv_range, ais_range, sar_range]
            contact["detectable_range_km"] = {
                sensor_type: float(value) for sensor_type, value in zip(TARGET_RANGE_TYPES, range_values) if value is not None
            }
            updated = Scenario.model_validate(payload)
            return updated.model_dump(mode="json"), f"Updated EMCON and detectability for {selected_id}.", "alert"
        if trigger == "delete-entity":
            if not selected_id:
                raise ValueError("Select an entity first.")
            payload = scenario.model_dump(mode="json")
            payload["sensors"] = [item for item in payload["sensors"] if item["sensor_id"] != selected_id]
            payload["contacts"] = [item for item in payload["contacts"] if item["contact_id"] != selected_id]
            payload["fusion_mappings"] = [item for item in payload["fusion_mappings"]
                                          if item["contact_id"] != selected_id and item["fusion_sensor_id"] != selected_id]
            for sensor in payload["sensors"]:
                if sensor.get("source_ais_sensor_id") == selected_id:
                    sensor["source_ais_sensor_id"] = ""
                if sensor.get("source_sar_sensor_id") == selected_id:
                    sensor["source_sar_sensor_id"] = ""
            updated = Scenario.model_validate(payload)
            return updated.model_dump(mode="json"), f"Deleted {selected_id}.", "alert"
        if trigger == "tactical-map":
            if not placement_mode or not click_data:
                return no_update, no_update, no_update
            latitude, longitude = click_data["latlng"]["lat"], click_data["latlng"]["lng"]
            payload = scenario.model_dump(mode="json")
            if placement_mode.startswith("waypoint:"):
                contact_id = placement_mode.split(":", 1)[1]
                contact = next((item for item in scenario.contacts if item.contact_id == contact_id), None)
                if contact is None:
                    raise ValueError("The selected hostile no longer exists.")
                waypoint = extrapolate_waypoint(contact, latitude, longitude)
                contact_payload = next(item for item in payload["contacts"] if item["contact_id"] == contact_id)
                contact_payload["waypoints"].append(waypoint.model_dump(mode="json"))
                payload["duration_s"] = max(payload["duration_s"], math.ceil(waypoint.time_s))
                updated = Scenario.model_validate(payload)
                return (updated.model_dump(mode="json"),
                        f"Added waypoint {len(contact_payload['waypoints'])} to {contact_id} at {relative_timestamp(waypoint.time_s)}.",
                        "alert")
            if placement_mode in SENSOR_CLASSES:
                count = sum(sensor["sensor_type"] == placement_mode for sensor in payload["sensors"]) + 1
                sensor_id = f"{placement_mode.upper()}_{count:02d}"
                owner = "Navy" if placement_mode in {"ais", "sar", "fusion"} else "Army" if placement_mode in {"ew", "cctv"} else "Air"
                sensor = SENSOR_CLASSES[placement_mode](sensor_id=sensor_id, name=f"New {placement_mode.replace('_', ' ').upper()}",
                                                        owner=owner, latitude=latitude, longitude=longitude)
                payload["sensors"].append(sensor.model_dump(mode="json"))
                placed_id = sensor_id
            else:
                count = sum(contact["domain"] == placement_mode for contact in payload["contacts"]) + 1
                contact_id = f"HOSTILE_{placement_mode.upper()}_{count:02d}"
                contact = Contact(contact_id=contact_id, name=f"Hostile {placement_mode.title()} {count}", domain=placement_mode,
                                  subtype="fixed-wing" if placement_mode == "air" else "vessel",
                                  emcon_mode="active", detectable_range_km=(
                                      {"radar_2d": 35, "radar_3d": 40, "eoir": 20, "ew": 50}
                                      if placement_mode == "air" else {"eoir": 20, "cctv": 15, "ais": 80, "sar": 100}
                                  ),
                                  waypoints=[Waypoint(latitude=latitude, longitude=longitude, altitude_m=1000 if placement_mode == "air" else 0,
                                                      time_s=0, speed_kts=100 if placement_mode == "air" else 15)])
                payload["contacts"].append(contact.model_dump(mode="json"))
                placed_id = contact_id
            updated = Scenario.model_validate(payload)
            return updated.model_dump(mode="json"), f"Placed {placed_id}. Select it in the inspector to configure it.", "alert"
        if isinstance(trigger, dict) and trigger.get("type") == "entity-marker":
            new_position = ctx.triggered[0].get("value")
            if not new_position:
                return no_update, no_update, no_update
            entity_id = trigger["id"]
            payload = scenario.model_dump(mode="json")
            changed = False
            for sensor in payload["sensors"]:
                if sensor["sensor_id"] == entity_id:
                    old_position = [sensor["latitude"], sensor["longitude"]]
                    if any(abs(float(old) - float(new)) > 1e-9 for old, new in zip(old_position, new_position)):
                        sensor["latitude"], sensor["longitude"] = new_position
                        changed = True
            for contact in payload["contacts"]:
                if contact["contact_id"] == entity_id:
                    old_position = [contact["waypoints"][0]["latitude"], contact["waypoints"][0]["longitude"]]
                    if any(abs(float(old) - float(new)) > 1e-9 for old, new in zip(old_position, new_position)):
                        contact["waypoints"][0]["latitude"], contact["waypoints"][0]["longitude"] = new_position
                        changed = True
            if not changed:
                return no_update, no_update, no_update
            updated = Scenario.model_validate(payload)
            return updated.model_dump(mode="json"), f"Moved {entity_id}.", "alert"
        return no_update, no_update, no_update
    except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as error:
        return no_update, f"Change rejected:\n{error}", "alert error"


@app.callback(
    Output("scenario-name", "value"), Output("scenario-duration", "value"), Output("scenario-seed", "value"),
    Output("timeline", "max"),
    Input("scenario-store", "data"),
)
def render_scenario_settings(raw_scenario):
    scenario = Scenario.model_validate(raw_scenario)
    return scenario.name, scenario.duration_s, scenario.random_seed, scenario.duration_s


@app.callback(
    Output("entity-select", "options"), Output("entity-select", "value"),
    Input("scenario-store", "data"), State("entity-select", "value"),
)
def entity_options(raw_scenario, selected):
    scenario = Scenario.model_validate(raw_scenario)
    options = ([{"label": f"SENSOR · {item.name}", "value": item.sensor_id} for item in scenario.sensors] +
               [{"label": f"HOSTILE · {item.name}", "value": item.contact_id} for item in scenario.contacts])
    values = {option["value"] for option in options}
    return options, selected if selected in values else None


@app.callback(
    Output("entity-json", "value"), Output("entity-heading", "children"), Output("target-controls", "style"),
    Output("target-emcon", "value"),
    *[Output(f"target-range-{sensor_type}", "value") for sensor_type in TARGET_RANGE_TYPES],
    Input("entity-select", "value"), Input("scenario-store", "data"),
)
def render_entity_editor(selected, raw_scenario):
    if not selected:
        return "", "No entity selected", {"display": "none"}, None, *([None] * len(TARGET_RANGE_TYPES))
    scenario = Scenario.model_validate(raw_scenario)
    for sensor in scenario.sensors:
        if sensor.sensor_id == selected:
            return (json.dumps(sensor.model_dump(mode="json"), indent=2),
                    f"{sensor.sensor_type.upper().replace('_', ' ')} · {sensor.owner}",
                    {"display": "none"}, None, *([None] * len(TARGET_RANGE_TYPES)))
    for contact in scenario.contacts:
        if contact.contact_id == selected:
            values = [contact.detectable_range_km.get(sensor_type) for sensor_type in TARGET_RANGE_TYPES]
            return (json.dumps(contact.model_dump(mode="json"), indent=2),
                    f"{contact.domain.upper()} CONTACT · HOSTILE", {"display": "block"}, contact.emcon_mode, *values)
    return "", "Entity no longer exists", {"display": "none"}, None, *([None] * len(TARGET_RANGE_TYPES))


def marker_icon(category: str) -> dict[str, Any]:
    class_name = "sensor-dot" if category == "sensor" else "air-dot" if category == "air" else "surface-dot"
    return {"iconUrl": "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=", "iconSize": [18, 18],
            "iconAnchor": [9, 9], "className": f"entity-icon entity-dot {class_name}"}


@app.callback(Output("static-map-layers", "children"), Input("scenario-store", "data"))
def render_static_map_layers(raw_scenario):
    scenario = Scenario.model_validate(raw_scenario)
    layers: list[Any] = []
    for sensor in scenario.sensors:
        color = "#4de2df" if sensor.enabled else "#52656b"
        layers.append(dl.Circle(center=[sensor.latitude, sensor.longitude], radius=sensor.detection_range_km * 1000,
                                color=color, fillColor=color, fillOpacity=.035, opacity=.45, weight=1,
                                dashArray="5 6", interactive=False))
        layers.append(dl.Circle(center=[sensor.latitude, sensor.longitude], radius=sensor.classification_range_km * 1000,
                                color="#f4b942", fill=False, opacity=.25, weight=1, interactive=False))
        layers.append(dl.Marker(id={"type": "entity-marker", "id": sensor.sensor_id}, position=[sensor.latitude, sensor.longitude],
                                draggable=True, icon=marker_icon("sensor"), children=[dl.Tooltip(f"{sensor.name} · {sensor.sensor_type}")]))
    for contact in scenario.contacts:
        route = [[point.latitude, point.longitude] for point in contact.waypoints]
        if len(route) > 1:
            layers.append(dl.Polyline(positions=route, color="#ff5d6c" if contact.domain == "air" else "#f4b942",
                                      weight=3, dashArray="7 7", opacity=.9, interactive=False))
        for index, point in enumerate(contact.waypoints, start=1):
            color = "#ff5d6c" if contact.domain == "air" else "#f4b942"
            layers.append(dl.CircleMarker(center=[point.latitude, point.longitude], radius=5, color="#071016",
                                          fillColor=color, fillOpacity=1, opacity=1, weight=2,
                                          children=[dl.Tooltip(f"WP{index} · {relative_timestamp(point.time_s)} · {point.speed_kts:.0f} kt")]))
    return layers


@app.callback(Output("dynamic-map-layers", "children"), Input("scenario-store", "data"), Input("playback-store", "data"))
def render_dynamic_map_layers(raw_scenario, playback):
    scenario = Scenario.model_validate(raw_scenario)
    time_s = float(playback.get("time_s", 0))
    layers: list[Any] = []
    states: dict[str, dict[str, float]] = {}
    for contact in scenario.contacts:
        state = contact_state_at(contact, time_s)
        states[contact.contact_id] = state
        label = f"{contact.name} · {state['altitude_m']:.0f} m · {state['speed_kts']:.0f} kt"
        layers.append(dl.Marker(position=[state["latitude"], state["longitude"]], draggable=False,
                                icon=marker_icon(contact.domain), children=[dl.Tooltip(label, permanent=True, direction="top")]))
    for sensor in scenario.sensors:
        if not sensor.enabled or sensor.sensor_type == "fusion":
            continue
        for contact in scenario.contacts:
            state = states[contact.contact_id]
            eligible, _, _, _ = _eligible(sensor, contact, state)
            if eligible:
                layers.append(dl.Polyline(positions=[[sensor.latitude, sensor.longitude], [state["latitude"], state["longitude"]]],
                                          color="#70e69a", weight=1, opacity=.35, dashArray="2 6", interactive=False))
    return layers


@app.callback(
    Output("playback-store", "data"), Output("timeline", "value"),
    Input("play", "n_clicks"), Input("pause", "n_clicks"), Input("restart", "n_clicks"),
    Input("playback-interval", "n_intervals"), Input("timeline", "value"), Input("playback-speed", "value"),
    State("playback-store", "data"), State("scenario-store", "data"), prevent_initial_call=True,
)
def update_playback(_play, _pause, _restart, _ticks, slider_value, speed, playback, raw_scenario):
    scenario = Scenario.model_validate(raw_scenario)
    playback = dict(playback or {"time_s": 0, "playing": False, "speed": 1})
    trigger = ctx.triggered_id
    playback["speed"] = speed or 1
    if trigger == "play":
        playback["playing"] = True
    elif trigger == "pause":
        playback["playing"] = False
    elif trigger == "restart":
        playback.update(time_s=0, playing=False)
    elif trigger == "timeline":
        playback["time_s"] = float(slider_value or 0)
    elif trigger == "playback-interval" and playback["playing"]:
        playback["time_s"] = min(scenario.duration_s, playback["time_s"] + .5 * playback["speed"])
        if playback["time_s"] >= scenario.duration_s:
            playback["playing"] = False
    return playback, playback["time_s"]


@app.callback(Output("time-readout", "children"), Output("event-log", "children"), Input("playback-store", "data"), Input("scenario-store", "data"))
def playback_labels(playback, raw_scenario):
    scenario = Scenario.model_validate(raw_scenario)
    time_s = float(playback.get("time_s", 0))
    absolute = scenario.start_time + __import__("datetime").timedelta(seconds=time_s)
    status = "RUNNING" if playback.get("playing") else "PAUSED"
    return relative_timestamp(time_s), f"{status} · {absolute.isoformat()} · {len(scenario.contacts)} contacts · {len(scenario.sensors)} sensors"


@app.callback(Output("playback-interval", "disabled"), Input("playback-store", "data"))
def toggle_playback_timer(playback):
    return not bool((playback or {}).get("playing"))


@app.callback(Output("outputs-store", "data"), Output("export-list", "children", allow_duplicate=True),
              Output("notice", "children", allow_duplicate=True), Output("notice", "className", allow_duplicate=True),
              Input("generate", "n_clicks"), State("scenario-store", "data"), prevent_initial_call=True,
              running=[
                  (Output("generate", "disabled"), True, False),
                  (Output("generate", "children"), "Generating…", "Generate outputs"),
                  (Output("download-all", "disabled"), True, False),
              ])
def generate(_clicks, raw_scenario):
    try:
        started = time.perf_counter()
        scenario = Scenario.model_validate(raw_scenario)
        outputs = generate_outputs(scenario)
        count = sum(len(messages) for messages in outputs.values())
        elapsed = time.perf_counter() - started
        return outputs, build_export_rows(scenario, outputs), f"Generated {count:,} messages across {len(outputs)} sensor files in {elapsed:.2f} s.", "alert"
    except (ValidationError, ValueError) as error:
        return no_update, no_update, f"Generation failed:\n{error}", "alert error"


def build_export_rows(scenario: Scenario, outputs: dict | None):
    rows = []
    for sensor in scenario.sensors:
        count = len((outputs or {}).get(sensor.sensor_id, []))
        rows.append(html.Div([
            html.Span(f"{sensor.sensor_id} · {sensor.sensor_type}"),
            html.Span(f"{count:,}", className="count"),
            html.Button("Download", id={"type": "download-one", "id": sensor.sensor_id}, className="btn", disabled=count == 0),
            dcc.Download(id={"type": "sensor-download", "id": sensor.sensor_id}),
        ], className="export-row"))
    return rows or html.P("No sensors configured.", className="hint")


@app.callback(Output("export-list", "children"), Input("scenario-store", "data"), State("outputs-store", "data"))
def render_exports(raw_scenario, outputs):
    return build_export_rows(Scenario.model_validate(raw_scenario), outputs)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-_") or "scenario"


@app.callback(Output({"type": "sensor-download", "id": MATCH}, "data"),
              Input({"type": "download-one", "id": MATCH}, "n_clicks"),
              State("outputs-store", "data"), State("scenario-store", "data"), prevent_initial_call=True)
def download_sensor(_clicks, outputs, raw_scenario):
    sensor_id = ctx.triggered_id["id"]
    scenario = Scenario.model_validate(raw_scenario)
    sensor = next(sensor for sensor in scenario.sensors if sensor.sensor_id == sensor_id)
    filename = f"{safe_filename(scenario.name)}_{safe_filename(sensor_id)}_{sensor.sensor_type}.json"
    return dcc.send_string(json.dumps((outputs or {}).get(sensor_id, []), indent=2), filename)


@app.callback(Output("scenario-download", "data"), Input("export-scenario", "n_clicks"), State("scenario-store", "data"), prevent_initial_call=True)
def download_scenario(_clicks, raw_scenario):
    scenario = Scenario.model_validate(raw_scenario)
    return dcc.send_string(json.dumps(scenario.model_dump(mode="json"), indent=2), f"{safe_filename(scenario.name)}_scenario.json")


app.clientside_callback(
    """
    function(n, outputs, scenario) {
        if (!n || !outputs || !scenario) return window.dash_clientside.no_update;
        const safe = (s) => (s || 'scenario').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-_]+|[-_]+$/g, '');
        for (const sensor of scenario.sensors || []) {
            const messages = outputs[sensor.sensor_id] || [];
            const blob = new Blob([JSON.stringify(messages, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${safe(scenario.name)}_${safe(sensor.sensor_id)}_${sensor.sensor_type}.json`;
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        return `downloaded-${Date.now()}`;
    }
    """,
    Output("all-download-sink", "children"), Input("download-all", "n_clicks"),
    State("outputs-store", "data"), State("scenario-store", "data"), prevent_initial_call=True,
)


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
