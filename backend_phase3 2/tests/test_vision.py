import pytest

from stride_backend.models import DetectionBatch, SpeechEvent
from stride_backend.settings import Settings
from stride_backend.store import VerifiedClockAlignment
from tests.live_helpers import ControlledDetector, running


@pytest.fixture
def live(jpeg):
    with running(jpeg, detector=ControlledDetector()) as harness:
        yield harness


def test_start_and_honest_initial_status(live):
    response = live.action("start")
    assert response.status_code == 200
    assert response.json()["state"] == "active"
    assert response.json()["generation"] == 1
    assert response.json()["status"] == "unavailable"
    assert live.latest()["objects"] == []
    assert live.detector.calls == []


def test_pause_resume_and_stop(live):
    start = live.action("start").json()
    pause = live.action("pause").json()
    assert pause["state"] == "paused" and pause["status"] == "paused"
    resume = live.action("resume").json()
    assert resume["state"] == "active"
    stop = live.action("stop").json()
    assert stop["state"] == "stopped" and stop["status"] == "unavailable"
    assert start["generation"] < pause["generation"] < resume["generation"] < stop["generation"]
    assert start["state_seq"] < pause["state_seq"] < resume["state_seq"] < stop["state_seq"]


@pytest.mark.parametrize("before,invalid", [
    ([], "pause"), ([], "resume"), (["start"], "start"),
    (["start", "pause"], "pause"), (["start", "pause"], "start"),
    (["stop"], "start"), (["stop"], "resume"), (["stop"], "pause"),
])
def test_invalid_transitions_are_deterministic(live, before, invalid):
    for index, action in enumerate(before):
        assert live.action(action, f"before-{index}").status_code == 200
    previous = live.latest()
    response = live.action(invalid, "invalid")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert live.action(invalid, "invalid").json() == response.json()
    assert live.latest()["generation"] == previous["generation"]


def test_duplicate_actions_and_old_start_cannot_revive_stopped(live):
    start = live.action("start", "a1").json()
    again = live.action("start", "a1").json()
    assert again["duplicate"] is True
    assert again["generation"] == start["generation"]
    assert live.action("pause", "a1").status_code == 409
    stop = live.action("stop", "a2").json()
    replay = live.action("start", "a1").json()
    assert replay["duplicate"] is True and replay["state"] == "stopped"
    assert replay["state_seq"] == stop["state_seq"]
    assert live.action("start", "unknown-old-start").status_code == 409


def test_optional_generation_precondition(live):
    generation = live.action("start").json()["generation"]
    assert live.action("pause", expected_generation=generation).status_code == 200
    assert live.action("resume", expected_generation=generation).status_code == 409
    assert live.latest()["state"] == "paused"


def test_independent_session_state(live):
    live.action("start")
    live.action("start", session="session-2")
    live.action("pause")
    assert live.latest()["status"] == "paused"
    assert live.latest("session-2")["state"] == "active"
    live.action("stop", session="session-2")
    assert live.latest()["state"] == "paused"


def test_automatic_frame_dispatch_and_publication(live):
    live.action("start")
    assert live.upload().status_code == 202
    live.detector.wait_calls(1)
    assert live.latest()["status"] == "unavailable"
    live.detector.release()
    result = live.wait(lambda state: state.status == "live")
    assert result["objects"][0] == {
        "label": "chair", "score": 0.8, "bbox": [0.1, 0.1, 0.3, 0.8],
        "track_id": "supplied-track", "position": "left",
    }
    assert result["frame_id"] == "frame-1"
    assert result["received_ms"] == live.clock.epoch()
    assert result["completed_ms"] == live.clock.epoch()
    assert result["freshness_basis"] == "server_receipt"
    assert result["camera_clock_aligned"] is False
    assert result["age_ms"] == 0
    assert result["upload_hz"] == result["inference_hz"] == result["result_hz"] == 1


@pytest.mark.parametrize("action", ["pause", "stop"])
def test_inactive_upload_receipt_preserved_but_frame_not_dispatched(live, action):
    live.action("start")
    live.action(action)
    assert live.upload().status_code == 202
    state = live.latest()
    assert state["pending_frames"] == 0 and state["in_flight"] is False
    assert state["objects"] == [] and state["speech_event"] is None
    assert state["dropped_frames"] == 1
    assert live.detector.calls == []
    if action == "pause":
        live.action("resume")
        assert live.latest()["pending_frames"] == 0


