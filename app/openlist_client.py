from __future__ import annotations

from typing import Any, List

import httpx

from app.config import Settings


class OpenListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {}
        auth = None
        if settings.token:
            headers["Authorization"] = f"Bearer {settings.token}"
        if settings.username and settings.user_password:
            auth = (settings.username, settings.user_password)
        self.client = httpx.Client(base_url=settings.api_base_url, headers=headers, auth=auth, timeout=15)

    def fetch_files(self) -> list[dict[str, Any]]:
        """Calls POST /api/fs/dirs to list entries under configured dir_path."""
        payload = {
            "path": self.settings.dir_path,
            "password": self.settings.password or "",
            "force_root": False,
        }
        resp = self.client.post("/api/fs/dirs", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"OpenList error: {data}")
        entries = data.get("data") or []
        return entries

    def normalize_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """
        Convert an OpenList fs entry to a video record dict expected by our DB.
        Returns None for invalid entries.
        """
        name = entry.get("name")
        if not name:
            return None
        base_path = self.settings.dir_path.rstrip("/")
        path = f"{base_path}/{name}" if base_path else f"/{name}"
        url = self.settings.build_file_url(path)
        created_at = entry.get("modified")
        return {
            "id": path.lstrip("/"),
            "url": url,
            "title": name,
            "cover": None,
            "duration": None,
            "orientation": None,
            "created_at": created_at,
        }

    def build_video_records(self, entries: List[dict[str, Any]]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for entry in entries:
            norm = self.normalize_entry(entry)
            if norm:
                records.append(norm)
        return records
