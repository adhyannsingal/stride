"""Bound small controller JSON requests before FastAPI reads/parses the body."""

from starlette.datastructures import Headers

from .errors import BackendError, error_response


class ControllerBodyGuard:
    def __init__(self, app, settings, controller_auth, clock, epoch_clock):
        self.app, self.settings, self.auth = app, settings, controller_auth
        self.clock, self.epoch = clock, epoch_clock

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root = scope.get("root_path", "").rstrip("/")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        device_post = path in {"/telemetry", "/device/telemetry", "/device/ack"} or (path.startswith("/devices/") and path.endswith("/ack"))
        if scope["type"] != "http" or scope.get("method") != "POST" or not (device_post or path == "/device/pair"):
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        try:
            if device_post:
                scope["stride.controller_id"] = self.auth.authenticate(headers)
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise BackendError(415, "unsupported_media_type", "Use application/json")
            length = headers.get("content-length")
            if length is not None:
                try:
                    number = int(length)
                    if number < 0:
                        raise ValueError
                except ValueError:
                    raise BackendError(400, "invalid_content_length", "Invalid Content-Length") from None
                if number > self.settings.max_controller_payload_bytes:
                    raise BackendError(413, "controller_payload_too_large", "Controller JSON exceeds the byte limit")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > self.settings.max_controller_payload_bytes:
                    raise BackendError(413, "controller_payload_too_large", "Controller JSON exceeds the byte limit")
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
        except BackendError as exc:
            return await error_response(exc.status_code, exc.code, exc.message)(scope, receive, send)
        scope["stride.controller_received_ms"] = self.epoch()
        scope["stride.controller_received_mono"] = self.clock()
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, buffered_receive, send)
