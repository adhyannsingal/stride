"""Authenticate and bound the entire multipart body before parsing any files."""

from hmac import compare_digest

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import BackendError, error_response
from .settings import Settings
from .store import epoch_ms, monotonic_ms

MULTIPART_OVERHEAD_BYTES = 16 * 1024


class IngestionGuard:
    def __init__(self, app: ASGIApp, settings: Settings, clock=monotonic_ms, epoch_clock=epoch_ms, session_auth=None):
        self.app = app
        self.settings = settings
        self.clock = clock
        self.epoch_clock = epoch_clock
        self.session_auth = session_auth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if scope["type"] != "http" or path != "/frame" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        expected = self.settings.device_token.get_secret_value() if self.settings.device_token else ""
        provided = headers.get("x-device-token", "")
        device_authorized = bool(expected and compare_digest(provided.encode(), expected.encode()))
        browser_credentials = headers.get("x-session-token") is not None or "stride_session=" in headers.get("cookie", "")
        if not device_authorized and not provided and browser_credentials and self.session_auth:
            try:
                scope["stride.authorized_session_id"] = self.session_auth.upload_session(Request(scope))
            except BackendError as exc:
                await error_response(exc.status_code, exc.code, exc.message)(scope, receive, send)
                return
        elif not device_authorized and (expected or provided):
            await error_response(401, "unauthorized", "A valid X-Device-Token header is required")(scope, receive, send)
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "multipart/form-data":
            await error_response(415, "unsupported_media_type", "Use multipart/form-data with a JPEG file")(scope, receive, send)
            return

        limit = self.settings.max_frame_bytes + MULTIPART_OVERHEAD_BYTES
        length = headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                await error_response(400, "invalid_content_length", "Invalid Content-Length")(scope, receive, send)
                return
            if size > limit:
                await error_response(413, "frame_too_large", "Upload exceeds the configured request size limit")(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await error_response(413, "frame_too_large", "Upload exceeds the configured request size limit")(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        scope["stride.received_ms"] = self.epoch_clock()
        scope["stride.received_monotonic_ms"] = self.clock()
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
