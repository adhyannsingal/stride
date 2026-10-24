"""Detector seam only. No model imports, model loading, or fabricated results."""

from typing import Protocol

from .models import DetectionBatch
from .store import Frame


class Detector(Protocol):
    async def detect(self, frame: Frame) -> DetectionBatch:
        """Infer from frame.jpeg and return a batch preserving frame.metadata exactly.

        A synchronous model must run off the HTTP event loop. The integration
        worker owns scheduling: at most one inference job per session, taking
        the newest pending frame each time instead of accumulating a queue.
        Publish using app.state.frame_store.publish_detections(batch), which
        returns False for stale results or mismatched/source-invalidated receipts.
        Always call store.finish(frame) in a finally block to release the claim.
        """
        ...
