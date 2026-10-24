from time import time_ns

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stride_backend.main import create_app
from stride_backend.settings import Settings


def test_health_docs_and_time(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    form = schema["paths"]["/frame"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert set(form["required"]) == {"file", "session_id", "device_id", "boot_id", "frame_id", "sequence", "captured_ms", "source"}
    assert schema["paths"]["/frame"]["post"]["security"] == [{"APIKeyHeader": []}]
    before = time_ns() // 1_000_000
    response = client.get("/time")
    assert response.status_code == 200
    assert before <= response.json()["server_ms"] <= time_ns() // 1_000_000
    assert response.headers["cache-control"] == "no-store"


def test_successful_upload(upload, jpeg, app):
    before = time_ns() // 1_000_000
    response = upload()
    assert response.status_code == 202, response.text
    receipt = response.json()
    assert receipt["frame_id"] == "frame-1"
    assert receipt["captured_ms"] == 42
    assert before <= receipt["received_ms"] <= time_ns() // 1_000_000
    assert receipt["camera_clock_aligned"] is False
    assert receipt["freshness_basis"] == "server_receipt"
    assert receipt["size_bytes"] == len(jpeg)
    assert (receipt["width"], receipt["height"]) == (32, 24)
    assert receipt["replaced_pending"] is False
    frame = app.state.frame_store.take_latest("session-1")
    assert frame.jpeg == jpeg
    assert frame.metadata.receipt_id == receipt["receipt_id"]


@pytest.mark.parametrize("image", [b"", b"not a jpeg", b"\xff\xd8bad image\xff\xd9"])
def test_invalid_jpeg(upload, image, app):
    response = upload(image=image)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_jpeg"
    assert app.state.frame_store.take_latest("session-1") is None


def test_oversized_file(upload, settings):
    response = upload(image=b"x" * (settings.max_frame_bytes + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "frame_too_large"


def test_oversized_request(upload, settings):
    response = upload(image=b"x" * (settings.max_frame_bytes + 20000))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "frame_too_large"


@pytest.mark.parametrize("field", ["session_id", "device_id", "boot_id", "frame_id", "sequence", "captured_ms", "source"])
def test_missing_fields(upload, metadata, field):
    del metadata[field]
    response = upload(data=metadata)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert field in response.json()["error"]["fields"]


def test_missing_file(client, metadata):
    response = client.post("/frame", data=metadata, files={"unused": (None, "value")}, headers={"X-Device-Token": "test-device-token"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("field,value", [
    ("session_id", " "), ("frame_id", " "), ("device_id", " "), ("boot_id", " "),
    ("sequence", "-1"), ("captured_ms", "-1"), ("source", "unavailable"), ("sequence", "abc"),
    ("session_id", "x" * 129),
])
def test_invalid_metadata(upload, metadata, field, value):
    metadata[field] = value
    response = upload(data=metadata)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("headers", [{}, {"X-Device-Token": "wrong-token"}])
def test_unauthorized(upload, headers):
    response = upload(headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert "wrong-token" not in response.text


def test_auth_before_parsing_or_size_validation(upload, settings):
    assert upload(image=b"x" * (settings.max_frame_bytes + 20000), headers={}).status_code == 401


def test_wrong_mime(upload):
    response = upload(content_type="image/png")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_sequence_regression_and_duplicate(upload, metadata, app):
    metadata["sequence"] = "10"
    assert upload(data=metadata).status_code == 202
    app.state.frame_store.take_latest("session-1")
    for sequence in (10, 9):
        metadata.update(sequence=str(sequence), frame_id=f"frame-{sequence}")
        response = upload(data=metadata)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "sequence_regression"


def test_latest_frame_replacement(upload, metadata, app):
    assert upload().json()["replaced_pending"] is False
    for seq in range(2, 6):
        response = upload(data={**metadata, "sequence": str(seq), "frame_id": f"frame-{seq}"})
        assert response.status_code == 202
        assert response.json()["replaced_pending"] is True
    store = app.state.frame_store
    frame = store.take_latest("session-1")
    assert frame.metadata.frame_id == "frame-5"
    assert store.take_latest("session-1") is None
    store.finish(frame)
    assert store.take_latest("session-1") is None


@pytest.mark.parametrize("field", ["session_id", "device_id", "boot_id"])
def test_sequence_scoped_to_session_device_boot(upload, metadata, field):
    assert upload(data={**metadata, "sequence": "10"}).status_code == 202
    assert upload(data={**metadata, field: "new-value", "sequence": "0"}).status_code == 202


def test_invalid_frame_does_not_advance_sequence(upload):
    assert upload(image=b"invalid").status_code == 422
    assert upload().status_code == 202


def test_protected_by_default(monkeypatch):
    monkeypatch.delenv("STRIDE_DEVICE_TOKEN", raising=False)
    monkeypatch.delenv("STRIDE_LOCAL_DEV", raising=False)
    with pytest.raises(ValidationError, match="STRIDE_DEVICE_TOKEN"):
        Settings(_env_file=None)


def test_explicit_local_dev_allows_tokenless(jpeg, metadata):
    app = create_app(Settings(_env_file=None, local_dev=True, device_token=None))
    with TestClient(app) as client:
        response = client.post("/frame", data=metadata, files={"file": ("f.jpg", jpeg, "image/jpeg")})
        assert response.status_code == 202


def test_errors_use_consistent_envelope(client):
    for path in ("/missing", "/frame"):
        response = client.get(path)
        assert response.status_code in (404, 405)
        assert set(response.json()) == {"error"}
        assert set(response.json()["error"]) == {"code", "message", "fields"}


def test_malformed_multipart(client):
    response = client.post("/frame", content=b"broken", headers={"X-Device-Token": "test-device-token", "Content-Type": "multipart/form-data"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_multipart"
