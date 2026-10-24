"""Navigation and last-seen contracts, independent of live detector schemas."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .models import FrozenModel, Identifier, NonNegativeInt

Direction = Literal["left", "right", "straight", "stop"]
NavigationState = Literal["idle", "guiding", "paused", "blocked", "completed"]
Instruction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Checkpoint(FrozenModel):
    checkpoint_id: Identifier
    ordinal: Annotated[int, Field(ge=0, lt=64)]
    instruction: Instruction
    direction: Direction
    landmark: str | None = Field(default=None, max_length=256)
    return_instruction: Instruction | None = None
    return_direction: Direction | None = None
    return_checked: bool = False

    @model_validator(mode="after")
    def separate_return(self):
        if (self.return_instruction is None) != (self.return_direction is None):
            raise ValueError("Return instruction and direction must be supplied together")
        if self.return_checked and self.return_instruction is None:
            raise ValueError("No return route has been supplied to check")
        return self


class SavedRoute(FrozenModel):
    route_id: Identifier
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    description: str = Field(default="", max_length=2000)
    checked: bool = False
    demo_fixture: bool = True
    verification_note: str | None = None
    created_at: NonNegativeInt
    updated_at: NonNegativeInt
    checkpoints: Annotated[tuple[Checkpoint, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def ordered_checkpoints(self):
        if [cp.ordinal for cp in self.checkpoints] != list(range(len(self.checkpoints))):
            raise ValueError("Checkpoint ordinals must be contiguous, starting at zero")
        if len({cp.checkpoint_id for cp in self.checkpoints}) != len(self.checkpoints):
            raise ValueError("Checkpoint IDs must be unique")
        return self


class RouteList(FrozenModel):
    routes: tuple[SavedRoute, ...]


class RouteAction(FrozenModel):
    session_id: Identifier
    route_id: Identifier | None = None
    navigation_id: Identifier | None = None
    action_id: Identifier
    action: Literal["start", "confirm", "repeat", "pause", "resume", "stop"]
    expected_revision: NonNegativeInt | None = None

    @model_validator(mode="after")
    def require_identity(self):
        if self.action == "start" and self.route_id is None:
            raise ValueError("Start requires route_id")
        if self.action != "start" and (self.navigation_id is None or self.expected_revision is None):
            raise ValueError("Navigation actions require navigation_id and expected_revision")
        return self


class CheckpointRef(FrozenModel):
    checkpoint_id: Identifier
    ordinal: NonNegativeInt
    landmark: str | None = None


class GuidanceEvent(FrozenModel):
    event_id: Identifier
    navigation_id: Identifier
    session_id: Identifier
    instruction: str
    direction: Direction
    created_at: NonNegativeInt
    expires_at: NonNegativeInt
    state_revision: NonNegativeInt
    checkpoint_id: Identifier
    valid: bool


class NavigationProgress(FrozenModel):
    session_id: Identifier
    navigation_id: Identifier
    route_id: Identifier
    state: NavigationState
    state_revision: NonNegativeInt
    current_checkpoint: CheckpointRef | None
    confirmed_checkpoint_count: NonNegativeInt
    total_checkpoints: NonNegativeInt
    confirmed_checkpoints: tuple[CheckpointRef, ...]
    instruction: str | None = None
    haptic_direction: Direction | None = None
    guidance_event_id: str | None = None
    guidance_event: GuidanceEvent | None = None
    status_message: str
    physical_position_known: Literal[False] = False
    progress_source: Literal["user_confirmation"] = "user_confirmation"
    sensor_monitoring: Literal["not_associated", "unknown", "fresh_measurement"] = "not_associated"
    paired_device_id: str | None = None
    obstacle_state: Literal["clear", "caution", "danger", "unknown"] | None = None
    created_at: NonNegativeInt
    updated_at: NonNegativeInt


class RouteResponse(NavigationProgress):
    action_id: Identifier
    duplicate: bool = False
    applied_revision: NonNegativeInt


class RouteEvent(FrozenModel):
    event_id: Identifier
    navigation_id: Identifier
    action: str
    prior_state: NavigationState
    resulting_state: NavigationState
    checkpoint_index: NonNegativeInt
    timestamp: NonNegativeInt


class Sighting(FrozenModel):
    sighting_id: Identifier
    session_id: Identifier
    label: str
    checkpoint_id: str | None
    checkpoint_association: Literal["last_user_confirmed"] | None
    frame_id: str
    device_id: str
    boot_id: str
    source_revision: NonNegativeInt
    vision_generation: NonNegativeInt
    vision_instance_id: Identifier
    source: Literal["real", "simulated", "fixture"]
    provider: Literal["yolo", "gemini", "fixture"]
    captured_at: int | None
    captured_ms: NonNegativeInt
    received_at: NonNegativeInt
    recorded_at: NonNegativeInt
    last_seen_at: NonNegativeInt
    age_ms: NonNegativeInt
    timestamp_basis: Literal["server_receipt", "aligned_capture"]
    track_id: str
    observation: Literal["last_seen"] = "last_seen"


class MemoryResponse(FrozenModel):
    session_id: Identifier
    routes: tuple[SavedRoute, ...]
    navigation: NavigationProgress | None
    previous_navigation: tuple[NavigationProgress, ...]
    route_events: tuple[RouteEvent, ...]
    sightings: tuple[Sighting, ...]
    returned_at: NonNegativeInt


class SightingWriteResult(FrozenModel):
    saved: NonNegativeInt = 0
    skipped: NonNegativeInt = 0
    error: str | None = None


class ObstacleObservation(FrozenModel):
    """Internal Phase 4 seam; no sensor endpoint is implemented in Phase 3."""
    fresh: bool
    valid: bool
    obstacle: bool | None
