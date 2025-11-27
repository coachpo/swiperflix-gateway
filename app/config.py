from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    """
    Central configuration for OpenList integration.

    Edit the defaults below to point at your OpenList instance.
    """

    api_base_url: str = "http://192.168.31.177:5244/"
    dir_path: str = "/"
    password: str | None = None  # directory password, if set
    token: str | None = None # token if API requires auth
    username: str | None = "api"  # optional basic-auth username
    user_password: str | None = "Liqing@8888"  # optional basic-auth password
    public_base_url: str | None = None  # used to build direct file URLs

    def build_file_url(self, path: str) -> str:
        base = (self.public_base_url or self.api_base_url).rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"


# Singleton settings instance; update values here or patch in code/tests if needed.
settings = Settings()


def get_settings() -> Settings:
    return settings
