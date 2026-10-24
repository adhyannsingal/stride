import base64
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stride_backend.main import create_app
from stride_backend.settings import Settings
from tests.live_helpers import Clock, running


@pytest.fixture
def protected_settings():
    return Settings(
        _env_file=None, device_token="camera-only-secret", local_dev=False,
        session_tokens={"session-1": "frontend-secret-1", "session-2": "frontend-secret-2"},
        frontend_origins=("https://phone.example",),
    )


@pytest.mark.parametrize("path", ["/vision/latest?session_id=session-1", "/status?session_id=session-1"])
def test_session_id_or_camera_token_is_not_browser_authorization(protected_settings, path):
    with TestClient(create_app(protected_settings)) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Device-Token": "camera-only-secret"}).status_code == 401
        assert client.get(path, headers={"X-Session-Token": "camera-only-secret"}).status_code == 401


def test_control_requires_authorization(protected_settings):
    with TestClient(create_app(protected_settings)) as client:
        response = client.post("/vision", json={"session_id": "session-1", "action_id": "a1", "action": "start"})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


def test_cross_session_access_denied(protected_settings):
    with TestClient(create_app(protected_settings)) as client:
        headers = {"X-Session-Token": "frontend-secret-1"}
        for path in ("/vision/latest?session_id=session-2", "/status?session_id=session-2"):
            assert client.get(path, headers=headers).status_code == 401
        response = client.post("/vision", headers=headers, json={"session_id": "session-2", "action_id": "x", "action": "start"})
        assert response.status_code == 401
        assert client.get("/vision/latest?session_id=unknown", headers=headers).status_code == 403


def test_cookie_exchange_is_secure_scoped_expiring_and_not_a_device_secret(protected_settings):
    clock = Clock()
    app = create_app(protected_settings, clock=clock.mono, epoch_clock=clock.epoch)
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/auth/session", json={"session_id": "session-1", "session_token": "frontend-secret-1"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert "camera-only-secret" not in cookie and "frontend-secret-1" not in cookie
        assert client.get("/vision/latest?session_id=session-1").status_code == 200
        assert client.get("/vision/latest?session_id=session-2").status_code == 401
        clock.advance(protected_settings.session_cookie_ttl_seconds * 1000 + 1)
        assert client.get("/vision/latest?session_id=session-1").status_code == 401


def test_login_invalid_token_and_tampered_cookie(protected_settings):
    with TestClient(create_app(protected_settings), base_url="https://testserver") as client:
        response = client.post("/auth/session", json={"session_id": "session-1", "session_token": "wrong-secret"})
        assert response.status_code == 401
        assert "wrong-secret" not in response.text
        payload = base64.urlsafe_b64encode(json.dumps({"session_id": "session-1", "expires_ms": 9999999999999}).encode()).decode().rstrip("=")
        client.cookies.set("stride_session", payload + ".invalid")
        assert client.get("/vision/latest?session_id=session-1").status_code == 401


@pytest.mark.parametrize("cookie", ["broken", "x.y", "☃.☃", "."])
def test_malformed_cookies_have_consistent_errors(protected_settings, cookie):
    # Non-ASCII cannot be transported in an HTTP header; test the verifier directly.
    if "☃" in cookie:
        from starlette.requests import Request
        from stride_backend.auth import SessionAuth
        from stride_backend.errors import BackendError
        request = Request({"type": "http", "method": "GET", "path": "/", "scheme": "https", "server": ("testserver", 443), "query_string": b"", "headers": []})
        request._cookies = {"stride_session": cookie}
        with pytest.raises(BackendError) as error:
            SessionAuth(protected_settings, Clock().epoch).authorize(request, "session-1")
        assert error.value.status_code == 401
    else:
        with TestClient(create_app(protected_settings)) as client:
            client.cookies.set("stride_session", cookie)
            assert client.get("/vision/latest?session_id=session-1").status_code == 401


