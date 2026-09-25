from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .models import (
    AisEvent,
    AisSensor,
    CctvSensor,
    Contact,
    EmitterEvent,
    EoirSensor,
    EwSensor,
    FusionMapping,
    FusionSensor,
    Radar2DSensor,
    Radar3DSensor,
    SarSensor,
    Scenario,
    Waypoint,
)


def _track(prefix: str, sensor_id: str, contact_id: str) -> str:
    value = int(hashlib.sha1(f"{sensor_id}|{contact_id}".encode()).hexdigest()[:6], 16) % 1000
    return f"{prefix}-{value:03d}"


def build_demo_scenario() -> Scenario:
    sensors = [
        Radar3DSensor(sensor_id="GIRAFFE_AIRBASE_01", name="Giraffe 3D Radar", owner="Air", latitude=1.365,
                      longitude=103.902, detection_range_km=45, classification_range_km=25, refresh_rate_s=5,
                      detection_probability=.98, classification_probability=.92),
        Radar2DSensor(sensor_id="MPSTAR_AIRBASE_01", name="MPSTAR Radar", owner="Air", latitude=1.334,
                      longitude=103.889, detection_range_km=35, classification_range_km=20, refresh_rate_s=6),
        EoirSensor(sensor_id="EOIR_AIRBASE_01", name="Airbase EO/IR", owner="Air", latitude=1.350,
                   longitude=103.920, orientation_deg=45, field_of_view_deg=120, detection_range_km=28,
                   classification_range_km=22, refresh_rate_s=8, classification_probability=.91),
        EwSensor(sensor_id="ARMY_EW_01", name="Army EW Direction Finder", owner="Army", latitude=1.305,
                 longitude=103.825, orientation_deg=45, field_of_view_deg=180, detection_range_km=60,
                 classification_range_km=45, refresh_rate_s=10, classification_probability=.86),
        CctvSensor(sensor_id="CCTV_COASTAL_01", name="Coastal Surveillance CCTV", owner="Army", latitude=1.270,
                   longitude=103.930, orientation_deg=150, field_of_view_deg=180, detection_range_km=30,
                   classification_range_km=18, refresh_rate_s=10, detection_probability=.98,
                   classification_probability=.9),
        EoirSensor(sensor_id="EOIR_NAVYBASE_01", name="Navy EO/IR", owner="Navy", latitude=1.255,
                   longitude=103.930, orientation_deg=100, field_of_view_deg=160, detection_range_km=35,
                   classification_range_km=24, refresh_rate_s=10),
        AisSensor(sensor_id="AIS_OCEANS_X", name="MPA OCEANS-X AIS", owner="Navy", latitude=1.245,
                  longitude=103.890, detection_range_km=80, classification_range_km=80, refresh_rate_s=15),
        SarSensor(sensor_id="GLINT_SAR_01", name="GLINT / Sentinel-1 SAR", owner="Navy", latitude=1.210,
                  longitude=103.850, detection_range_km=120, classification_range_km=70, refresh_rate_s=60,
                  detection_probability=.95, classification_probability=.8),
        FusionSensor(sensor_id="AIS_SAR_FUSION_01", name="AIS + SAR Correlation", owner="Navy", latitude=1.245,
                     longitude=103.890, detection_range_km=120, classification_range_km=120, refresh_rate_s=15,
                     source_ais_sensor_id="AIS_OCEANS_X", source_sar_sensor_id="GLINT_SAR_01"),
    ]
    contacts = [
        Contact(contact_id="HOSTILE_UAS_01", name="Red Kite", domain="air", subtype="fixed-wing",
                emcon_mode="active", detectable_range_km={"radar_2d": 38, "radar_3d": 44, "eoir": 24, "ew": 55},
                waypoints=[
                    Waypoint(latitude=1.540, longitude=104.050, altitude_m=2400, time_s=0, speed_kts=140),
                    Waypoint(latitude=1.400, longitude=103.980, altitude_m=1800, time_s=120, speed_kts=135),
                    Waypoint(latitude=1.290, longitude=103.860, altitude_m=900, time_s=240, speed_kts=120),
                    Waypoint(latitude=1.220, longitude=103.790, altitude_m=500, time_s=300, speed_kts=110),
                ], emitter_events=[EmitterEvent(time_s=0, enabled=True), EmitterEvent(time_s=210, enabled=False)]),
        Contact(contact_id="HOSTILE_VESSEL_01", name="Grey Marlin", domain="surface", subtype="cargo",
                emcon_mode="passive", detectable_range_km={"eoir": 25, "cctv": 24, "ais": 80, "sar": 110},
                waypoints=[
                    Waypoint(latitude=1.120, longitude=104.040, time_s=0, speed_kts=18),
                    Waypoint(latitude=1.170, longitude=103.940, time_s=150, speed_kts=18),
                    Waypoint(latitude=1.210, longitude=103.810, time_s=300, speed_kts=16),
                ], ais_events=[
                    AisEvent(time_s=0, enabled=True, mmsi="563009999", vessel_name="MPA OCEANS-X"),
                    AisEvent(time_s=135, enabled=False, mmsi="563009999", vessel_name="MPA OCEANS-X"),
                    AisEvent(time_s=230, enabled=True, mmsi="563008888", vessel_name="NORTH STAR"),
                ]),
    ]
    sar_track = _track("SAR", "GLINT_SAR_01", "HOSTILE_VESSEL_01")
    mappings = [FusionMapping(fusion_sensor_id="AIS_SAR_FUSION_01", contact_id="HOSTILE_VESSEL_01",
                              ais_identity="563009999", sar_track_id=sar_track, tolerance_s=20)]
    return Scenario(scenario_id="demo-singapore", name="Joint Sensor Demonstration",
                    start_time=datetime(2026, 9, 25, 14, 32, tzinfo=timezone.utc), duration_s=300,
                    random_seed=2026, sensors=sensors, contacts=contacts, fusion_mappings=mappings)
