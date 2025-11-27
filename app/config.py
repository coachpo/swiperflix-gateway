from __future__ import annotations

from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for OpenList integration, loaded from environment.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPENLIST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_base_url: str = Field(default="http://localhost:5244", description="OpenList API base URL")
    dir_path: str = Field(default="/", description="Directory to list")
    password: str | None = Field(default=None, description="Directory password, if set")
    token: str | None = Field(default=None, description="OpenList token (raw, no Bearer)")
    username: str | None = Field(default=None, description="Basic auth username")
    user_password: str | None = Field(default=None, description="Basic auth password")
    public_base_url: str | None = Field(default=None, description="Base URL to build file links")
    gateway_base_url: str | None = Field(default=None, description="Optional proxy base for responses")

    def build_file_url(self, path: str) -> str:
        base = (self.public_base_url or self.api_base_url).rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        encoded = "/".join(quote(seg, safe="") for seg in path.lstrip("/").split("/"))
        return f"{base}/{encoded}"


# Singleton settings instance; update values here or patch in code/tests if needed.
settings = Settings()


def get_settings() -> Settings:
    return settings