def test_untrusted_origins_rejected_and_cors_is_exact(protected_settings):
    with TestClient(create_app(protected_settings)) as client:
        headers = {"X-Session-Token": "frontend-secret-1", "Origin": "https://evil.example"}
        assert client.get("/vision/latest?session_id=session-1", headers=headers).status_code == 403
        assert client.post("/auth/session", headers={"Origin": "https://evil.example"}, json={"session_id": "session-1", "session_token": "frontend-secret-1"}).status_code == 403
        headers["Origin"] = "https://phone.example"
        response = client.get("/vision/latest?session_id=session-1", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://phone.example"
        assert response.headers["access-control-allow-credentials"] == "true"
        preflight = client.options("/vision", headers={"Origin": "https://phone.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] != "*"


@pytest.mark.parametrize("change", [
    {"frontend_origins": ("*",)}, {"frontend_origins": ("https://*.example",)},
    {"frontend_origins": ("https://phone.example/path",)},
    {"session_tokens": {"session-1": "camera-only-secret"}},
    {"session_tokens": {"session-1": "same", "session-2": "same"}},
    {"session_tokens": {"session-1": " "}},
])
def test_unsafe_configuration_rejected(change):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, local_dev=False, device_token="camera-only-secret", **change)


def test_production_does_not_silently_disable_session_auth(jpeg):
    settings = Settings(_env_file=None, local_dev=False, device_token="test-device-token")
    with running(jpeg, settings=settings) as live:
        assert live.client.get("/health").status_code == 200
        response = live.client.get("/vision/latest?session_id=session-1")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "session_auth_unconfigured"


def test_explicit_local_dev_without_session_credentials(jpeg):
    settings = Settings(_env_file=None, local_dev=True, device_token=None)
    with running(jpeg, settings=settings) as live:
        assert live.client.post("/vision", json={"session_id": "local", "action_id": "a1", "action": "start"}).status_code == 200
        assert live.client.get("/vision/latest?session_id=local").status_code == 200


def test_phone_cookie_upload_does_not_need_device_token(protected_settings, jpeg):
    with TestClient(create_app(protected_settings), base_url="https://testserver") as client:
        assert client.post("/auth/session", json={"session_id": "session-1", "session_token": "frontend-secret-1"}).status_code == 200
        data = {"session_id": "session-1", "device_id": "phone-1", "boot_id": "boot-1", "frame_id": "frame-1", "sequence": 1, "captured_ms": 0, "source": "real"}
        response = client.post("/frame", data=data, files={"file": ("fixture.jpg", jpeg, "image/jpeg")})
        assert response.status_code == 202
        response = client.post("/frame", data={**data, "session_id": "session-2"}, files={"file": ("fixture.jpg", jpeg, "image/jpeg")})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "session_access_denied"


def test_session_header_upload_is_also_scoped(protected_settings, jpeg):
    with TestClient(create_app(protected_settings)) as client:
        data = {"session_id": "session-1", "device_id": "phone-1", "boot_id": "boot-1", "frame_id": "frame-1", "sequence": 1, "captured_ms": 0, "source": "real"}
        headers = {"X-Session-Token": "frontend-secret-1"}
        assert client.post("/frame", headers=headers, data=data, files={"file": ("fixture.jpg", jpeg, "image/jpeg")}).status_code == 202
        assert client.post("/frame", headers=headers, data={**data, "session_id": "session-2"}, files={"file": ("fixture.jpg", jpeg, "image/jpeg")}).status_code == 403


def test_bad_session_upload_rejected_before_reading_body(protected_settings):
    import asyncio
    from stride_backend.auth import SessionAuth
    from stride_backend.ingestion import IngestionGuard
    sent = []

    async def forbidden(*args):
        raise AssertionError("Unauthorized browser upload must not be read")

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/frame", "scheme": "https", "server": ("testserver", 443), "query_string": b"", "headers": [(b"x-session-token", b"invalid")]}
    asyncio.run(IngestionGuard(forbidden, protected_settings, session_auth=SessionAuth(protected_settings, Clock().epoch))(scope, forbidden, send))
    assert sent[0]["status"] == 401
