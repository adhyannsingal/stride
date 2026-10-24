"""Small, session-scoped credential exchange; camera secrets are never UI auth."""

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable

from fastapi import Request, Response

from .errors import BackendError
from .models import SessionAuthResponse, SessionCredentials
from .settings import Settings

COOKIE_NAME = "stride_session"


class SessionAuth:
    def __init__(self, settings: Settings, epoch_ms: Callable[[], int]):
        self.settings = settings
        self.epoch_ms = epoch_ms

    def check_origin(self, request: Request) -> None:
        origin = request.headers.get("origin")
        same_origin = f"{request.url.scheme}://{request.url.netloc}"
        if origin is not None and origin not in {same_origin, *self.settings.frontend_origins}:
            raise BackendError(403, "origin_denied", "Browser origin is not allowed")

    def _secret(self, session_id: str) -> str:
        if not self.settings.session_tokens:
            raise BackendError(503, "session_auth_unconfigured", "Session credentials have not been provisioned")
        value = self.settings.session_tokens.get(session_id)
        if value is None:
            raise BackendError(403, "session_access_denied", "Access to this session is denied")
        return value.get_secret_value()

    @staticmethod
    def _signature(payload: str, secret: str) -> str:
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def authorize(self, request: Request, session_id: str) -> None:
        self.check_origin(request)
        if self.settings.local_dev and not self.settings.session_tokens:
            return
        secret = self._secret(session_id)
        header = request.headers.get("x-session-token")
        if header is not None:
            if hmac.compare_digest(header.encode(), secret.encode()):
                return
            raise BackendError(401, "unauthorized", "Valid session authorization is required")
        cookie = request.cookies.get(COOKIE_NAME, "")
        try:
            payload, signature = cookie.split(".", 1)
            if not hmac.compare_digest(signature, self._signature(payload, secret)):
                raise ValueError
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if data["session_id"] != session_id:
                raise ValueError
            if type(data["expires_ms"]) is not int or data["expires_ms"] <= self.epoch_ms():
                raise ValueError
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            raise BackendError(401, "unauthorized", "Valid session authorization is required") from None

    def upload_session(self, request: Request) -> str:
        """Authenticate a browser before reading its multipart body.

        The frame route subsequently verifies that multipart session_id matches
        this authenticated identity. This never grants the device's global scope.
        """
        header = request.headers.get("x-session-token")
        if header is not None:
            for session_id, secret in self.settings.session_tokens.items():
                if hmac.compare_digest(header.encode(), secret.get_secret_value().encode()):
                    self.authorize(request, session_id)
                    return session_id
        else:
            cookie = request.cookies.get(COOKIE_NAME, "")
            try:
                if len(cookie) > 4096:
                    raise ValueError
                payload = cookie.split(".", 1)[0]
                data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
                session_id = data["session_id"]
                if not isinstance(session_id, str) or not 0 < len(session_id) <= 128:
                    raise ValueError
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                raise BackendError(401, "unauthorized", "Valid session authorization is required") from None
            self.authorize(request, session_id)
            return session_id
        raise BackendError(401, "unauthorized", "Valid session authorization is required")

    def login(self, request: Request, response: Response, credentials: SessionCredentials) -> SessionAuthResponse:
        self.check_origin(request)
        secret = self._secret(credentials.session_id)
        if not hmac.compare_digest(credentials.session_token.get_secret_value().encode(), secret.encode()):
            raise BackendError(401, "unauthorized", "Valid session authorization is required")
        expires = self.epoch_ms() + self.settings.session_cookie_ttl_seconds * 1000
        data = {"session_id": credentials.session_id, "expires_ms": expires, "nonce": secrets.token_hex(16)}
        payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()
        response.set_cookie(
            COOKIE_NAME, f"{payload}.{self._signature(payload, secret)}",
            httponly=True, secure=not self.settings.local_dev, samesite="strict",
            max_age=self.settings.session_cookie_ttl_seconds,
            path=(request.scope.get("root_path", "").rstrip("/") or "/"),
        )
        response.headers["Cache-Control"] = "no-store"
        return SessionAuthResponse(session_id=credentials.session_id, expires_ms=expires)
