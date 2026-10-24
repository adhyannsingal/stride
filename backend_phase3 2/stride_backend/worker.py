"""Fixed asynchronous dispatchers with bounded off-loop detector execution."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from .detector import Detector
from .models import DetectionBatch
from .settings import Settings
from .store import Frame, LatestFrameStore


class DetectorCancelled(Exception):
    pass


def _invoke(detector: Detector, frame: Frame):
    # Even a poorly behaved async adapter doing blocking CPU work cannot block
    # the HTTP loop. Adapter coroutines run on a worker thread's event loop.
    try:
        return asyncio.run(detector.detect(frame))
    except asyncio.CancelledError:
        raise DetectorCancelled from None


def _consume_exception(future):
    if not future.cancelled():
        future.exception()


class InferenceWorker:
    def __init__(self, store: LatestFrameStore, detector: Detector | None, settings: Settings):
        self.store = store
        self.detector = detector
        self.settings = settings
        self.tasks: list[asyncio.Task] = []
        self._wake = asyncio.Event()
        self._pool: ThreadPoolExecutor | None = None
        self._stopping = False

    async def start(self) -> None:
        if self.tasks and any(not task.done() for task in self.tasks):
            return
        self.store.startup()
        self._stopping = False
        self._wake = asyncio.Event()
        self.tasks = []
        if self.detector is None:
            return
        count = min(self.settings.inference_workers, self.settings.max_sessions)
        self._pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix="stride-inference")
        self.tasks = [asyncio.create_task(self._run(), name=f"stride-inference-{i}") for i in range(count)]

    def notify(self) -> None:
        self._wake.set()

    async def _run(self) -> None:
        while not self._stopping:
            self._wake.clear()
            frame = self.store.take_next_active()
            if frame is None:
                await self._wake.wait()
                continue
            try:
                reason = self.store.publication_error(frame)
                if reason:
                    self.store.fail(frame, reason)
                    continue
                future = asyncio.get_running_loop().run_in_executor(self._pool, _invoke, self.detector, frame)
                future.add_done_callback(_consume_exception)
                try:
                    result = await asyncio.wait_for(asyncio.shield(future), self.settings.inference_timeout_ms / 1000)
                except TimeoutError:
                    self.store.fail(frame, "inference_timeout")
                    # The thread still owns this frame. Do not start another job
                    # for it or grow a queue while a detector is stuck.
                    try:
                        await asyncio.shield(future)
                    except Exception:
                        pass
                    self.store.inference_completed(frame)
                    continue
                self.store.inference_completed(frame)
                try:
                    raw = result.model_dump(warnings=False) if isinstance(result, DetectionBatch) else result
                    batch = DetectionBatch.model_validate(raw)
                except (ValidationError, ValueError, TypeError, AttributeError):
                    self.store.fail(frame, "invalid_result")
                    continue
                if batch.frame != frame.metadata:
                    self.store.fail(frame, "identity_mismatch")
                    continue
                reason = self.store.publication_error(frame)
                if reason:
                    self.store.fail(frame, reason)
                elif not self.store.publish_detections(batch):
                    self.store.fail(frame, "publication_rejected")
            except asyncio.CancelledError:
                self.store.fail(frame, "inference_cancelled")
                raise
            except Exception as exc:
                self.store.inference_completed(frame)
                self.store.fail(frame, "detector_cancelled" if isinstance(exc, DetectorCancelled) else "detector_error")
            finally:
                self.store.finish(frame)
                self.notify()

    async def close(self) -> None:
        self._stopping = True
        self.store.shutdown()
        self.notify()
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=self.settings.worker_shutdown_grace_ms / 1000)
            for task in pending:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
