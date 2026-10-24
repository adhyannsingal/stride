from contextlib import contextmanager
from threading import Condition, Event

from fastapi.testclient import TestClient

from stride_backend.main import create_app
from stride_backend.models import Detection, DetectionBatch, SpeechEvent
from stride_backend.settings import Settings


class Clock:
    def __init__(self):
        self.now = 1000

    def mono(self):
        return self.now

    def epoch(self):
        return 1700000000000 + self.now

    def advance(self, milliseconds):
        self.now += milliseconds


class ControlledDetector:
    """Deterministic test double. Thread events control completion, never sleeps."""
    def __init__(self, *, blocking=True, callback=None):
        self.blocking = blocking
        self.callback = callback or self.result
        self.calls = []
        self.gates = []
        self.changed = Condition()
        self.active = {}
        self.max_active = {}

    @staticmethod
    def result(frame):
        return DetectionBatch(
            frame=frame.metadata, completed_ms=frame.metadata.received_ms,
            objects=(Detection(label="chair", score=0.8, bbox=(0.1, 0.1, 0.3, 0.8), track_id="supplied-track"),),
            speech_event=SpeechEvent(event_id=f"supplied-event-{frame.metadata.frame_id}", text="Chair on the left"),
        )

    async def detect(self, frame):
        session = frame.metadata.session_id
        gate = Event()
        with self.changed:
            self.calls.append(frame)
            self.gates.append(gate)
            self.active[session] = self.active.get(session, 0) + 1
            self.max_active[session] = max(self.max_active.get(session, 0), self.active[session])
            blocking = self.blocking
            self.changed.notify_all()
        try:
            if blocking and not gate.wait(5):
                raise AssertionError("Test did not release detector gate")
            return self.callback(frame)
        finally:
            with self.changed:
                self.active[session] -= 1
                self.changed.notify_all()

    def wait_calls(self, count):
        with self.changed:
            assert self.changed.wait_for(lambda: len(self.calls) >= count, timeout=3), "Worker did not dispatch inference"

    def release(self, index=0):
        self.gates[index].set()

    def release_all(self):
        with self.changed:
            self.blocking = False
            for gate in self.gates:
                gate.set()


class Harness:
    def __init__(self, jpeg, *, detector, settings=None):
        self.jpeg = jpeg
        self.clock = Clock()
        self.settings = settings or Settings(
            _env_file=None, device_token="test-device-token", local_dev=True,
            session_tokens={"session-1": "ui-token-1", "session-2": "ui-token-2"},
        )
        self.app = create_app(self.settings, detector=detector, clock=self.clock.mono, epoch_clock=self.clock.epoch)
        self.store = self.app.state.frame_store
        self.detector = self.app.state.inference_worker.detector
        self.changed = Condition()
        for name in ("publish_detections", "fail", "finish"):
            original = getattr(self.store, name)

            def wrapped(*args, _original=original, **kwargs):
                result = _original(*args, **kwargs)
                with self.changed:
                    self.changed.notify_all()
                return result

            setattr(self.store, name, wrapped)

    @staticmethod
    def headers(session="session-1"):
        return {"X-Session-Token": "ui-token-1" if session == "session-1" else "ui-token-2"}

    def action(self, action, action_id=None, session="session-1", **extra):
        return self.client.post("/vision", headers=self.headers(session), json={
            "session_id": session, "action_id": action_id or action, "action": action, **extra,
        })

    def upload(self, sequence=1, session="session-1", **extra):
        data = {
            "session_id": session, "device_id": "camera-1", "boot_id": "boot-1",
            "frame_id": f"frame-{sequence}", "sequence": sequence, "captured_ms": 42,
            "source": "fixture", **extra,
        }
        return self.client.post("/frame", headers={"X-Device-Token": "test-device-token"},
                                data=data, files={"file": ("fixture.jpg", self.jpeg, "image/jpeg")})

    def latest(self, session="session-1"):
        response = self.client.get("/vision/latest", params={"session_id": session}, headers=self.headers(session))
        assert response.status_code == 200, response.text
        return response.json()

    def wait(self, predicate, session="session-1"):
        with self.changed:
            assert self.changed.wait_for(lambda: predicate(self.store.snapshot(session)), timeout=3), self.store.snapshot(session)
        return self.latest(session)


@contextmanager
def running(jpeg, *, detector=None, settings=None):
    harness = Harness(jpeg, detector=detector, settings=settings)
    with TestClient(harness.app) as client:
        harness.client = client
        try:
            yield harness
        finally:
            if isinstance(harness.detector, ControlledDetector):
                harness.detector.release_all()
