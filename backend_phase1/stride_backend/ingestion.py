"""Authenticate and bound the entire multipart body before parsing any files."""

from hmac import compare_digest
from time import time_ns

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import error_response
from .settings import Settings
from .store import monotonic_ms

MULTIPART_OVERHEAD_BYTES = 16 * 1024


class IngestionGuard:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

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
        if expected and not compare_digest(provided.encode(), expected.encode()):
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
        scope["stride.received_ms"] = time_ns() // 1_000_000
        scope["stride.received_monotonic_ms"] = monotonic_ms()
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
