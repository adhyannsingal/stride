"""Environment configuration; defaults require an ingestion secret."""

from urllib.parse import urlsplit
from pathlib import Path

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
    database_path: Path = Field(default=Path("data/stride.sqlite3"), repr=False)
    record_stable_sightings: bool = False
    load_demo_routes: bool = True
    guidance_ttl_ms: int = Field(default=10000, gt=0, le=60000)
    max_route_actions_per_session: int = Field(default=2048, gt=0, le=100000)
    max_sightings_per_session: int = Field(default=200, gt=0, le=10000)
    sighting_cooldown_ms: int = Field(default=30000, ge=0, le=3600000)
    controller_tokens: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    controller_sessions: dict[str, str] = Field(default_factory=dict)
    max_controllers: int = Field(default=8, gt=0, le=64)
    max_controller_payload_bytes: int = Field(default=4096, ge=512, le=65536)
    sensor_min_cm: float = Field(default=2, ge=0, allow_inf_nan=False)
    sensor_max_cm: float = Field(default=400, gt=0, allow_inf_nan=False)
    obstacle_danger_cm: float = Field(default=50, gt=0, allow_inf_nan=False)
    obstacle_caution_cm: float = Field(default=100, gt=0, allow_inf_nan=False)
    obstacle_hysteresis_cm: float = Field(default=5, ge=0, allow_inf_nan=False)
    obstacle_recovery_samples: int = Field(default=3, ge=1, le=20)
    telemetry_fresh_ms: int = Field(default=1000, gt=0, le=10000)
    controller_heartbeat_ms: int = Field(default=2000, gt=0, le=30000)
    controller_expected_hz: float = Field(default=5, gt=0, le=100, allow_inf_nan=False)
    device_monitor_interval_ms: int = Field(default=100, ge=20, le=1000)
    telemetry_history_per_device: int = Field(default=100, ge=1, le=10000)
    max_boots_per_device: int = Field(default=16, ge=1, le=1000)
    max_commands_per_device: int = Field(default=64, ge=1, le=1000)
    device_events_per_navigation: int = Field(default=128, ge=1, le=10000)
    haptic_ttl_ms: int = Field(default=1000, ge=50, le=1500)

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
        controller_values = [secret.get_secret_value() for secret in self.controller_tokens.values()]
        if len(self.controller_sessions) > self.max_controllers or len(set(self.controller_sessions.values())) != len(self.controller_sessions):
            raise ValueError("Use at most max_controllers, with one controller per authorized session")
        if self.controller_tokens and set(self.controller_tokens) != set(self.controller_sessions):
            raise ValueError("Controller credentials and allowed-session mappings must have matching device IDs")
        if not self.local_dev and self.controller_sessions and not self.controller_tokens:
            raise ValueError("Production controllers require device-specific credentials")
        if any(not x.strip() for x in controller_values) or len(set(controller_values)) != len(controller_values) or any(x == token or x in values for x in controller_values):
            raise ValueError("Controller credentials must be unique, nonempty and separate from camera/UI credentials")
        for device_id, session_id in self.controller_sessions.items():
            if any(not x.strip() or x != x.strip() or len(x) > 128 for x in (device_id, session_id)):
                raise ValueError("Controller/session IDs must be nonempty identifiers")
            if not self.local_dev and session_id not in self.session_tokens:
                raise ValueError("Controller mappings must reference provisioned UI sessions")
        if not self.sensor_min_cm < self.obstacle_danger_cm < self.obstacle_caution_cm < self.sensor_max_cm:
            raise ValueError("Require sensor_min < danger < caution < sensor_max")
        if self.obstacle_caution_cm + self.obstacle_hysteresis_cm >= self.sensor_max_cm:
            raise ValueError("Hysteresis must leave a supported clear recovery range")
        if any(not name.strip() or len(name) > 128 or name != name.strip() for name in self.session_tokens):
            raise ValueError("Session token keys must be nonempty identifiers of at most 128 characters")
        for origin in self.frontend_origins:
            parsed = urlsplit(origin)
            if "*" in origin or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Frontend origins must be exact http(s) origins without wildcards or paths")
        return self
