import asyncio
import tempfile

from fastapi.testclient import TestClient

from stride_backend.ingestion import IngestionGuard, MULTIPART_OVERHEAD_BYTES


def test_streamed_body_limit_without_content_length(settings):
    called = False
    sent = []

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    chunks = iter([
        {"type": "http.request", "body": b"x" * settings.max_frame_bytes, "more_body": True},
        {"type": "http.request", "body": b"x" * (MULTIPART_OVERHEAD_BYTES + 1), "more_body": False},
    ])

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/frame", "headers": [
        (b"x-device-token", b"test-device-token"),
        (b"content-type", b"multipart/form-data; boundary=test"),
    ]}
    asyncio.run(IngestionGuard(downstream, settings)(scope, receive, send))
    assert called is False
    assert sent[0]["status"] == 413


def test_unauthorized_body_never_read(settings):
    async def forbidden(*args):
        raise AssertionError("Must not read or parse an unauthorized body")

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/frame", "headers": []}
    asyncio.run(IngestionGuard(forbidden, settings)(scope, forbidden, send))
    assert sent[0]["status"] == 401


def test_upload_does_not_spill_to_disk(upload, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Image uploads must remain in RAM")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", forbidden)
    assert upload().status_code == 202


def test_root_path_preserves_ingestion_auth(app, jpeg, metadata):
    with TestClient(app, root_path="/api") as client:
        response = client.post("/api/frame", data=metadata, files={"file": ("f.jpg", jpeg, "image/jpeg")})
        assert response.status_code == 401
        response = client.post(
            "/api/frame", data=metadata, files={"file": ("f.jpg", jpeg, "image/jpeg")},
            headers={"X-Device-Token": "test-device-token"},
        )
        assert response.status_code == 202
