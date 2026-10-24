"""Session-scoped progress recall and explicit, bounded tracked sightings."""

import sqlite3
from uuid import uuid4

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .database import Database
from .errors import BackendError
from .models import DetectionBatch
from .navigation import current_navigation, progress
from .route_models import MemoryResponse, RouteEvent, Sighting, SightingWriteResult
from .route_store import list_routes
from .settings import Settings
from .store import LatestFrameStore, epoch_ms


class MemoryService:
    def __init__(self, database: Database, frames: LatestFrameStore, settings: Settings, clock=epoch_ms):
        self.database = database
        self.frames = frames
        self.settings = settings
        self.clock = clock
        self.vision_instance_id = str(uuid4())
        self.devices = None

    def read(self, session_id: str, *, include_events=False, limit=25) -> MemoryResponse:
        if not 1 <= limit <= 100:
            raise BackendError(422, "invalid_limit", "Memory limit must be between 1 and 100")
        now = self.clock()
        with self.database.transaction(write=bool(self.devices and self.devices.enabled)) as connection:
            if self.devices and self.devices.enabled:
                self.devices.after_navigation(connection, session_id)
            current = current_navigation(connection, session_id)
            rows = connection.execute(
                "SELECT * FROM navigation_sessions WHERE session_id=? AND navigation_id!=? ORDER BY created_at DESC,rowid DESC LIMIT ?",
                (session_id, current["navigation_id"] if current else "", limit),
            ).fetchall()
            events = ()
            if include_events:
                event_rows = connection.execute(
                    "SELECT e.event_id,e.navigation_id,e.action,e.prior_state,e.resulting_state,e.checkpoint_index,e.timestamp FROM route_events e JOIN navigation_sessions n ON e.navigation_id=n.navigation_id WHERE n.session_id=? ORDER BY e.seq DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
                events = tuple(RouteEvent(**dict(row)) for row in reversed(event_rows))
            sightings = []
            sighting_rows = connection.execute(
                "SELECT * FROM object_sightings WHERE session_id=? ORDER BY last_seen_at DESC,rowid DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            for row in sighting_rows:
                values = dict(row)
                values.pop("receipt_id")
                values["age_ms"] = max(0, now - values["last_seen_at"])
                values["checkpoint_association"] = "last_user_confirmed" if values["checkpoint_id"] else None
                sightings.append(Sighting(**values))
            return MemoryResponse(
                session_id=session_id, routes=list_routes(connection, limit).routes,
                navigation=progress(connection, current, now, devices=self.devices) if current else None,
                previous_navigation=tuple(progress(connection, row, now, devices=self.devices) for row in rows),
                route_events=events, sightings=tuple(sightings), returned_at=now,
            )

    def _validated_current(self, session_id, batch):
        if batch.frame.session_id != session_id:
            raise BackendError(409, "sighting_identity_mismatch", "Sighting session does not match its frame")
        current = self.frames.latest_detections(session_id)
        if current is None or current.frame != batch.frame or current.objects != batch.objects or current.provider != batch.provider:
            raise BackendError(409, "sighting_not_current", "Sighting must reference the current validated fresh detection batch")
        state = self.frames.snapshot(session_id)
        if state.status != "live":
            raise BackendError(409, "sighting_not_current", "Live detection is not currently available")
        return state.generation

    async def record_sightings(self, *, session_id: str, batch: DetectionBatch,
                              track_ids: tuple[str, ...]) -> SightingWriteResult:
        """Opt-in confirmed-track event hook; not called on every detector frame.

        Call only after Phase 2 has published this batch. The integration chooses
        tracks it has actually stabilized. No changes to Detector are needed.
        Database errors return memory_unavailable instead of escaping to inference.
        """
        try:
            batch = DetectionBatch.model_validate(batch.model_dump(warnings=False))
        except (ValidationError, AttributeError, TypeError, ValueError):
            raise BackendError(422, "invalid_sighting", "Invalid detection batch") from None
        if not isinstance(track_ids, (tuple, list)) or not 1 <= len(track_ids) <= 16:
            raise BackendError(422, "invalid_sighting", "Select 1 to 16 distinct confirmed track IDs")
        for track in track_ids:
            if not isinstance(track, str) or not track.strip() or len(track) > 128:
                raise BackendError(422, "invalid_sighting", "Invalid confirmed track ID")
            if sum(obj.track_id == track for obj in batch.objects) != 1:
                raise BackendError(422, "invalid_sighting", "Selected track must identify exactly one detection")
        if len(set(track_ids)) != len(track_ids):
            raise BackendError(422, "invalid_sighting", "Select distinct confirmed track IDs")
        self._validated_current(session_id, batch)
        try:
            return await run_in_threadpool(self._record, session_id, batch, track_ids)
        except sqlite3.Error:
            return SightingWriteResult(error="memory_unavailable", skipped=len(track_ids))

    def _record(self, session_id, batch, track_ids):
        with self.database.transaction(write=True) as connection:
            generation = self._validated_current(session_id, batch)
            meta = batch.frame
            # Associate with progress explicitly confirmed by the observation's
            # server receipt time, not a checkpoint confirmed during later recall.
            checkpoint = connection.execute(
                "SELECT c.checkpoint_id FROM route_events e JOIN navigation_sessions n ON n.navigation_id=e.navigation_id JOIN checkpoints c ON c.route_id=n.route_id AND c.ordinal=e.checkpoint_index WHERE e.navigation_id=(SELECT navigation_id FROM navigation_sessions WHERE session_id=? AND created_at<=? ORDER BY created_at DESC,rowid DESC LIMIT 1) AND e.action='confirm' AND e.timestamp<=? ORDER BY e.seq DESC LIMIT 1",
                (session_id, meta.received_ms, meta.received_ms),
            ).fetchone()
            checkpoint_id = checkpoint["checkpoint_id"] if checkpoint else None
            saved = 0
            for obj in batch.objects:
                if obj.track_id not in track_ids:
                    continue
                key = (session_id, meta.device_id, meta.boot_id, meta.source_revision, generation, self.vision_instance_id,
                       obj.track_id, obj.label, meta.source, batch.provider)
                previous = connection.execute(
                    "SELECT sighting_id,last_seen_at,receipt_id FROM object_sightings WHERE session_id=? AND device_id=? AND boot_id=? AND source_revision=? AND vision_generation=? AND vision_instance_id=? AND track_id=? AND label=? AND source=? AND provider=?",
                    key,
                ).fetchone()
                observed_at = meta.received_ms
                if previous and (previous["receipt_id"] == meta.receipt_id or observed_at <= previous["last_seen_at"]
                                 or observed_at - previous["last_seen_at"] < self.settings.sighting_cooldown_ms):
                    continue
                sighting_id = previous["sighting_id"] if previous else str(uuid4())
                # captured_ms may be uptime. Do not manufacture an epoch capture
                # time: retain it verbatim and label receipt-based age explicitly.
                connection.execute(
                    "INSERT INTO object_sightings(sighting_id,session_id,label,checkpoint_id,frame_id,receipt_id,device_id,boot_id,source_revision,vision_generation,vision_instance_id,source,provider,captured_at,captured_ms,received_at,recorded_at,last_seen_at,timestamp_basis,track_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?) ON CONFLICT(sighting_id) DO UPDATE SET checkpoint_id=excluded.checkpoint_id,frame_id=excluded.frame_id,receipt_id=excluded.receipt_id,captured_ms=excluded.captured_ms,received_at=excluded.received_at,recorded_at=excluded.recorded_at,last_seen_at=excluded.last_seen_at",
                    (sighting_id, session_id, obj.label, checkpoint_id, meta.frame_id, meta.receipt_id,
                     meta.device_id, meta.boot_id, meta.source_revision, generation, self.vision_instance_id, meta.source, batch.provider,
                     meta.captured_ms, meta.received_ms, self.clock(), observed_at, "server_receipt", obj.track_id),
                )
                saved += 1
            connection.execute(
                "DELETE FROM object_sightings WHERE session_id=? AND sighting_id NOT IN (SELECT sighting_id FROM object_sightings WHERE session_id=? ORDER BY last_seen_at DESC,rowid DESC LIMIT ?)",
                (session_id, session_id, self.settings.max_sightings_per_session),
            )
            return SightingWriteResult(saved=saved, skipped=len(track_ids) - saved)
