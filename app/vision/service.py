"""Bounded continuous inference. Canonical auth/ingest/events belong to Agent 1."""
import asyncio
import copy
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from .model import OnnxDetector
from .tracking import Tracker


def epoch_ms():
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Frame:
    session_id: str
    device_id: str
    boot_id: str
    sequence: int
    frame_id: str
    captured_ms: int
    source_revision: int
    source: str
    origin: str
    jpeg: bytes
    clock_synced: bool = True
    width: int = 640
    height: int = 480
    received_ms: int | None = None


@dataclass
class State:
    revision: int
    source: str
    origin: str
    active: bool = False
    generation: int = 0
    pending: Frame | None = None
    worker: asyncio.Task | None = None
    tracker: Tracker = field(default_factory=Tracker)
    latest: dict | None = None
    completed: deque = field(default_factory=lambda: deque(maxlen=300))
    received: int = 0
    dropped: int = 0
    inferred: int = 0
    error: str | None = None
    offered_candidate: dict | None = None
    callback_worker: asyncio.Task | None = None
    callback_drops: int = 0


class VisionService:
    def __init__(self, settings=None, *, detector=None, clock=epoch_ms,
                 on_observation: Callable[[dict], Awaitable[None]] | None = None,
                 max_sessions=8):
        self.settings, self.detector = settings, detector
        self.clock, self.on_observation, self.max_sessions = clock, on_observation, max_sessions
        self.sessions, self.workers = {}, set()
        self.closed = False
        self.model_lock = asyncio.Lock()
        self.load_lock = asyncio.Lock()

    async def start(self):
        """Load one model off the event loop; missing settings/model fail clearly."""
        async with self.load_lock:
            if self.closed:
                raise RuntimeError('Vision service is closed')
            if self.detector is None:
                if self.settings is None:
                    raise ValueError('LIVE_DETECTOR_MODEL_PATH setting required')
                self.detector = await asyncio.to_thread(OnnxDetector, self.settings.LIVE_DETECTOR_MODEL_PATH,
                                                        expected_sha256=getattr(self.settings,"LIVE_DETECTOR_MODEL_SHA256",None))

    def bind(self, session_id, revision, source, origin):
        """Backend calls after canonical session binding/source selection."""
        if self.closed:
            raise RuntimeError('Vision service is closed')
        allowed = {'real': {'browser_camera','w11_camera'}, 'simulated': {'simulator'}, 'fixture': {'fixture'}}
        if origin not in allowed.get(source, set()):
            raise ValueError('Invalid adapter provenance')
        old = self.sessions.get(session_id)
        if old and revision <= old.revision:
            raise ValueError('Source revision must increase')
        if not old and len(self.sessions) >= self.max_sessions:
            raise ValueError('Vision session capacity exceeded')
        if old:
            self._clear(old)
        self.sessions[session_id] = State(revision, source, origin)

    def _clear(self, state):
        state.active = False
        state.generation += 1
        state.pending = state.latest = state.offered_candidate = None
        state.tracker = Tracker()
        state.completed.clear()
        state.error = None
        if state.callback_worker:
            state.callback_worker.cancel()
            state.callback_worker = None

    def invalidate(self, session_id, source_revision):
        s = self.sessions[session_id]
        if source_revision < s.revision:
            raise ValueError('Retired source revision')
        self._clear(s)
        s.revision = source_revision

    def control(self, session_id, action, source_revision):
        """Sync. API boundary owns action-ID idempotency BEFORE calling this."""
        s = self.sessions[session_id]
        if action not in {'start','pause','resume','stop'}:
            raise ValueError('Invalid vision action')
        if source_revision != s.revision:
            raise ValueError('Retired or unbound source revision')
        self._clear(s)
        s.active = action in {'start','resume'}
        return self.snapshot(session_id)

    def offer_frame(self, f: Frame):
        """Sync, nonblocking; canonical /frame validates JPEG, boot/seq/auth first."""
        s = self.sessions[f.session_id]
        now = self.clock()
        if self.closed or self.detector is None:
            raise RuntimeError('Vision model not started')
        if not s.active or (f.source_revision,f.source,f.origin) != (s.revision,s.source,s.origin):
            raise ValueError('Inactive or replaced camera source')
        if not f.clock_synced or not 0 <= now-f.captured_ms < 1000:
            raise ValueError('Unsynchronized, future or expired frame')
        if not f.jpeg or len(f.jpeg)>1_000_000:
            raise ValueError('Invalid frame size')
        s.received += 1
        if s.pending is not None:
            s.dropped += 1
        s.pending = f
        if s.worker is None or s.worker.done():
            s.worker = self._task(self._work(f.session_id,s))

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.workers.add(task)
        task.add_done_callback(self.workers.discard)
        return task

    async def _work(self, session_id, s):
        while s.active and s.pending is not None:
            async with self.model_lock:
                if not s.active or s.pending is None or self.sessions.get(session_id) is not s:
                    return
                f, s.pending = s.pending, None
                generation = s.generation
                if self.clock()-f.captured_ms >= 1000:
                    s.dropped += 1
                    continue
                try:
                    detections = await asyncio.to_thread(self.detector,f.jpeg)
                except Exception:
                    if self._current(session_id,s,generation):
                        s.tracker = Tracker()
                        s.error, s.latest = 'detector_failed', None
                    continue
                now = self.clock()
                s.inferred += 1
                if not self._current(session_id,s,generation) or not 0 <= now-f.captured_ms < 1000:
                    s.dropped += 1
                    continue
                objects, candidate = s.tracker.update(detections,now)
                if candidate:
                    candidate['expires_ms'] = f.captured_ms+1000
                s.completed.append(now)
                s.error = None
                s.latest = {'session_id':session_id,'frame_id':f.frame_id,'device_id':f.device_id,
                            'boot_id':f.boot_id,'sequence':f.sequence,'captured_ms':f.captured_ms,
                            'completed_ms':now,'received_ms':f.received_ms,
                            'source_revision':s.revision,'source':s.source,'origin':s.origin,
                            'objects':objects,'candidate_event':candidate,'vision_generation':generation}
                if self.on_observation:
                    if s.offered_candidate is not None:
                        s.callback_drops += 1
                    s.offered_candidate = copy.deepcopy(s.latest)
                    if s.callback_worker is None or s.callback_worker.done():
                        s.callback_worker = self._task(self._publish(session_id,s,generation))

    def _current(self, session_id,s,generation):
        return s.active and generation==s.generation and self.sessions.get(session_id) is s

    async def _publish(self, session_id,s,generation):
        while s.offered_candidate is not None and self._current(session_id,s,generation):
            result, s.offered_candidate = s.offered_candidate,None
            if self.clock()-result['captured_ms'] >= 1000:
                s.callback_drops += 1
                continue
            try:
                # Slow persistence never blocks inference or creates a backlog.
                await asyncio.wait_for(self.on_observation(result), timeout=.25)
            except Exception:
                s.callback_drops += 1

    def is_current(self, observation, now_ms=None):
        """Backend MUST recheck immediately before committing candidate events."""
        s = self.sessions.get(observation['session_id'])
        now = self.clock() if now_ms is None else now_ms
        return bool(s and self._current(observation['session_id'],s,observation['vision_generation'])
                    and observation['source_revision']==s.revision
                    and 0 <= now-observation['captured_ms'] < 1000)

    def snapshot(self, session_id, now_ms=None):
        s = self.sessions[session_id]
        now = self.clock() if now_ms is None else now_ms
        age = now-s.latest['captured_ms'] if s.latest else None
        status = 'paused' if not s.active else 'live' if age is not None and 0<=age<1000 else 'stale' if s.latest else 'unavailable'
        recent = [t for t in s.completed if 0<=now-t<5000]
        hz = (len(recent)-1)*1000/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else 0
        result = copy.deepcopy(s.latest or {'frame_id':None,'captured_ms':None,'completed_ms':None})
        result.pop('candidate_event',None)
        result.update(session_id=session_id,server_time_ms=now,source_revision=s.revision,
                      source=s.source,origin=s.origin,provider='yolo',status=status,
                      age_ms=age,result_hz=round(hz,2),received_frames=s.received,
                      inferred_frames=s.inferred,dropped_frames=s.dropped,
                      callback_drops=s.callback_drops,error=s.error,speech_event=None)
        # Shared state_seq and final speech_event are supplied only by backend arbiter.
        if status!='live':
            result['objects']=[]
        return result

    async def close(self):
        self.closed = True
        for s in self.sessions.values():
            self._clear(s)
        if self.workers:
            _, pending = await asyncio.wait(self.workers, timeout=2)
            for task in pending:
                task.cancel()
            await asyncio.gather(*self.workers,return_exceptions=True)
        self.sessions.clear()
