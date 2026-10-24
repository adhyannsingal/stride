import asyncio
import sys
from types import ModuleType

from fastapi.testclient import TestClient

from stride_backend.main import create_app
from stride_backend.settings import Settings
from tests.live_helpers import ControlledDetector, running


def config(**changes):
    return Settings(_env_file=None, device_token="test-device-token", local_dev=True,
                    session_tokens={"session-1": "ui-token-1", "session-2": "ui-token-2"}, **changes)


def test_fixed_worker_count_and_http_loop_remains_responsive(jpeg):
    detector = ControlledDetector()
    with running(jpeg, detector=detector, settings=config(inference_workers=2)) as live:
        workers = live.app.state.inference_worker
        assert len(workers.tasks) == 2
        live.action("start")
        live.action("start", session="session-2")
        live.upload()
        live.upload(session="session-2")
        detector.wait_calls(2)
        assert {frame.metadata.session_id for frame in detector.calls} == {"session-1", "session-2"}
        assert live.client.get("/health").status_code == 200
        assert live.client.get("/time").status_code == 200
        for seq in range(2, 10):
            live.upload(seq)
        assert len(workers.tasks) == 2
        assert len(detector.calls) == 2
        assert live.latest()["pending_frames"] == 1
    assert all(task.done() for task in workers.tasks)


def test_timeout_does_not_start_a_second_call_or_publish_late_result(jpeg):
    detector = ControlledDetector()
    with running(jpeg, detector=detector, settings=config(inference_timeout_ms=10)) as live:
        live.action("start")
        live.upload()
        detector.wait_calls(1)
        state = live.wait(lambda state: state.last_inference_error == "inference_timeout")
        assert state["in_flight"] is True
        live.upload(2)
        assert len(detector.calls) == 1
        detector.release()
        detector.wait_calls(2)
        assert live.latest()["published_results"] == 0
        assert detector.max_active["session-1"] == 1
        detector.release(1)
        live.wait(lambda state: state.status == "live")


def test_factory_is_loaded_once_without_rewriting_entrypoint(jpeg, monkeypatch):
    module = ModuleType("stride_test_factory")
    detector = ControlledDetector()
    calls = []

    def factory():
        calls.append(True)
        return detector

    module.build = factory
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with running(jpeg, settings=config(detector_factory="stride_test_factory:build")) as live:
        live.action("start")
        for seq in range(1, 4):
            live.upload(seq)
            detector.wait_calls(seq)
            detector.release(seq - 1)
            live.wait(lambda state: state.frame_id == f"frame-{seq}" and not state.in_flight)
        assert calls == [True]
        assert live.app.state.inference_worker.detector is detector


def test_bad_factory_leaves_server_available_and_honest(jpeg):
    with running(jpeg, settings=config(detector_factory="missing_stride_module:build")) as live:
        assert live.client.get("/health").status_code == 200
        live.action("start")
        state = live.latest()
        assert state["detector_configured"] is False
        assert state["last_inference_error"] == "detector_load_error"
        assert state["status"] == "unavailable"


def test_detector_cancellation_is_an_error_not_a_crashed_dispatcher(jpeg):
    def cancelled(frame):
        raise asyncio.CancelledError
    detector = ControlledDetector(callback=cancelled)
    with running(jpeg, detector=detector) as live:
        live.action("start")
        live.upload()
        detector.wait_calls(1)
        detector.release()
        live.wait(lambda state: state.last_inference_error == "detector_cancelled" and not state.in_flight)
        assert all(not task.done() for task in live.app.state.inference_worker.tasks)


def test_shutdown_cancels_publication_and_releases_claims(jpeg):
    detector = ControlledDetector()
    app = create_app(config(worker_shutdown_grace_ms=0), detector)
    try:
        with TestClient(app) as client:
            client.post("/vision", headers={"X-Session-Token": "ui-token-1"}, json={"session_id": "session-1", "action_id": "a1", "action": "start"})
            client.post("/frame", headers={"X-Device-Token": "test-device-token"}, data={
                "session_id": "session-1", "device_id": "camera-1", "boot_id": "boot-1",
                "frame_id": "frame-1", "sequence": 1, "captured_ms": 0, "source": "fixture",
            }, files={"file": ("fixture.jpg", jpeg, "image/jpeg")})
            detector.wait_calls(1)
            worker = app.state.inference_worker
            store = app.state.frame_store
        assert all(task.done() for task in worker.tasks)
        assert store.snapshot("session-1").objects == ()
        assert store.take_latest("session-1") is None
    finally:
        detector.release_all()


