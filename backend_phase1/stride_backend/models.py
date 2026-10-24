"""Canonical transport and detector schemas, independent of a model runtime."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
NonNegativeInt = Annotated[int, Field(ge=0)]
UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


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


class DetectionBatch(FrozenModel):
    frame: ReceivedFrameMetadata
    completed_ms: NonNegativeInt
    provider: Literal["yolo"] = "yolo"
    objects: Annotated[tuple[Detection, ...], Field(max_length=300)]
