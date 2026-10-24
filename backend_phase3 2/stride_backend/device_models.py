"""Controller telemetry and optional remote cue contracts. No GPIO semantics."""

import json
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, StrictBool, StringConstraints, field_validator

from .models import FrozenModel, Identifier

Count = Annotated[int, Field(ge=0, le=9223372036854775807, strict=True)]
Distance = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]
ObstacleState = Literal["clear", "caution", "danger", "unknown"]
CommandKind = Literal["left", "right", "straight", "stop", "cancel"]
CommandStatus = Literal["issued", "delivered", "received", "executed", "rejected", "expired", "canceled"]


class Telemetry(FrozenModel):
    device_id: Identifier
    boot_id: Identifier
    sequence: Count
    uptime_ms: Count
    distance_cm: Distance | None = None
    measurement_valid: StrictBool = Field(validation_alias=AliasChoices("measurement_valid", "valid"))
    battery_percent: Annotated[float, Field(ge=0, le=100, strict=True, allow_inf_nan=False)] | None = None
    sensor_status: Annotated[str, StringConstraints(max_length=64)] | None = None
    firmware_version: Annotated[str, StringConstraints(max_length=64)] | None = None
    source: Literal["real", "simulated", "fixture"] = "real"
    diagnostics: dict[str, str | float | bool | None] = Field(default_factory=dict, max_length=8)

    @field_validator("diagnostics")
    @classmethod
    def bounded_diagnostics(cls, value):
        if any(len(key) > 64 for key in value) or len(json.dumps(value, allow_nan=False).encode()) > 1024:
            raise ValueError("Diagnostics exceed the configured contract bounds")
        return value


class DevicePair(FrozenModel):
    device_id: Identifier
    session_id: Identifier


class PairResponse(DevicePair):
    paired: bool = True
    duplicate: bool


class HapticCommand(FrozenModel):
    command_id: str
    device_id: str
    session_id: str
    boot_id: str
    navigation_id: str | None
    state_revision: int
    kind: CommandKind
    priority: int
    created_at: int
    expires_at: int
    remaining_ttl_ms: int
    status: CommandStatus
    execution_reported: bool = False
    perception_verified: Literal[False] = False


class CommandPoll(FrozenModel):
    device_id: str
    server_ms: int
    command: HapticCommand | None = None


class CommandAck(FrozenModel):
    device_id: Identifier
    command_id: Identifier
    status: Literal["received", "executed", "rejected", "expired"]

    @field_validator("status", mode="before")
    @classmethod
    def legacy_ack_names(cls, value):
        return {"accepted": "received", "completed": "executed"}.get(value, value) if isinstance(value, str) else value


class AckResponse(FrozenModel):
    device_id: str
    command_id: str
    acknowledged: bool = True
    duplicate: bool
    status: CommandStatus
    execution_reported: bool
    perception_verified: Literal[False] = False


class DeviceStatus(FrozenModel):
    device_id: str
    session_id: str | None
    paired: bool
    availability: Literal["unknown", "connected", "stale"]
    last_authenticated_contact_ms: int | None = None
    last_telemetry_received_ms: int | None = None
    telemetry_age_ms: int | None = None
    telemetry_fresh: bool = False
    measurement_fresh: bool = False
    sensor_valid: bool = False
    measurement_reason: str | None = None
    current_distance_cm: float | None = None
    last_reported_distance_cm: float | None = None
    last_valid_distance_cm: float | None = None
    last_valid_distance_age_ms: int | None = None
    obstacle_state: ObstacleState = "unknown"
    source: Literal["real", "simulated", "fixture"] | None = None
    boot_id: str | None = None
    sequence: int | None = None
    uptime_ms: int | None = None
    battery_percent: float | None = None
    firmware_version: str | None = None
    recovery_clear_count: int = 0
    recovery_required: int
    expected_telemetry_hz: float
    measurement_timeout_ms: int
    heartbeat_timeout_ms: int
    navigation_state: str | None = None
    navigation_revision: int | None = None
    pending_commands: int = 0
    latest_command: HapticCommand | None = None
    last_acknowledged_command_id: str | None = None
    local_alerts_verified: Literal[False] = False


class TelemetryResponse(FrozenModel):
    device_id: str
    accepted: bool = True
    duplicate: bool
    received_ms: int
    obstacle_state: ObstacleState
    telemetry_fresh: bool
    sensor_valid: bool
    measurement_reason: str | None
    navigation_state: str | None
    navigation_revision: int | None
    physical_alert_verified: Literal[False] = False
