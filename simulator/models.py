from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Waypoint(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: float = Field(default=0, ge=0)
    time_s: float = Field(ge=0)
    speed_kts: float = Field(default=0, ge=0)
    hold_s: float = Field(default=0, ge=0)


class EmitterEvent(StrictModel):
    time_s: float = Field(ge=0)
    enabled: bool


class AisEvent(StrictModel):
    time_s: float = Field(ge=0)
    enabled: bool = True
    mmsi: str = Field(default="", max_length=20)
    vessel_name: str = Field(default="UNKNOWN", max_length=80)


class Contact(StrictModel):
    contact_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    domain: Literal["air", "surface"]
    subtype: str = Field(default="unknown", max_length=60)
    affiliation: Literal["hostile"] = "hostile"
    emcon_mode: Literal["active", "passive", "silent"] = "active"
    detectable_range_km: dict[str, float] = Field(default_factory=dict)
    waypoints: list[Waypoint] = Field(min_length=1)
    emitter_events: list[EmitterEvent] = Field(default_factory=list)
    ais_events: list[AisEvent] = Field(default_factory=list)

    @field_validator("detectable_range_km")
    @classmethod
    def validate_detectable_ranges(cls, values: dict[str, float]) -> dict[str, float]:
        allowed = {"radar_2d", "radar_3d", "eoir", "ew", "cctv", "ais", "sar"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported detectability sensor types: {', '.join(sorted(unknown))}")
        if any(value < 0 for value in values.values()):
            raise ValueError("target detectable ranges cannot be negative")
        return values

    @model_validator(mode="after")
    def validate_timeline(self) -> "Contact":
        times = [p.time_s for p in self.waypoints]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("waypoint times must be unique and increasing")
        if self.domain == "surface" and any(p.altitude_m != 0 for p in self.waypoints):
            raise ValueError("surface waypoint altitude must be zero")
        for events, label in ((self.emitter_events, "emitter"), (self.ais_events, "AIS")):
            event_times = [event.time_s for event in events]
            if event_times != sorted(event_times):
                raise ValueError(f"{label} events must be ordered by time")
        return self


class BaseSensor(StrictModel):
    sensor_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    owner: Literal["Air", "Army", "Navy"] = "Air"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    orientation_deg: float = Field(default=0, ge=0, lt=360)
    detection_range_km: float = Field(default=25, gt=0)
    classification_range_km: float = Field(default=15, gt=0)
    field_of_view_deg: float = Field(default=360, gt=0, le=360)
    min_altitude_m: float = Field(default=0, ge=0)
    max_altitude_m: float = Field(default=20000, ge=0)
    refresh_rate_s: float = Field(default=1, gt=0)
    detection_probability: float = Field(default=1, ge=0, le=1)
    classification_probability: float = Field(default=1, ge=0, le=1)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_ranges(self) -> "BaseSensor":
        if self.classification_range_km > self.detection_range_km:
            raise ValueError("classification range cannot exceed detection range")
        if self.min_altitude_m > self.max_altitude_m:
            raise ValueError("minimum altitude cannot exceed maximum altitude")
        return self


class Radar2DSensor(BaseSensor):
    sensor_type: Literal["radar_2d"] = "radar_2d"


class Radar3DSensor(BaseSensor):
    sensor_type: Literal["radar_3d"] = "radar_3d"


class EoirSensor(BaseSensor):
    sensor_type: Literal["eoir"] = "eoir"


class EwSensor(BaseSensor):
    sensor_type: Literal["ew"] = "ew"


class CctvSensor(BaseSensor):
    sensor_type: Literal["cctv"] = "cctv"
    owner: Literal["Air", "Army", "Navy"] = "Army"


class AisSensor(BaseSensor):
    sensor_type: Literal["ais"] = "ais"
    owner: Literal["Air", "Army", "Navy"] = "Navy"


class SarSensor(BaseSensor):
    sensor_type: Literal["sar"] = "sar"
    owner: Literal["Air", "Army", "Navy"] = "Navy"


class FusionSensor(BaseSensor):
    sensor_type: Literal["fusion"] = "fusion"
    owner: Literal["Air", "Army", "Navy"] = "Navy"
    source_ais_sensor_id: str = ""
    source_sar_sensor_id: str = ""


Sensor = Annotated[
    Union[Radar2DSensor, Radar3DSensor, EoirSensor, EwSensor, CctvSensor, AisSensor, SarSensor, FusionSensor],
    Field(discriminator="sensor_type"),
]


class FusionMapping(StrictModel):
    fusion_sensor_id: str
    contact_id: str
    ais_identity: str
    sar_track_id: str
    tolerance_s: float = Field(default=10, gt=0)


class Scenario(StrictModel):
    schema_version: Literal[1] = 1
    scenario_id: str = Field(default="scenario-001", min_length=1, max_length=64)
    name: str = Field(default="Untitled scenario", min_length=1, max_length=100)
    start_time: datetime
    duration_s: int = Field(default=300, ge=1, le=86400)
    random_seed: int = 42
    sensors: list[Sensor] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    fusion_mappings: list[FusionMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ids_and_references(self) -> "Scenario":
        sensor_ids = [sensor.sensor_id for sensor in self.sensors]
        contact_ids = [contact.contact_id for contact in self.contacts]
        if len(sensor_ids) != len(set(sensor_ids)):
            raise ValueError("sensor IDs must be unique")
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("contact IDs must be unique")
        sensor_id_set, contact_id_set = set(sensor_ids), set(contact_ids)
        for mapping in self.fusion_mappings:
            if mapping.fusion_sensor_id not in sensor_id_set:
                raise ValueError(f"fusion mapping references missing sensor {mapping.fusion_sensor_id}")
            if mapping.contact_id not in contact_id_set:
                raise ValueError(f"fusion mapping references missing contact {mapping.contact_id}")
        return self
