"""Detector protocol and optional factory loading; no model runtime dependencies."""

from importlib import import_module
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


def load_detector(factory_path: str) -> Detector:
    """Load one user-provided zero-argument factory, once during app assembly."""
    module_name, separator, attribute = factory_path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("STRIDE_DETECTOR_FACTORY must be module:factory")
    factory = getattr(import_module(module_name), attribute)
    detector = factory()
    if not callable(getattr(detector, "detect", None)):
        raise TypeError("Detector factory must return an object with detect(frame)")
    return detector
