"""Device-scoped credentials, kept separate from camera and browser auth."""

from hmac import compare_digest

from starlette.datastructures import Headers

from .errors import BackendError


class ControllerAuth:
    def __init__(self, settings):
        self.settings = settings

    def authenticate(self, headers: Headers, expected_device: str | None = None) -> str:
        configured = self.settings.controller_sessions
        if not configured:
            raise BackendError(503, "controller_auth_unconfigured", "No controllers have been provisioned")
        token = headers.get("x-device-token", "")
        identity = None
        if self.settings.controller_tokens:
            for device_id, secret in self.settings.controller_tokens.items():
                if compare_digest(token.encode(), secret.get_secret_value().encode()):
                    identity = device_id
            if identity is None:
                raise BackendError(401, "unauthorized_device", "Valid device-specific authorization is required")
        elif self.settings.local_dev:
            identity = headers.get("x-device-id")
            if identity not in configured:
                raise BackendError(401, "unauthorized_device", "Local development requires a provisioned X-Device-ID")
        else:
            raise BackendError(401, "unauthorized_device", "Valid device-specific authorization is required")
        declared = headers.get("x-device-id")
        if (expected_device is not None and identity != expected_device) or (declared is not None and declared != identity):
            raise BackendError(403, "device_access_denied", "Device identity does not match its credential")
        return identity