def test_lifespan_can_restart_without_reinitializing_injected_detector(jpeg):
    detector = ControlledDetector(blocking=False)
    app = create_app(config(), detector)
    for _ in range(2):
        with TestClient(app) as client:
            response = client.post("/vision", headers={"X-Session-Token": "ui-token-1"}, json={"session_id": "session-1", "action_id": "a1", "action": "start"})
            assert response.status_code == 200
            assert len(app.state.inference_worker.tasks) == 1
        assert all(task.done() for task in app.state.inference_worker.tasks)


def test_bounded_action_history_reserves_stop_and_retains_tombstone(jpeg):
    with running(jpeg, settings=config(max_actions_per_session=2)) as live:
        assert live.action("start").status_code == 200
        assert live.action("pause").status_code == 200
        assert live.action("resume").status_code == 429
        assert live.action("stop").status_code == 200
        live.clock.advance(10000000)
        replay = live.action("start").json()
        assert replay["duplicate"] is True and replay["state"] == "stopped"
        assert len(live.store._sessions["session-1"].actions) == 3


def test_controlled_session_capacity_is_bounded(jpeg):
    settings = Settings(_env_file=None, local_dev=True, max_sessions=1)
    with running(jpeg, settings=settings) as live:
        assert live.client.post("/vision", json={"session_id": "s1", "action_id": "a1", "action": "start"}).status_code == 200
        response = live.client.post("/vision", json={"session_id": "s2", "action_id": "a2", "action": "start"})
        assert response.status_code == 429
        assert len(live.store._sessions) == 1


def test_upload_generation_ticket_cannot_cross_pause_resume(jpeg):
    with running(jpeg) as live:
        live.action("start")
        ticket = live.store.ingestion_generation("session-1")
        # Create a valid frame through the unchanged Phase 1 path.
        live.upload()
        frame = live.store.take_latest("session-1")
        live.store.finish(frame)
        live.action("pause")
        live.action("resume")
        from dataclasses import replace
        frame = replace(frame, metadata=frame.metadata.model_copy(update={"sequence": 2, "frame_id": "late-upload"}))
        live.store.put(frame, expected_generation=ticket)
        assert live.latest()["pending_frames"] == 0
        assert live.latest()["dropped_frames"] == 1


def test_old_upload_cannot_select_source_or_evict_current_pending(jpeg):
    from dataclasses import replace
    with running(jpeg) as live:
        live.action("start")
        ticket = live.store.ingestion_generation("session-1")
        live.upload()
        first = live.store.take_latest("session-1")
        live.store.finish(first)
        live.action("pause")
        live.action("resume")
        live.upload(2)
        old = replace(first, metadata=first.metadata.model_copy(update={
            "device_id": "old-delayed-camera", "source_revision": 99, "sequence": 3,
        }))
        assert live.store.put(old, expected_generation=ticket) is False
        assert live.latest()["pending_frames"] == 1
        assert live.latest()["source_revision"] == 0
        assert live.store.take_latest("session-1").metadata.frame_id == "frame-2"


def test_speech_history_is_bounded(jpeg):
    detector = ControlledDetector()
    with running(jpeg, detector=detector, settings=config(max_speech_events_per_generation=1)) as live:
        live.action("start")
        for seq in (1, 2):
            live.upload(seq)
            detector.wait_calls(seq)
            detector.release(seq - 1)
            state = live.wait(lambda state: state.frame_id == f"frame-{seq}")
            assert (state["speech_event"] is not None) == (seq == 1)
        assert len(live.store._sessions["session-1"].seen_speech_ids) == 1
