import asyncio
from contextlib import contextmanager
import sqlite3

import pytest

from stride_backend.database import Database
from stride_backend.errors import BackendError
from stride_backend.models import Detection
from stride_backend.settings import Settings
from tests.live_helpers import ControlledDetector, running


@pytest.fixture
def memory_live(jpeg):
    with running(jpeg, detector=ControlledDetector()) as live:
        live.action("start")
        yield live


def publish(live, sequence=1, *, track="supplied-track", label="chair"):
    live.detector.callback = lambda frame: ControlledDetector.result(frame).model_copy(update={
        "objects": (Detection(label=label, score=0.8, bbox=(0.1, 0.1, 0.3, 0.8), track_id=track),),
    })
    index = len(live.detector.calls)
    assert live.upload(sequence).status_code == 202
    live.detector.wait_calls(index + 1)
    live.detector.release(index)
    live.wait(lambda state: state.frame_id == f"frame-{sequence}" and not state.in_flight)
    return live.store.latest_detections("session-1")


def record(live, batch, tracks=("supplied-track",), session="session-1"):
    return asyncio.run(live.app.state.memory.record_sightings(session_id=session, batch=batch, track_ids=tracks))


def recall(live, session="session-1", **params):
    response = live.client.get("/memory", headers=live.headers(session), params={"session_id": session, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_sighting_is_explicit_preserves_provenance_and_original_times(memory_live):
    live = memory_live
    batch = publish(live)
    assert recall(live)["sightings"] == []  # No per-frame persistence.
    assert record(live, batch).saved == 1
    live.clock.advance(5000)
    sighting = recall(live)["sightings"][0]
    assert sighting["observation"] == "last_seen"
    assert sighting["age_ms"] == 5000
    assert sighting["source"] == "fixture" and sighting["provider"] == "yolo"
    assert sighting["captured_ms"] == 42
    assert sighting["captured_at"] is None
    assert sighting["timestamp_basis"] == "server_receipt"
    assert sighting["last_seen_at"] == batch.frame.received_ms
    assert sighting["recorded_at"] == batch.frame.received_ms
    assert sighting["track_id"] == "supplied-track"
    assert sighting["checkpoint_id"] is None


def test_associates_only_checkpoint_confirmed_by_observation_time(memory_live):
    live = memory_live
    live.app.state.route_catalog.mark_checked("demo-hallway", "TEST ONLY fixture verification")
    state = live.client.post("/route", headers=live.headers(), json={"session_id": "session-1", "route_id": "demo-hallway", "action_id": "nav-start", "action": "start"}).json()
    state = live.client.post("/route", headers=live.headers(), json={"session_id": "session-1", "navigation_id": state["navigation_id"], "expected_revision": state["state_revision"], "action_id": "confirm-a", "action": "confirm"}).json()
    live.clock.advance(10)
    batch = publish(live)
    live.clock.advance(10)
    assert live.client.post("/route", headers=live.headers(), json={"session_id": "session-1", "navigation_id": state["navigation_id"], "expected_revision": state["state_revision"], "action_id": "confirm-b", "action": "confirm"}).status_code == 200
    assert record(live, batch).saved == 1
    sighting = recall(live)["sightings"][0]
    assert sighting["checkpoint_id"] == "demo-hallway:A"
    assert sighting["checkpoint_association"] == "last_user_confirmed"
    assert sighting["recorded_at"] > sighting["last_seen_at"]


def test_duplicate_sightings_and_cooldown_do_not_write_every_frame(memory_live):
    live = memory_live
    batch = publish(live)
    first = record(live, batch)
    assert first.saved == 1
    assert record(live, batch).skipped == 1
    original = recall(live)["sightings"][0]
    live.clock.advance(100)
    assert record(live, publish(live, 2)).skipped == 1
    assert recall(live)["sightings"][0]["frame_id"] == "frame-1"
    live.clock.advance(30000)
    assert record(live, publish(live, 3)).saved == 1
    sightings = recall(live)["sightings"]
    assert len(sightings) == 1
    assert sightings[0]["sighting_id"] == original["sighting_id"]
    assert sightings[0]["frame_id"] == "frame-3" and sightings[0]["age_ms"] == 0


def test_sighting_storage_and_history_responses_are_bounded(jpeg):
    settings = Settings(_env_file=None, local_dev=True, device_token="test-device-token",
                        session_tokens={"session-1": "ui-token-1", "session-2": "ui-token-2"}, max_sightings_per_session=2)
    with running(jpeg, detector=ControlledDetector(), settings=settings) as live:
        live.action("start")
        for sequence in (1, 2, 3):
            live.clock.advance(1)
            batch = publish(live, sequence, track=f"track-{sequence}")
            assert record(live, batch, (f"track-{sequence}",)).saved == 1
        assert len(recall(live)["sightings"]) == 2
        assert len(recall(live, limit=1)["sightings"]) == 1
        with live.app.state.database.transaction() as connection:
            assert connection.execute("SELECT COUNT(*) FROM object_sightings").fetchone()[0] == 2


def test_memory_is_scoped_even_when_other_session_id_is_known(memory_live):
    live = memory_live
    record(live, publish(live))
    assert recall(live, "session-2")["sightings"] == []
    assert live.client.get("/memory?session_id=session-2", headers=live.headers()).status_code == 401


@pytest.mark.parametrize("field,value", [("frame_id", "other"), ("source", "real"), ("device_id", "other"), ("source_revision", 99)])
def test_sighting_identity_cannot_be_forged(memory_live, field, value):
    live = memory_live
    batch = publish(live)
    altered = batch.model_copy(update={"frame": batch.frame.model_copy(update={field: value})})
    with pytest.raises(BackendError) as error:
        record(live, altered)
    assert error.value.code == "sighting_not_current"
    assert recall(live)["sightings"] == []


def test_cross_session_hook_and_stale_batch_rejected(memory_live):
    live = memory_live
    batch = publish(live)
    with pytest.raises(BackendError) as error:
        record(live, batch, session="session-2")
    assert error.value.code == "sighting_identity_mismatch"
    live.clock.advance(1001)
    with pytest.raises(BackendError) as error:
        record(live, batch)
    assert error.value.code == "sighting_not_current"


@pytest.mark.parametrize("tracks", [(), ("absent",), ("supplied-track", "supplied-track"), ("x",) * 17, (["not-hashable"],)])
def test_invalid_confirmed_track_selection_is_rejected(memory_live, tracks):
    batch = publish(memory_live)
    with pytest.raises(BackendError) as error:
        record(memory_live, batch, tracks)
    assert error.value.status_code == 422


def test_memory_failure_does_not_crash_or_change_detector_state(memory_live, monkeypatch):
    live = memory_live
    batch = publish(live)

    @contextmanager
    def broken(**kwargs):
        raise sqlite3.OperationalError("private database path")
        yield

    with monkeypatch.context() as scoped:
        scoped.setattr(live.app.state.database, "transaction", broken)
        result = record(live, batch)
        assert result.error == "memory_unavailable" and result.saved == 0
    assert live.latest()["status"] == "live"
    assert live.latest()["last_inference_error"] is None
    publish(live, 2)
    assert live.latest()["frame_id"] == "frame-2"


def test_memory_database_reopens_without_images_or_credentials(memory_live):
    live = memory_live
    record(live, publish(live))
    database = Database(live.app.state.settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        row = connection.execute("SELECT * FROM object_sightings WHERE session_id=?", ("session-1",)).fetchone()
        assert row["label"] == "chair"
        schema = " ".join(row[0] for row in connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
        assert "BLOB" not in schema and "device_token" not in schema and "session_token" not in schema
