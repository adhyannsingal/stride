"""YOLO plugin for the existing Phase 2 worker; no second app/queue/controller."""
import json
import os
from pathlib import Path
from threading import Lock
from time import time_ns
from stride_backend.models import Detection, DetectionBatch
from stride_backend.store import Frame, monotonic_ms
from .model import OnnxDetector
from .tracking import Tracker


class Phase2Detector:
    def __init__(self, model, max_sessions=8):
        self.model = model
        self.max_sessions = max_sessions
        self._sessions = {}
        # Phase 2 permits multiple worker threads; one shared ONNX call at a time.
        self._lock = Lock()

    async def detect(self, frame: Frame) -> DetectionBatch:
        # Phase 2 explicitly invokes this coroutine on its bounded worker thread.
        # Do not move it to the HTTP loop or add another async queue here.
        with self._lock:
            meta = frame.metadata
            identity = (frame.generation, meta.source_revision, meta.device_id,
                        meta.boot_id, meta.source, meta.origin)
            previous = self._sessions.get(meta.session_id)
            if previous is None and len(self._sessions) >= self.max_sessions:
                raise RuntimeError('Detector session capacity reached')
            tracker = previous[1] if previous and previous[0] == identity else Tracker()
            self._sessions[meta.session_id] = (identity, tracker)
            found = self.model(frame.jpeg)
            objects, _candidate = tracker.update(found, monotonic_ms())
            # Phase 2 has no sensor/route priority arbiter yet. Never turn raw
            # candidates into final speech merely to make an audio demo succeed.
            return DetectionBatch(
                frame=meta, completed_ms=time_ns() // 1_000_000,
                objects=tuple(Detection(label=obj['label'],score=obj['score'],
                                        bbox=tuple(obj['box']),track_id=obj['track_id'])
                              for obj in objects),
                speech_event=None,
            )


def build_detector():
    """Factory loaded once by STRIDE_DETECTOR_FACTORY=app.vision.phase2:build_detector."""
    repo = Path(__file__).resolve().parents[2]
    path = Path(os.environ.get('LIVE_DETECTOR_MODEL_PATH', repo/'models/yolov8n.onnx'))
    checksum = os.environ.get('LIVE_DETECTOR_MODEL_SHA256')
    manifest = path.with_name('manifest.json')
    if not checksum and manifest.exists():
        checksum = json.loads(manifest.read_text())['onnx_sha256']
    model = OnnxDetector(path, expected_sha256=checksum)
    return Phase2Detector(model,max_sessions=int(os.environ.get('STRIDE_MAX_SESSIONS','8')))
