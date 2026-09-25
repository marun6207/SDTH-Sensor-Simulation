from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Observation(ContractModel):
    timestamp: datetime
    lat: float = Field(ge=-90, le=90)
    longitude: float = Field(alias="long", ge=-180, le=180)
    altitude: float = Field(ge=-500)
    speed: float | None = Field(default=None, ge=0)
    vehicle_type: str | None = Field(default=None, alias="type", max_length=120)

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("timestamp must be an RFC 3339 UTC string ending in Z")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("timestamp must be valid RFC 3339") from exc
        if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("timestamp must use UTC")
        return parsed

    @field_validator("lat", "longitude", "altitude", "speed", mode="before")
    @classmethod
    def validate_finite_number(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("value must be a JSON number")
        if not math.isfinite(float(value)):
            raise ValueError("value must be finite")
        return float(value)

    @field_validator("vehicle_type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("type must be non-empty or null")
        return value

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ForecastConfig(ContractModel):
    horizon_s: int = Field(default=900, ge=1, le=86400)
    step_s: int = Field(default=30, ge=1)
    fit_window_observations: int = Field(default=6, ge=2, le=100)
    domain_altitude_threshold_m: float = Field(default=5, ge=-500, le=10000)
    base_horizontal_uncertainty_m: float = Field(default=100, gt=0)
    base_vertical_uncertainty_m: float = Field(default=50, gt=0)
    likely_residual_multiplier: float = Field(default=2, gt=0)
    speed_disagreement_ratio: float = Field(default=.25, gt=0)
    infrastructure_point_buffer_m: float = Field(default=100, gt=0)
    infrastructure_line_buffer_m: float = Field(default=50, gt=0)

    @model_validator(mode="after")
    def validate_steps(self) -> "ForecastConfig":
        if self.step_s > self.horizon_s:
            raise ValueError("step_s cannot exceed horizon_s")
        return self


class DomainResult(ContractModel):
    value: Literal["air", "surface"]
    source: Literal["first_observation_altitude", "override"]
    override: bool


class MobilityProfile(ContractModel):
    name: str
    domain: Literal["air", "surface"]
    min_speed_mps: float = Field(ge=0)
    max_speed_mps: float = Field(gt=0)
    max_acceleration_mps2: float = Field(gt=0)
    max_turn_rate_deg_s: float = Field(gt=0)
    max_climb_rate_mps: float = Field(ge=0)
    max_descent_rate_mps: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_speed_range(self) -> "MobilityProfile":
        if self.min_speed_mps > self.max_speed_mps:
            raise ValueError("minimum speed cannot exceed maximum speed")
        return self


class InfrastructureFeature(ContractModel):
    osm_type: Literal["node", "way", "relation", "anonymous"]
    osm_id: int | str
    version: int = 0
    category: str
    display_name: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    geometry: dict[str, Any]


class SnapshotManifest(ContractModel):
    schema_version: Literal[1] = 1
    snapshot_id: str
    created_at: datetime
    osm_data_timestamp: str | None = None
    endpoint: str
    query: str
    catalog_version: str
    coverage: dict[str, Any]
    raw_sha256: str
    features_sha256: str
    attribution: str = "© OpenStreetMap contributors"

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class InfrastructureSnapshot(ContractModel):
    path: str
    manifest: SnapshotManifest
    features: list[InfrastructureFeature]


def parse_track(document: Any) -> list[Observation]:
    if not isinstance(document, list):
        raise ValueError("track document must be a JSON array")
    if not document:
        raise ValueError("track array must contain at least one observation")
    observations = [Observation.model_validate(item) for item in document]
    for previous, current in zip(observations, observations[1:]):
        if current.timestamp <= previous.timestamp:
            raise ValueError("observation timestamps must be strictly increasing in array order")
    return observations


def infer_domain(
    observations: list[Observation],
    override: Literal["air", "surface"] | None = None,
    threshold_m: float = 5,
) -> DomainResult:
    if not observations:
        raise ValueError("cannot infer domain without observations")
    if override:
        return DomainResult(value=override, source="override", override=True)
    value = "air" if observations[0].altitude > threshold_m else "surface"
    return DomainResult(value=value, source="first_observation_altitude", override=False)
