"""Environment configuration; defaults require an ingestion secret."""

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STRIDE_", env_file=".env", extra="ignore", frozen=True,
        hide_input_in_errors=True,
    )

    device_token: SecretStr | None = Field(default=None, repr=False)
    local_dev: bool = False
    max_frame_bytes: int = Field(default=524288, gt=0)
    max_image_pixels: int = Field(default=4000000, gt=0)
    max_sessions: int = Field(default=8, gt=0)
    max_streams_per_session: int = Field(default=16, gt=0)
    session_ttl_ms: int = Field(default=300000, gt=0)
    frame_freshness_ms: int = Field(default=1000, gt=0, le=1000)
    session_tokens: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    session_cookie_ttl_seconds: int = Field(default=3600, gt=0, le=86400)
    frontend_origins: tuple[str, ...] = ()
    detector_factory: str | None = None
    inference_workers: int = Field(default=1, gt=0, le=8)
    inference_timeout_ms: int = Field(default=1000, gt=0, le=10000)
    worker_shutdown_grace_ms: int = Field(default=250, ge=0, le=5000)
    max_actions_per_session: int = Field(default=128, gt=0, le=4096)
    max_speech_events_per_generation: int = Field(default=256, gt=0, le=4096)

    @model_validator(mode="after")
    def require_secret(self) -> "Settings":
        token = self.device_token.get_secret_value() if self.device_token else ""
        if not self.local_dev and not token.strip():
            raise ValueError("Set STRIDE_DEVICE_TOKEN or explicitly enable STRIDE_LOCAL_DEV")
        if len(self.session_tokens) > self.max_sessions:
            raise ValueError("Session token count exceeds STRIDE_MAX_SESSIONS")
        values = [secret.get_secret_value() for secret in self.session_tokens.values()]
        if any(not value.strip() for value in values) or len(values) != len(set(values)):
            raise ValueError("Session tokens must be nonempty and unique")
        if token and token in values:
            raise ValueError("Session tokens must differ from the camera device token")
        if any(not name.strip() or len(name) > 128 or name != name.strip() for name in self.session_tokens):
            raise ValueError("Session token keys must be nonempty identifiers of at most 128 characters")
        for origin in self.frontend_origins:
            parsed = urlsplit(origin)
            if "*" in origin or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Frontend origins must be exact http(s) origins without wildcards or paths")
        return self
