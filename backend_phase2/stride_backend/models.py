"""Canonical transport and detector schemas, independent of a model runtime."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
NonNegativeInt = Annotated[int, Field(ge=0)]
UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FrameMetadata(FrozenModel):
    session_id: Identifier
    device_id: Identifier
    boot_id: Identifier
    frame_id: Identifier
    sequence: NonNegativeInt
    captured_ms: NonNegativeInt
    source: Literal["real", "simulated", "fixture"]
    origin: Identifier = "unspecified"
    source_revision: NonNegativeInt = 0


class ReceivedFrameMetadata(FrameMetadata):
    receipt_id: str
    received_ms: NonNegativeInt
    freshness_basis: Literal["server_receipt"] = "server_receipt"
    camera_clock_aligned: Literal[False] = False
    size_bytes: NonNegativeInt
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class FrameReceipt(ReceivedFrameMetadata):
    status: Literal["accepted"] = "accepted"
    replaced_pending: bool


class HealthResponse(FrozenModel):
    status: Literal["ok"] = "ok"


class TimeResponse(FrozenModel):
    server_ms: NonNegativeInt


class ErrorDetail(FrozenModel):
    code: str
    message: str
    fields: tuple[str, ...] = ()


class ErrorResponse(FrozenModel):
    error: ErrorDetail


class Detection(FrozenModel):
    label: Identifier
    score: UnitFloat
    # Normalized image-relative xyxy, after accounting for image orientation.
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    track_id: Identifier | None = None

    @model_validator(mode="after")
    def ordered_box(self) -> "Detection":
        x1, y1, x2, y2 = self.bbox
        if x1 >= x2 or y1 >= y2:
            raise ValueError("bbox must use normalized (xmin, ymin, xmax, ymax)")
        return self


class SpeechEvent(FrozenModel):
    event_id: Identifier
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class DetectionBatch(FrozenModel):
    frame: ReceivedFrameMetadata
    completed_ms: NonNegativeInt
    provider: Literal["yolo"] = "yolo"
    objects: Annotated[tuple[Detection, ...], Field(max_length=300)]
    speech_event: SpeechEvent | None = None


VisionActionName = Literal["start", "pause", "resume", "stop"]
VisionState = Literal["idle", "active", "paused", "stopped"]
VisionStatus = Literal["live", "stale", "paused", "unavailable"]


class VisionAction(FrozenModel):
    session_id: Identifier
    action_id: Identifier
    action: VisionActionName
    expected_generation: NonNegativeInt | None = None


class VisionControlResponse(FrozenModel):
    session_id: Identifier
    action_id: Identifier
    action: VisionActionName
    state: VisionState
    state_seq: NonNegativeInt
    generation: NonNegativeInt
    source_revision: NonNegativeInt
    status: VisionStatus
    duplicate: bool
    applied_state_seq: NonNegativeInt


class VisionObject(Detection):
    position: Literal["left", "center", "right"]


class VisionSpeechEvent(SpeechEvent):
    generation: NonNegativeInt
    source_revision: NonNegativeInt


class VisionLatest(FrozenModel):
    session_id: Identifier
    state_seq: NonNegativeInt
    generation: NonNegativeInt
    state: VisionState
    status: VisionStatus
    detector_configured: bool
    frame_id: str | None = None
    device_id: str | None = None
    boot_id: str | None = None
    sequence: int | None = None
    captured_ms: int | None = None
    received_ms: int | None = None
    completed_ms: int | None = None
    delivered_ms: int
    age_ms: int | None = None
    receipt_to_result_ms: int | None = None
    freshness_basis: Literal["server_receipt", "aligned_capture"] = "server_receipt"
    camera_clock_aligned: bool = False
    source_revision: NonNegativeInt = 0
    source: Literal["real", "simulated", "fixture"] | None = None
    origin: str | None = None
    result_hz: float = 0
    upload_hz: float = 0
    inference_hz: float = 0
    objects: tuple[VisionObject, ...] = ()
    speech_event: VisionSpeechEvent | None = None
    dropped_frames: NonNegativeInt = 0
    superseded_frames: NonNegativeInt = 0
    uploaded_frames: NonNegativeInt = 0
    inference_runs: NonNegativeInt = 0
    published_results: NonNegativeInt = 0
    pending_frames: Annotated[int, Field(ge=0, le=1)] = 0
    in_flight: bool = False
    last_inference_error: str | None = None


class StatusResponse(FrozenModel):
    backend: HealthResponse = HealthResponse()
    vision: VisionLatest


class SessionCredentials(FrozenModel):
    session_id: Identifier
    session_token: SecretStr = Field(repr=False)


class SessionAuthResponse(FrozenModel):
    session_id: Identifier
    expires_ms: NonNegativeInt
