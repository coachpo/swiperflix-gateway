from __future__ import annotations

import logging
from typing import Any, List

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OpenListClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _new_client(self) -> httpx.Client:
        headers = {}
        auth = None
        if self.settings.token:
            # OpenList expects raw token without Bearer prefix
            headers["Authorization"] = self.settings.token
        if self.settings.username and self.settings.user_password and not self.settings.token:
            auth = (self.settings.username, self.settings.user_password)
        return httpx.Client(
            base_url=self.settings.api_base_url,
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def authenticate(self) -> str:
        if not (self.settings.username and self.settings.user_password):
            raise RuntimeError("No username/password configured for OpenList login")
        payload = {
            "username": self.settings.username,
            "password": self.settings.user_password,
            "otp_code": "",
        }
        with httpx.Client(base_url=self.settings.api_base_url, timeout=15) as client:
            resp = client.post("/api/auth/login", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                raise RuntimeError(f"OpenList login failed: {data}")
            token = data.get("data", {}).get("token")
            if not token:
                raise RuntimeError("OpenList login did not return token")
            # update settings so subsequent requests use it
            self.settings.token = token
            logger.info("OpenList login obtained token=%s", token)
            return token

    def fetch_files(self) -> list[dict[str, Any]]:
        """Calls POST /api/fs/list to list entries under configured dir_path."""
        payload = {
            "path": self.settings.dir_path,
            "password": self.settings.password or "",
            "refresh": False,
            "page": 1,
            "per_page": 50,
        }
        client = self._new_client()
        try:
            resp = client.post("/api/fs/list", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("OpenList /api/fs/list timed out") from exc
        if data.get("code") != 200:
            # token invalid; try to re-auth with username/password if available
            if data.get("code") == 401 and (self.settings.username and self.settings.user_password):
                if self.settings.token:
                    logger.warning("OpenList token rejected; token=%s", self.settings.token)
                self.authenticate()
                client = self._new_client()
                resp = client.post("/api/fs/list", json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 200:
                    raise RuntimeError(f"OpenList error after re-auth: {data}")
            else:
                raise RuntimeError(f"OpenList error: {data}")
        payload_data = data.get("data") or []
        # fs/list can return {content: [...], total: n} or a bare array
        if isinstance(payload_data, dict) and "content" in payload_data:
            entries = payload_data.get("content") or []
        else:
            entries = payload_data
        return entries

    def normalize_entry(self, entry: dict[str, Any] | str) -> dict[str, Any] | None:
        """
        Convert an OpenList fs entry to a video record dict expected by our DB.
        Returns None for invalid entries.
        """
        if isinstance(entry, str):
            name = entry
            modified = None
        else:
            name = entry.get("name")
            modified = entry.get("modified")
        if not name:
            return None
        base_path = self.settings.dir_path.rstrip("/")
        path = f"{base_path}/{name}" if base_path else f"/{name}"
        source_url = self.settings.build_file_url(path)
        created_at = modified
        return {
            "path": path.lstrip("/"),
            "source_url": source_url,
            "title": name,
            "cover": None,
            "duration": None,
            "orientation": None,
            "created_at": created_at,
        }

    def build_video_records(self, entries: List[dict[str, Any] | str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for entry in entries:
            norm = self.normalize_entry(entry)
            if norm:
                records.append(norm)
        return records
