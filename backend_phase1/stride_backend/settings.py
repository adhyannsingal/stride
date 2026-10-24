"""Environment configuration; defaults require an ingestion secret."""

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

    @model_validator(mode="after")
    def require_secret(self) -> "Settings":
        token = self.device_token.get_secret_value() if self.device_token else ""
        if not self.local_dev and not token.strip():
            raise ValueError("Set STRIDE_DEVICE_TOKEN or explicitly enable STRIDE_LOCAL_DEV")
        return self