def test_pre_start_frame_is_not_replayed(live):
    assert live.upload().status_code == 202
    assert live.latest()["state"] == "idle"
    live.action("start")
    assert live.latest()["pending_frames"] == 0
    assert live.detector.calls == []


def test_slow_inference_keeps_only_newest_pending_and_one_claim(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    for sequence in range(2, 12):
        response = live.upload(sequence)
        assert response.status_code == 202
    state = live.latest()
    assert state["pending_frames"] == 1
    assert state["superseded_frames"] == 9
    assert state["dropped_frames"] == 9
    assert len(live.detector.calls) == 1
    live.detector.release()
    live.detector.wait_calls(2)
    assert live.detector.calls[1].metadata.sequence == 11
    assert live.detector.max_active["session-1"] == 1
    # A fresh completed observation remains useful while a newer frame waits.
    assert live.latest()["frame_id"] == "frame-1"
    live.detector.release(1)
    live.wait(lambda state: state.frame_id == "frame-11")


def test_absent_detector_is_unavailable_and_bounded(jpeg):
    with running(jpeg) as live:
        assert live.action("start").status_code == 200
        for sequence in range(1, 5):
            assert live.upload(sequence).status_code == 202
        state = live.latest()
        assert state["detector_configured"] is False
        assert state["status"] == "unavailable" and state["result_hz"] == 0
        assert state["objects"] == [] and state["pending_frames"] == 1
        assert live.app.state.inference_worker.tasks == []


def test_detector_exception_reported_without_leaking_message(live):
    def failure(frame):
        raise RuntimeError("sensitive internal details")
    live.detector.callback = failure
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    state = live.wait(lambda state: state.last_inference_error == "detector_error" and not state.in_flight)
    assert state["objects"] == [] and state["status"] == "unavailable"
    assert state["inference_hz"] == 1 and state["result_hz"] == 0
    assert "sensitive" not in str(state)
    assert live.client.get("/health").json() == {"status": "ok"}
    live.detector.callback = ControlledDetector.result
    live.upload(2)
    live.detector.wait_calls(2)
    live.detector.release(1)
    assert live.wait(lambda state: state.status == "live")["last_inference_error"] is None


def test_stale_inference_cannot_publish_based_on_recent_completion(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.clock.advance(1001)
    live.detector.release()
    state = live.wait(lambda state: state.last_inference_error == "stale_result")
    assert state["objects"] == [] and state["speech_event"] is None
    assert state["published_results"] == 0


def test_expired_result_suppresses_objects_and_events_and_rate(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    first = live.wait(lambda state: state.status == "live")
    live.clock.advance(1001)
    stale = live.latest()
    assert stale["status"] == "stale" and stale["age_ms"] == 1001
    assert stale["state_seq"] > first["state_seq"]
    assert stale["objects"] == [] and stale["speech_event"] is None
    assert stale["result_hz"] == 0
    assert live.latest()["state_seq"] == stale["state_seq"]


@pytest.mark.parametrize("action", ["pause", "stop"])
def test_lifecycle_invalidates_running_and_pending_frames(live, action):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.upload(2)
    live.action(action)
    state = live.latest()
    assert state["objects"] == [] and state["pending_frames"] == 0
    live.detector.release()
    live.wait(lambda state: not state.in_flight)
    assert live.latest()["published_results"] == 0


def test_resume_generation_rejects_old_inference(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    old_generation = live.detector.calls[0].generation
    live.action("pause")
    live.action("resume")
    live.upload(2)
    live.detector.release()
    live.detector.wait_calls(2)
    assert live.latest()["objects"] == []
    assert live.latest()["published_results"] == 0
    assert live.detector.calls[1].generation > old_generation
    live.detector.release(1)
    live.wait(lambda state: state.frame_id == "frame-2" and state.status == "live")


def test_source_switch_invalidates_tracking_and_old_publication(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    assert live.upload(2, device_id="camera-2", source_revision=1).status_code == 202
    assert live.latest()["source_revision"] == 1
    assert live.latest()["speech_event"] is None
    live.detector.release()
    live.detector.wait_calls(2)
    assert live.latest()["published_results"] == 0
    live.detector.release(1)
    state = live.wait(lambda state: state.status == "live")
    assert state["device_id"] == "camera-2"
    assert state["objects"][0]["track_id"] == "supplied-track"
    assert live.upload(3, source_revision=0).status_code == 409
    assert live.upload(3, device_id="camera-3", source_revision=1).status_code == 409


def test_duplicate_polling_preserves_event_id_without_new_state(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    first = live.wait(lambda state: state.status == "live")
    second = live.latest()
    assert second["speech_event"] == first["speech_event"]
    assert second["state_seq"] == first["state_seq"]
    assert first["speech_event"]["event_id"] == "supplied-event-frame-1"
    assert first["speech_event"]["generation"] == first["generation"]


def test_previously_seen_event_is_not_reissued_in_a_new_result(live):
    def same_event(frame):
        return ControlledDetector.result(frame).model_copy(update={"speech_event": SpeechEvent(event_id="stable", text="Test only")})
    live.detector.callback = same_event
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    assert live.wait(lambda state: state.status == "live")["speech_event"]["event_id"] == "stable"
    live.upload(2)
    live.detector.wait_calls(2)
    live.detector.release(1)
    assert live.wait(lambda state: state.frame_id == "frame-2")["speech_event"] is None


@pytest.mark.parametrize("path,value", [
    (("objects", 0, "bbox"), [-0.1, 0, 1, 1]),
    (("objects", 0, "bbox"), [0.8, 0, 0.2, 1]),
    (("objects", 0, "bbox"), [0, 0, float("nan"), 1]),
    (("objects", 0, "bbox"), [0, 0, float("inf"), 1]),
    (("objects", 0, "score"), 1.1), (("objects", 0, "score"), -0.1),
    (("objects", 0, "score"), float("nan")), (("provider",), "unsupported"),
    (("objects", 0, "score"), True), (("objects", 0, "score"), "0.8"),
])
def test_invalid_detector_values_rejected(live, path, value):
    def invalid(frame):
        data = ControlledDetector.result(frame).model_dump()
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return data
    live.detector.callback = invalid
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    state = live.wait(lambda state: state.last_inference_error == "invalid_result")
    assert state["status"] == "unavailable" and state["objects"] == []


@pytest.mark.parametrize("field,value", [
    ("session_id", "other"), ("frame_id", "other"), ("device_id", "other"),
    ("boot_id", "other"), ("source_revision", 99), ("receipt_id", "other"),
])
def test_returned_identity_must_match_claim(live, field, value):
    def invalid(frame):
        data = ControlledDetector.result(frame).model_dump()
        data["frame"][field] = value
        return data
    live.detector.callback = invalid
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    state = live.wait(lambda state: state.last_inference_error == "identity_mismatch")
    assert state["published_results"] == 0


def test_status_distinguishes_upload_inference_and_result_rates(live):
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    response = live.client.get("/status?session_id=session-1", headers=live.headers())
    assert response.headers["cache-control"] == "no-store"
    status = response.json()
    assert status["backend"] == {"status": "ok"}
    assert status["vision"]["upload_hz"] == 1
    assert status["vision"]["inference_hz"] == status["vision"]["result_hz"] == 0
    assert status["vision"]["status"] == "unavailable"
    assert live.client.get("/vision/latest?session_id=session-1", headers=live.headers()).headers["cache-control"] == "no-store"


def test_clock_alignment_is_opt_in_and_rejects_old_capture(live):
    live.action("start")
    live.store.register_clock_alignment("session-1", VerifiedClockAlignment(
        device_id="camera-1", boot_id="boot-1", offset_ms=1700000000000,
        uncertainty_ms=10, valid_until_monotonic_ms=live.clock.mono() + 10000,
    ))
    live.upload(captured_ms=live.clock.mono() - 2000)
    assert live.latest()["pending_frames"] == 0
    assert live.detector.calls == []
    live.upload(2, captured_ms=live.clock.mono() - 20)
    live.detector.wait_calls(1)
    live.detector.release()
    state = live.wait(lambda state: state.status == "live")
    assert state["freshness_basis"] == "aligned_capture"
    assert state["camera_clock_aligned"] is True
    assert state["age_ms"] == 30


def test_no_speech_provider_returns_null(live):
    live.detector.callback = lambda frame: DetectionBatch(frame=frame.metadata, completed_ms=0, objects=())
    live.action("start")
    live.upload()
    live.detector.wait_calls(1)
    live.detector.release()
    assert live.wait(lambda state: state.status == "live")["speech_event"] is None


def test_production_fixture_upload_cannot_appear_live(jpeg):
    settings = Settings(_env_file=None, local_dev=False, device_token="test-device-token",
                        session_tokens={"session-1": "ui-token-1"})
    detector = ControlledDetector()
    with running(jpeg, detector=detector, settings=settings) as live:
        live.action("start")
        assert live.upload().status_code == 202
        state = live.latest()
        assert state["status"] == "unavailable" and state["objects"] == []
        assert state["last_inference_error"] == "non_live_source"
        assert detector.calls == []
