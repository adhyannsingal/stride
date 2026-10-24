from dataclasses import replace

import pytest

from stride_backend.errors import BackendError
from stride_backend.models import DetectionBatch, ReceivedFrameMetadata
from stride_backend.store import Frame, LatestFrameStore


@pytest.fixture
def clock():
    return [100]


@pytest.fixture
def store(settings, clock):
    return LatestFrameStore(settings, clock=lambda: clock[0])


def make_frame(clock, *, session="s1", boot="b1", sequence=1, revision=0):
    meta = ReceivedFrameMetadata(
        session_id=session, device_id="d1", boot_id=boot, frame_id=f"f{sequence}",
        sequence=sequence, captured_ms=0, source="fixture", source_revision=revision,
        receipt_id=f"{session}:{boot}:{sequence}:{clock[0]}", received_ms=clock[0],
        size_bytes=1, width=1, height=1,
    )
    return Frame(b"test-only", meta, clock[0])


def result(frame):
    # Empty test batch; no detector or fabricated live objects.
    return DetectionBatch(frame=frame.metadata, completed_ms=frame.metadata.received_ms, objects=())


def test_capacity(settings, clock):
    store = LatestFrameStore(settings.model_copy(update={"max_sessions": 1}), clock=lambda: clock[0])
    store.put(make_frame(clock))
    with pytest.raises(BackendError) as error:
        store.put(make_frame(clock, session="s2"))
    assert error.value.status_code == 429
    assert store.take_latest("s1").metadata.session_id == "s1"


def test_boot_history_bounded(settings, clock):
    store = LatestFrameStore(settings.model_copy(update={"max_streams_per_session": 1}), clock=lambda: clock[0])
    store.put(make_frame(clock))
    with pytest.raises(BackendError) as error:
        store.put(make_frame(clock, boot="b2"))
    assert error.value.code == "stream_capacity"


def test_expired_session_releases_capacity(settings, clock):
    store = LatestFrameStore(settings.model_copy(update={"max_sessions": 1}), clock=lambda: clock[0])
    store.put(make_frame(clock))
    clock[0] += settings.session_ttl_ms + 1
    store.put(make_frame(clock, session="s2"))
    assert store.take_latest("s1") is None
    assert store.take_latest("s2") is not None


def test_session_expiry_does_not_release_an_active_claim(store, settings, clock):
    store.put(make_frame(clock))
    first = store.take_latest("s1")
    clock[0] += settings.session_ttl_ms + 1
    store.put(make_frame(clock, sequence=2))
    assert store.take_latest("s1") is None
    assert store.publish_detections(result(first)) is False
    store.finish(first)
    assert store.take_latest("s1").metadata.sequence == 2


def test_pending_freshness_uses_monotonic_receipt(store, settings, clock):
    frame = make_frame(clock)
    frame = replace(frame, metadata=frame.metadata.model_copy(update={"captured_ms": 9999999999999}))
    store.put(frame)
    clock[0] += settings.frame_freshness_ms + 1
    assert store.take_latest("s1") is None
    # Still remember high-water sequence after dropping stale image bytes.
    with pytest.raises(BackendError) as error:
        store.put(make_frame(clock))
    assert error.value.code == "sequence_regression"


def test_single_claim_and_latest_pending_during_inference(store, clock):
    store.put(make_frame(clock))
    first = store.take_latest("s1")
    clock[0] += 10
    store.put(make_frame(clock, sequence=2))
    store.put(make_frame(clock, sequence=3))
    assert store.take_latest("s1") is None
    assert store.publish_detections(result(first)) is True
    assert store.publish_detections(result(first)) is False
    store.finish(first)
    newest = store.take_latest("s1")
    assert newest.metadata.sequence == 3
    assert store.publish_detections(result(newest)) is True
    assert store.latest_detections("s1").frame == newest.metadata


@pytest.mark.parametrize("field,value", [
    ("session_id", "other"), ("frame_id", "other"), ("device_id", "other"),
    ("boot_id", "other"), ("sequence", 99), ("receipt_id", "other"),
])
def test_mismatched_detection_rejected(store, clock, field, value):
    store.put(make_frame(clock))
    frame = store.take_latest("s1")
    batch = result(frame).model_copy(update={"frame": frame.metadata.model_copy(update={field: value})})
    assert store.publish_detections(batch) is False
    assert store.latest_detections("s1") is None


def test_expired_result_rejected_despite_new_upload(store, settings, clock):
    store.put(make_frame(clock))
    frame = store.take_latest("s1")
    clock[0] += settings.frame_freshness_ms + 1
    store.put(make_frame(clock, sequence=2))
    assert store.publish_detections(result(frame)) is False
    store.finish(frame)
    assert store.take_latest("s1").metadata.sequence == 2


def test_result_expires_while_new_frames_arrive(store, settings, clock):
    store.put(make_frame(clock))
    frame = store.take_latest("s1")
    assert store.publish_detections(result(frame))
    clock[0] += settings.frame_freshness_ms + 1
    store.put(make_frame(clock, sequence=2))
    assert store.latest_detections("s1") is None


def test_source_change_invalidates_results(store, clock):
    store.put(make_frame(clock))
    frame = store.take_latest("s1")
    assert store.publish_detections(result(frame))
    store.put(make_frame(clock, sequence=2, revision=1))
    assert store.latest_detections("s1") is None
    assert store.publish_detections(result(frame)) is False
    with pytest.raises(BackendError) as error:
        store.put(make_frame(clock, sequence=3, revision=0))
    assert error.value.code == "source_revision_regression"


def test_finish_does_not_release_another_claim(store, clock):
    store.put(make_frame(clock))
    first = store.take_latest("s1")
    store.finish(first)
    store.put(make_frame(clock, sequence=2))
    second = store.take_latest("s1")
    store.finish(first)
    store.put(make_frame(clock, sequence=3))
    assert store.take_latest("s1") is None
    store.finish(second)
    assert store.take_latest("s1").metadata.sequence == 3
