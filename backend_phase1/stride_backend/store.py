"""One pending frame per session; bounded identity history and no disk storage."""

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .errors import BackendError
from .models import DetectionBatch, ReceivedFrameMetadata
from .settings import Settings


def monotonic_ms() -> int:
    return monotonic_ns() // 1_000_000


@dataclass(frozen=True)
class Frame:
    jpeg: bytes = field(repr=False)
    metadata: ReceivedFrameMetadata
    received_monotonic_ms: int = field(repr=False)


@dataclass
class _Session:
    latest: ReceivedFrameMetadata
    received_monotonic_ms: int
    pending: Frame | None = None
    sequences: dict[tuple[str, str], int] = field(default_factory=dict)
    detections: DetectionBatch | None = None
    detections_monotonic_ms: int = 0
    in_flight: tuple[ReceivedFrameMetadata, int] | None = None


class LatestFrameStore:
    def __init__(self, settings: Settings, clock: Callable[[], int] = monotonic_ms):
        self._settings = settings
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = Lock()

    def _expire(self, now: int) -> None:
        for session_id, slot in list(self._sessions.items()):
            age = now - slot.received_monotonic_ms
            if age > self._settings.frame_freshness_ms:
                slot.pending = None
            if now - slot.detections_monotonic_ms > self._settings.frame_freshness_ms:
                slot.detections = None
            if age > self._settings.session_ttl_ms and slot.in_flight is None:
                del self._sessions[session_id]

    def put(self, frame: Frame) -> bool:
        """Atomically accept a frame; return whether a pending frame was replaced."""
        with self._lock:
            self._expire(self._clock())
            meta = frame.metadata
            slot = self._sessions.get(meta.session_id)
            key = (meta.device_id, meta.boot_id)
            if slot:
                previous = slot.sequences.get(key)
                if previous is not None and meta.sequence <= previous:
                    raise BackendError(409, "sequence_regression", "Sequence must increase within a session, device and boot")
                if meta.source_revision < slot.latest.source_revision:
                    raise BackendError(409, "source_revision_regression", "Source revision must not decrease")
                if previous is None and len(slot.sequences) >= self._settings.max_streams_per_session:
                    raise BackendError(429, "stream_capacity", "Session device/boot history is full; use a new session")
            else:
                if len(self._sessions) >= self._settings.max_sessions:
                    raise BackendError(429, "session_capacity", "Active session capacity reached")
                slot = _Session(meta, frame.received_monotonic_ms)
                self._sessions[meta.session_id] = slot
            replaced = slot.pending is not None
            if self._source_identity(slot.latest) != self._source_identity(meta):
                slot.detections = None
            slot.latest = meta
            slot.received_monotonic_ms = frame.received_monotonic_ms
            slot.sequences[key] = meta.sequence
            slot.pending = frame
            return replaced

    @staticmethod
    def _source_identity(meta: ReceivedFrameMetadata) -> tuple:
        return (meta.device_id, meta.boot_id, meta.source, meta.origin, meta.source_revision)

    def take_latest(self, session_id: str) -> Frame | None:
        """Claim one fresh frame. Call finish(frame) after inference, even on error."""
        with self._lock:
            self._expire(self._clock())
            slot = self._sessions.get(session_id)
            if slot is None or slot.in_flight is not None:
                return None
            frame, slot.pending = slot.pending, None
            if frame is not None:
                slot.in_flight = (frame.metadata, frame.received_monotonic_ms)
            return frame

    def finish(self, frame: Frame) -> None:
        """Release an inference claim without affecting a newer pending frame."""
        with self._lock:
            slot = self._sessions.get(frame.metadata.session_id)
            if slot and slot.in_flight and slot.in_flight[0] == frame.metadata:
                slot.in_flight = None

    def publish_detections(self, batch: DetectionBatch) -> bool:
        """Publish for the claimed receipt, if fresh and still on the same source."""
        with self._lock:
            now = self._clock()
            self._expire(now)
            slot = self._sessions.get(batch.frame.session_id)
            if slot is None or slot.in_flight is None or batch.frame != slot.in_flight[0]:
                return False
            if self._source_identity(batch.frame) != self._source_identity(slot.latest):
                return False
            if now - slot.in_flight[1] > self._settings.frame_freshness_ms:
                return False
            if slot.detections is not None and slot.detections.frame == batch.frame:
                return False
            slot.detections = batch
            slot.detections_monotonic_ms = slot.in_flight[1]
            return True

    def latest_detections(self, session_id: str) -> DetectionBatch | None:
        with self._lock:
            self._expire(self._clock())
            slot = self._sessions.get(session_id)
            return slot.detections if slot else None

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
