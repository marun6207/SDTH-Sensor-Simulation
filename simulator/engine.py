from __future__ import annotations

import hashlib
import math
from datetime import timedelta
from typing import Any

import numpy as np
from pyproj import Geod

from .models import AisEvent, Contact, FusionSensor, Scenario, Sensor, Waypoint

GEOD = Geod(ellps="WGS84")


def relative_timestamp(seconds: float) -> str:
    seconds = int(round(seconds)) % 86400
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _stable_track(prefix: str, sensor_id: str, contact_id: str) -> str:
    value = int(hashlib.sha1(f"{sensor_id}|{contact_id}".encode()).hexdigest()[:6], 16) % 1000
    return f"{prefix}-{value:03d}"


def angular_difference(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def geodesic_metrics(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    bearing, _, distance_m = GEOD.inv(lon1, lat1, lon2, lat2)
    return distance_m / 1000, bearing % 360


def extrapolate_waypoint(contact: Contact, latitude: float, longitude: float) -> Waypoint:
    """Create the next waypoint using the previous waypoint's speed and hold."""
    previous = contact.waypoints[-1]
    if previous.speed_kts <= 0:
        raise ValueError("the previous waypoint speed must be greater than zero")
    distance_km, _ = geodesic_metrics(previous.latitude, previous.longitude, latitude, longitude)
    travel_seconds = distance_km * 0.539956803 / previous.speed_kts * 3600
    return Waypoint(
        latitude=latitude,
        longitude=longitude,
        altitude_m=previous.altitude_m,
        time_s=previous.time_s + previous.hold_s + travel_seconds,
        speed_kts=previous.speed_kts,
    )


def contact_state_at(contact: Contact, time_s: float) -> dict[str, float]:
    points = contact.waypoints
    if time_s <= points[0].time_s:
        point = points[0]
        course = _leg_course(points, 0)
        return _point_state(point.latitude, point.longitude, point.altitude_m, point.speed_kts, course)
    if time_s >= points[-1].time_s:
        point = points[-1]
        course = _leg_course(points, max(0, len(points) - 2))
        return _point_state(point.latitude, point.longitude, point.altitude_m, point.speed_kts, course)

    for index, (start, end) in enumerate(zip(points, points[1:])):
        if start.time_s <= time_s <= end.time_s:
            leg_start = start.time_s + start.hold_s
            if time_s <= leg_start:
                return _point_state(start.latitude, start.longitude, start.altitude_m, 0, _leg_course(points, index))
            fraction = min(1.0, (time_s - leg_start) / max(end.time_s - leg_start, 1e-9))
            azimuth, _, distance_m = GEOD.inv(start.longitude, start.latitude, end.longitude, end.latitude)
            longitude, latitude, _ = GEOD.fwd(start.longitude, start.latitude, azimuth, distance_m * fraction)
            altitude = start.altitude_m + (end.altitude_m - start.altitude_m) * fraction
            speed = end.speed_kts or start.speed_kts
            return _point_state(latitude, longitude, altitude, speed, azimuth % 360)
    raise RuntimeError("contact interpolation failed")


def _leg_course(points: list[Any], index: int) -> float:
    if len(points) < 2:
        return 0
    start, end = points[index], points[min(index + 1, len(points) - 1)]
    course, _, _ = GEOD.inv(start.longitude, start.latitude, end.longitude, end.latitude)
    return course % 360


def _point_state(lat: float, lon: float, altitude: float, speed: float, course: float) -> dict[str, float]:
    return {"latitude": lat, "longitude": lon, "altitude_m": altitude, "speed_kts": speed, "course_deg": course}


def _event_state(events: list[Any], time_s: float, default: Any) -> Any:
    state = default
    for event in events:
        if event.time_s <= time_s:
            state = event
        else:
            break
    return state


def _eligible(sensor: Sensor, contact: Contact, state: dict[str, float]) -> tuple[bool, float, float, float]:
    distance_km, bearing = geodesic_metrics(sensor.latitude, sensor.longitude, state["latitude"], state["longitude"])
    elevation = math.degrees(math.atan2(state["altitude_m"], max(distance_km * 1000, 1e-9)))
    domain_ok = {
        "ais": contact.domain == "surface",
        "sar": contact.domain == "surface",
        "cctv": contact.domain == "surface",
        "ew": contact.domain == "air",
        "fusion": False,
    }.get(sensor.sensor_type, True)
    emissions_ok = not (
        (sensor.sensor_type == "ew" and contact.emcon_mode != "active")
        or (sensor.sensor_type == "ais" and contact.emcon_mode == "silent")
    )
    fov_ok = sensor.field_of_view_deg >= 360 or angular_difference(bearing, sensor.orientation_deg) <= sensor.field_of_view_deg / 2
    altitude_ok = sensor.min_altitude_m <= state["altitude_m"] <= sensor.max_altitude_m
    target_limit = contact.detectable_range_km.get(sensor.sensor_type, sensor.detection_range_km)
    effective_range = min(sensor.detection_range_km, target_limit)
    return domain_ok and emissions_ok and distance_km <= effective_range and fov_ok and altitude_ok, distance_km, bearing, elevation


def _base(sensor: Sensor, time_s: float) -> dict[str, Any]:
    return {"sensor_id": sensor.sensor_id, "timestamp": relative_timestamp(time_s)}


def _message(sensor: Sensor, contact: Contact, state: dict[str, float], time_s: float, distance: float, bearing: float,
             elevation: float, classified: bool, confidence: float) -> dict[str, Any] | None:
    subtype = contact.subtype if classified else "unknown"
    classification = ("UAS" if contact.domain == "air" else "VESSEL") if classified else "UNKNOWN"
    base = _base(sensor, time_s)
    if sensor.sensor_type in ("radar_2d", "radar_3d"):
        base.update(track_id=_stable_track("RDR", sensor.sensor_id, contact.contact_id), azimuth_deg=round(bearing, 1))
        if sensor.sensor_type == "radar_3d":
            base["elevation_deg"] = round(elevation, 1)
        base.update(range_km=round(distance, 2), classification=classification, subtype=subtype)
    elif sensor.sensor_type == "eoir":
        track = _stable_track("EO", sensor.sensor_id, contact.contact_id)
        base.update(track_id=track, azimuth_deg=round(bearing, 1), elevation_deg=round(elevation, 1),
                    classification=classification, subtype=subtype, confidence=round(confidence, 2),
                    image=f"{sensor.sensor_id}_{track}_{int(time_s):05d}.jpg")
    elif sensor.sensor_type == "ew":
        emitter = _event_state(contact.emitter_events, time_s, None)
        if emitter is not None and not emitter.enabled:
            return None
        base.update(emitter_id=_stable_track("RF", sensor.sensor_id, contact.contact_id), detected=True,
                    bearing_deg=round(bearing, 1), classification="suspected_uas_link" if classified else "unknown_emitter",
                    confidence=round(confidence, 2))
    elif sensor.sensor_type == "cctv":
        track = _stable_track("CCTV", sensor.sensor_id, contact.contact_id)
        base.update(track_id=track, azimuth_deg=round(bearing, 1),
                    range_km=round(distance, 2), classification=classification, subtype=subtype,
                    confidence=round(confidence, 2), image=f"{sensor.sensor_id}_{track}_{int(time_s):05d}.jpg")
    elif sensor.sensor_type == "ais":
        ais: AisEvent | None = _event_state(contact.ais_events, time_s, None)
        if not ais or not ais.enabled:
            return None
        base.update(mmsi=ais.mmsi, vessel_name=ais.vessel_name, latitude=round(state["latitude"], 6),
                    longitude=round(state["longitude"], 6), course_deg=round(state["course_deg"], 1),
                    speed_kts=round(state["speed_kts"], 1), navigation_status="under_way")
    elif sensor.sensor_type == "sar":
        base.update(track_id=_stable_track("SAR", sensor.sensor_id, contact.contact_id),
                    latitude=round(state["latitude"], 6), longitude=round(state["longitude"], 6),
                    confidence=round(confidence, 2), classification=classification, subtype=subtype)
    else:
        return None
    return base


def generate_outputs(scenario: Scenario) -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {sensor.sensor_id: [] for sensor in scenario.sensors}
    seed_sequence = np.random.SeedSequence(scenario.random_seed)
    regular_sensors = [sensor for sensor in scenario.sensors if sensor.sensor_type != "fusion"]
    random_generators = {sensor.sensor_id: np.random.default_rng(seq) for sensor, seq in zip(regular_sensors, seed_sequence.spawn(len(regular_sensors)))}

    for sensor in regular_sensors:
        if not sensor.enabled:
            continue
        rng = random_generators[sensor.sensor_id]
        ticks = np.arange(0, scenario.duration_s + 1e-9, sensor.refresh_rate_s)
        for time_s in ticks:
            for contact in scenario.contacts:
                state = contact_state_at(contact, float(time_s))
                eligible, distance, bearing, elevation = _eligible(sensor, contact, state)
                if not eligible or rng.random() > sensor.detection_probability:
                    continue
                can_classify = distance <= sensor.classification_range_km and rng.random() <= sensor.classification_probability
                confidence = sensor.classification_probability if can_classify else max(0.05, sensor.detection_probability * 0.5)
                message = _message(sensor, contact, state, float(time_s), distance, bearing, elevation, can_classify, confidence)
                if message:
                    message["_contact_id"] = contact.contact_id
                    outputs[sensor.sensor_id].append(message)

    for sensor in scenario.sensors:
        if sensor.sensor_type == "fusion" and sensor.enabled:
            outputs[sensor.sensor_id] = _generate_fusion(sensor, scenario, outputs)
    for messages in outputs.values():
        for message in messages:
            message.pop("_contact_id", None)
    return outputs


def _generate_fusion(sensor: FusionSensor, scenario: Scenario, outputs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ais_messages = outputs.get(sensor.source_ais_sensor_id, [])
    sar_messages = outputs.get(sensor.source_sar_sensor_id, [])
    mappings = [mapping for mapping in scenario.fusion_mappings if mapping.fusion_sensor_id == sensor.sensor_id]
    for mapping in mappings:
        contact_ais = [msg for msg in ais_messages if msg.get("_contact_id") == mapping.contact_id and msg.get("mmsi") == mapping.ais_identity]
        contact_sar = [msg for msg in sar_messages if msg.get("_contact_id") == mapping.contact_id and msg.get("track_id") == mapping.sar_track_id]
        for sar in contact_sar:
            sar_second = _timestamp_seconds(sar["timestamp"])
            match = min(contact_ais, key=lambda msg: abs(_timestamp_seconds(msg["timestamp"]) - sar_second), default=None)
            if match and abs(_timestamp_seconds(match["timestamp"]) - sar_second) <= mapping.tolerance_s:
                results.append({**_base(sensor, sar_second), "correlation_id": f"COR-{len(results)+1:03d}",
                                "ais_identity": mapping.ais_identity, "sar_track_id": mapping.sar_track_id,
                                "contact_id": mapping.contact_id, "status": "correlated", "confidence": sar["confidence"]})
    return results


def _timestamp_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds
