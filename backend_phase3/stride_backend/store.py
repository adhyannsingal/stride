"""Bounded frame slots, live generations, and atomic publication checks."""

from collections import deque
from dataclasses import dataclass, field, replace
from threading import Lock
from time import monotonic_ns, time_ns
from typing import Callable

from pydantic import ValidationError

from .errors import BackendError
from .models import (
    DetectionBatch, ReceivedFrameMetadata, VisionAction, VisionControlResponse,
    VisionLatest, VisionObject, VisionSpeechEvent,
)
from .settings import Settings

_UNSPECIFIED = object()


def monotonic_ms() -> int:
    return monotonic_ns() // 1_000_000


def epoch_ms() -> int:
    return time_ns() // 1_000_000


@dataclass(frozen=True)
class Frame:
    jpeg: bytes = field(repr=False)
    metadata: ReceivedFrameMetadata
    received_monotonic_ms: int = field(repr=False)
    generation: int = 0
    capture_age_on_receipt_ms: int | None = None

    def age_ms(self, now: int) -> int:
        return max(0, now - self.received_monotonic_ms) + (self.capture_age_on_receipt_ms or 0)


@dataclass(frozen=True)
class VerifiedClockAlignment:
    """Trusted integration input, never accepted from an upload or public API.

    offset_ms maps camera captured_ms to server epoch ms. The integration must
    verify clock offset/RTT and supply a conservative uncertainty and expiry.
    """
    device_id: str
    boot_id: str
    offset_ms: int
    uncertainty_ms: int
    valid_until_monotonic_ms: int


@dataclass
class _Rate:
    # Ten 100 ms buckets: bounded memory even at very high upload rates.
    buckets: deque = field(default_factory=lambda: deque(maxlen=10))

    def add(self, now: int) -> None:
        tick = now // 100
        if self.buckets and self.buckets[-1][0] == tick:
            self.buckets[-1] = (tick, self.buckets[-1][1] + 1)
        else:
            self.buckets.append((tick, 1))

    def hz(self, now: int) -> float:
        return float(sum(count for tick, count in self.buckets if now // 100 - 9 <= tick <= now // 100))


@dataclass
class _Claim:
    frame: Frame
    failed: bool = False
    published: bool = False


@dataclass
class _Observation:
    metadata: ReceivedFrameMetadata
    received_mono: int
    capture_age_on_receipt_ms: int | None
    completed_mono: int
    completed_ms: int
    speech_event: VisionSpeechEvent | None = None

    def age_ms(self, now: int) -> int:
        return max(0, now - self.received_mono) + (self.capture_age_on_receipt_ms or 0)


@dataclass
class _ActionRecord:
    request: VisionAction
    applied_seq: int
    error: tuple[int, str, str] | None = None


@dataclass
class _Session:
    latest: ReceivedFrameMetadata | None = None
    received_monotonic_ms: int = 0
    pending: Frame | None = None
    sequences: dict[tuple[str, str], int] = field(default_factory=dict)
    detections: DetectionBatch | None = None
    in_flight: _Claim | None = None
    controlled: bool = False
    state: str = "idle"
    state_seq: int = 0
    generation: int = 0
    status: str = "unavailable"
    generation_started_mono: int = 0
    actions: dict[str, _ActionRecord] = field(default_factory=dict)
    observation: _Observation | None = None
    alignment: VerifiedClockAlignment | None = None
    seen_speech_ids: set[str] = field(default_factory=set)
    last_error: str | None = None
    dropped: int = 0
    superseded: int = 0
    uploads: int = 0
    inference_runs: int = 0
    publications: int = 0
    upload_rate: _Rate = field(default_factory=_Rate)
    inference_rate: _Rate = field(default_factory=_Rate)
    result_rate: _Rate = field(default_factory=_Rate)


class LatestFrameStore:
    def __init__(self, settings: Settings, clock: Callable[[], int] = monotonic_ms,
                 *, epoch_clock: Callable[[], int] = epoch_ms, detector_configured: bool = False):
        self._settings = settings
        self._clock = clock
        self._epoch = epoch_clock
        self.detector_configured = detector_configured
        self.detector_error: str | None = None
        self._sessions: dict[str, _Session] = {}
        self._lock = Lock()
        self._cursor = 0
        self._closing = False

    def _expire(self, now: int) -> None:
        for session_id, slot in list(self._sessions.items()):
            if slot.pending and self._prepared(slot, slot.pending, now).age_ms(now) > self._settings.frame_freshness_ms:
                slot.pending = None
                slot.dropped += 1
            if slot.observation and slot.observation.age_ms(now) > self._settings.frame_freshness_ms:
                slot.detections = None
                slot.observation.speech_event = None
            # Controlled sessions retain bounded action history and stop tombstones.
            if not slot.controlled and now - slot.received_monotonic_ms > self._settings.session_ttl_ms and slot.in_flight is None:
                del self._sessions[session_id]

    def _slot(self, session_id: str) -> _Session:
        slot = self._sessions.get(session_id)
        if slot is None:
            if len(self._sessions) >= self._settings.max_sessions:
                raise BackendError(429, "session_capacity", "Session capacity reached")
            slot = _Session()
            self._sessions[session_id] = slot
        return slot

    @staticmethod
    def _source_identity(meta: ReceivedFrameMetadata) -> tuple:
        return (meta.device_id, meta.boot_id, meta.source, meta.origin, meta.source_revision)

    def _invalidate(self, slot: _Session) -> None:
        if slot.pending:
            slot.dropped += 1
        slot.pending = None
        slot.detections = None
        slot.observation = None
        slot.seen_speech_ids.clear()
        slot.last_error = None
        slot.result_rate = _Rate()
        slot.generation += 1
        slot.generation_started_mono = self._clock()
        slot.state_seq += 1
        # Keep a physical inference claim until finish(): threads cannot be killed.

    def ingestion_generation(self, session_id: str) -> int | None:
        """Ticket captured before asynchronous JPEG validation can yield to controls."""
        with self._lock:
            slot = self._sessions.get(session_id)
            return slot.generation if slot and slot.controlled else None

    def put(self, frame: Frame, *, expected_generation=_UNSPECIFIED) -> bool:
        """Preserve Phase 1 receipt semantics; inactive controlled uploads are dropped."""
        with self._lock:
            now = self._clock()
            self._expire(now)
            meta = frame.metadata
            slot = self._slot(meta.session_id)
            obsolete_upload = slot.controlled and (
                (expected_generation is not _UNSPECIFIED and expected_generation != slot.generation)
                or frame.received_monotonic_ms < slot.generation_started_mono
            )
            key = (meta.device_id, meta.boot_id)
            previous = slot.sequences.get(key)
            if previous is not None and meta.sequence <= previous:
                raise BackendError(409, "sequence_regression", "Sequence must increase within a session, device and boot")
            if slot.latest and meta.source_revision < slot.latest.source_revision:
                raise BackendError(409, "source_revision_regression", "Source revision must not decrease")
            if previous is None and len(slot.sequences) >= self._settings.max_streams_per_session:
                raise BackendError(429, "stream_capacity", "Session device/boot history is full; use a new session")
            if obsolete_upload:
                # A request validated across a control boundary cannot select a
                # new source, evict a current pending frame, or revive output.
                slot.sequences[key] = meta.sequence
                slot.uploads += 1
                slot.upload_rate.add(now)
                slot.dropped += 1
                return False
            changed = slot.latest is not None and self._source_identity(slot.latest) != self._source_identity(meta)
            if changed and slot.controlled and meta.source_revision <= slot.latest.source_revision:
                raise BackendError(409, "source_revision_required", "Increment source_revision when switching camera, boot, origin or source")
            replaced = slot.pending is not None
            if changed:
                self._invalidate(slot)
                slot.alignment = None
            if replaced:
                slot.superseded += 1
                if not changed:
                    slot.dropped += 1
            slot.latest = meta
            slot.received_monotonic_ms = frame.received_monotonic_ms
            slot.sequences[key] = meta.sequence
            slot.uploads += 1
            slot.upload_rate.add(now)
            if self._closing or (slot.controlled and slot.state != "active"):
                slot.pending = None
                slot.dropped += 1
            elif slot.controlled and not self._settings.local_dev and meta.source != "real":
                slot.dropped += 1
                slot.last_error = "non_live_source"
                slot.pending = None
            else:
                slot.pending = frame
            return replaced

    def _prepared(self, slot: _Session, frame: Frame, now: int) -> Frame:
        capture_age = None
        alignment = slot.alignment
        meta = frame.metadata
        if alignment and alignment.valid_until_monotonic_ms >= now and (alignment.device_id, alignment.boot_id) == (meta.device_id, meta.boot_id):
            difference = meta.received_ms - (meta.captured_ms + alignment.offset_ms)
            # An aligned capture implausibly in the future is ineligible.
            capture_age = (self._settings.frame_freshness_ms + 1 if difference < -alignment.uncertainty_ms
                           else max(0, difference + alignment.uncertainty_ms))
        return replace(frame, generation=slot.generation, capture_age_on_receipt_ms=capture_age)

    def _take(self, slot: _Session, now: int) -> Frame | None:
        if self._closing or slot.in_flight or slot.pending is None or (slot.controlled and slot.state != "active"):
            return None
        frame = self._prepared(slot, slot.pending, now)
        slot.pending = None
        if frame.age_ms(now) > self._settings.frame_freshness_ms:
            slot.dropped += 1
            return None
        slot.in_flight = _Claim(frame)
        return frame

    def take_latest(self, session_id: str) -> Frame | None:
        with self._lock:
            now = self._clock()
            self._expire(now)
            slot = self._sessions.get(session_id)
            return self._take(slot, now) if slot else None

    def take_next_active(self) -> Frame | None:
        """Fair bounded dispatch, sharing the same slots as Phase 1."""
        with self._lock:
            now = self._clock()
            self._expire(now)
            slots = list(self._sessions.values())
            for offset in range(len(slots)):
                index = (self._cursor + offset) % len(slots)
                slot = slots[index]
                if slot.controlled and slot.state == "active":
                    frame = self._take(slot, now)
                    if frame:
                        self._cursor = (index + 1) % len(slots)
                        return frame
            return None

    def _matching(self, frame: Frame) -> _Session | None:
        slot = self._sessions.get(frame.metadata.session_id)
        if slot and slot.in_flight and slot.in_flight.frame.metadata == frame.metadata and slot.in_flight.frame.generation == frame.generation:
            return slot
        return None

    def finish(self, frame: Frame) -> None:
        with self._lock:
            slot = self._matching(frame)
            if slot:
                slot.in_flight = None

    def inference_completed(self, frame: Frame) -> None:
        with self._lock:
            slot = self._matching(frame)
            if slot:
                slot.inference_runs += 1
                slot.inference_rate.add(self._clock())

    def fail(self, frame: Frame, category: str) -> None:
        with self._lock:
            slot = self._matching(frame)
            if slot:
                if not slot.in_flight.failed and not slot.in_flight.published:
                    slot.dropped += 1
                slot.in_flight.failed = True
                if slot.generation == frame.generation and slot.state == "active":
                    slot.last_error = category
                    slot.detections = None
                    slot.observation = None
                    slot.state_seq += 1

    def publication_error(self, frame: Frame) -> str | None:
        with self._lock:
            slot = self._matching(frame)
            if self._closing or slot is None or slot.in_flight.failed:
                return "superseded_result"
            if slot.generation != frame.generation or (slot.controlled and slot.state != "active"):
                return "superseded_result"
            if frame.age_ms(self._clock()) > self._settings.frame_freshness_ms:
                return "stale_result"
            return None

    def publish_detections(self, batch: DetectionBatch) -> bool:
        # Revalidate even models made with model_construct/model_copy.
        try:
            batch = DetectionBatch.model_validate(batch.model_dump(warnings=False))
        except (ValidationError, AttributeError, TypeError, ValueError):
            return False
        with self._lock:
            now = self._clock()
            self._expire(now)
            slot = self._sessions.get(batch.frame.session_id)
            if self._closing or slot is None or slot.in_flight is None:
                return False
            claim = slot.in_flight
            frame = claim.frame
            if claim.failed or claim.published or batch.frame != frame.metadata or slot.latest is None:
                return False
            if slot.generation != frame.generation or self._source_identity(batch.frame) != self._source_identity(slot.latest):
                return False
            if slot.controlled and (slot.state != "active" or not self.detector_configured):
                return False
            if frame.age_ms(now) > self._settings.frame_freshness_ms:
                return False
            if slot.controlled and not self._settings.local_dev and batch.frame.source != "real":
                return False
            if slot.controlled:
                batch = batch.model_copy(update={"completed_ms": self._epoch()})
            event = None
            if batch.speech_event and batch.speech_event.event_id not in slot.seen_speech_ids and len(slot.seen_speech_ids) < self._settings.max_speech_events_per_generation:
                slot.seen_speech_ids.add(batch.speech_event.event_id)
                event = VisionSpeechEvent(**batch.speech_event.model_dump(), generation=slot.generation, source_revision=batch.frame.source_revision)
            slot.observation = _Observation(batch.frame, frame.received_monotonic_ms, frame.capture_age_on_receipt_ms, now, batch.completed_ms, event)
            slot.detections = batch
            slot.last_error = None
            claim.published = True
            slot.publications += 1
            slot.result_rate.add(now)
            slot.state_seq += 1
            return True

    def latest_detections(self, session_id: str) -> DetectionBatch | None:
        with self._lock:
            self._expire(self._clock())
            slot = self._sessions.get(session_id)
            return slot.detections if slot else None

    def _status(self, slot: _Session, now: int) -> str:
        if slot.state == "paused":
            status = "paused"
        elif slot.state != "active" or not self.detector_configured or self._closing:
            status = "unavailable"
        elif slot.detections and slot.observation and slot.observation.age_ms(now) <= self._settings.frame_freshness_ms:
            status = "live"
        elif slot.observation:
            status = "stale"
        else:
            status = "unavailable"
        if status != slot.status:
            slot.status = status
            slot.state_seq += 1
        return status

    def control(self, request: VisionAction) -> VisionControlResponse:
        with self._lock:
            self._expire(self._clock())
            slot = self._slot(request.session_id)
            record = slot.actions.get(request.action_id)
            duplicate = record is not None
            if record:
                if request != record.request:
                    raise BackendError(409, "action_id_conflict", "Action ID was already used for a different request")
                if record.error:
                    raise BackendError(*record.error)
            else:
                # Never evict replay history; reserve one extra terminal stop record.
                if len(slot.actions) >= self._settings.max_actions_per_session and not (request.action == "stop" and slot.state != "stopped"):
                    raise BackendError(429, "action_capacity", "Session action history is full; stop and use a new session")
                allowed = {"idle": {"start", "stop"}, "active": {"pause", "stop"}, "paused": {"resume", "stop"}, "stopped": set()}
                error = None
                if request.expected_generation is not None and request.expected_generation != slot.generation:
                    error = (409, "generation_conflict", "Session generation has changed")
                elif request.action not in allowed[slot.state]:
                    error = (409, "invalid_transition", "Action is not valid in the current session state")
                record = _ActionRecord(request, slot.state_seq, error)
                slot.actions[request.action_id] = record
                slot.controlled = True
                if error:
                    raise BackendError(*error)
                self._invalidate(slot)
                slot.state = {"start": "active", "pause": "paused", "resume": "active", "stop": "stopped"}[request.action]
                record.applied_seq = slot.state_seq
            status = self._status(slot, self._clock())
            return VisionControlResponse(
                session_id=request.session_id, action_id=request.action_id, action=request.action,
                state=slot.state, state_seq=slot.state_seq, generation=slot.generation,
                source_revision=slot.latest.source_revision if slot.latest else 0,
                status=status, duplicate=duplicate, applied_state_seq=record.applied_seq,
            )

    def snapshot(self, session_id: str) -> VisionLatest:
        with self._lock:
            now = self._clock()
            self._expire(now)
            slot = self._sessions.get(session_id) or _Session()
            status = self._status(slot, now)
            observation = slot.observation
            meta = observation.metadata if observation else None
            provenance = slot.latest
            objects = ()
            if status == "live":
                items = []
                for obj in slot.detections.objects:
                    midpoint = (obj.bbox[0] + obj.bbox[2]) / 2
                    position = "left" if midpoint < 1 / 3 else "right" if midpoint > 2 / 3 else "center"
                    items.append(VisionObject(**obj.model_dump(), position=position))
                objects = tuple(items)
            return VisionLatest(
                session_id=session_id, state_seq=slot.state_seq, generation=slot.generation,
                state=slot.state, status=status, detector_configured=self.detector_configured,
                frame_id=meta.frame_id if meta else None, device_id=meta.device_id if meta else None,
                boot_id=meta.boot_id if meta else None, sequence=meta.sequence if meta else None,
                captured_ms=meta.captured_ms if meta else None, received_ms=meta.received_ms if meta else None,
                completed_ms=observation.completed_ms if observation else None, delivered_ms=self._epoch(),
                age_ms=observation.age_ms(now) if observation else None,
                receipt_to_result_ms=max(0, observation.completed_mono - observation.received_mono) if observation else None,
                freshness_basis="aligned_capture" if observation and observation.capture_age_on_receipt_ms is not None else "server_receipt",
                camera_clock_aligned=bool(observation and observation.capture_age_on_receipt_ms is not None),
                source_revision=provenance.source_revision if provenance else 0,
                source=provenance.source if provenance else None, origin=provenance.origin if provenance else None,
                result_hz=slot.result_rate.hz(now) if status == "live" else 0,
                upload_hz=slot.upload_rate.hz(now), inference_hz=slot.inference_rate.hz(now),
                objects=objects, speech_event=observation.speech_event if observation and status == "live" else None,
                dropped_frames=slot.dropped, superseded_frames=slot.superseded,
                uploaded_frames=slot.uploads, inference_runs=slot.inference_runs, published_results=slot.publications,
                pending_frames=int(slot.pending is not None), in_flight=slot.in_flight is not None,
                last_inference_error=slot.last_error or self.detector_error,
            )

    def register_clock_alignment(self, session_id: str, alignment: VerifiedClockAlignment) -> None:
        with self._lock:
            now = self._clock()
            if type(alignment.offset_ms) is not int or type(alignment.uncertainty_ms) is not int or not 0 <= alignment.uncertainty_ms < self._settings.frame_freshness_ms:
                raise ValueError("Invalid verified clock offset/uncertainty")
            if not now < alignment.valid_until_monotonic_ms <= now + 60000:
                raise ValueError("Verified alignment must expire within 60 seconds")
            slot = self._sessions.get(session_id)
            if slot is None:
                raise BackendError(404, "session_not_found", "Session has not been started")
            slot.alignment = alignment

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
            for slot in self._sessions.values():
                self._invalidate(slot)

    def startup(self) -> None:
        with self._lock:
            self._closing = False

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
