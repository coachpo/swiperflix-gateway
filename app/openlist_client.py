from __future__ import annotations

import logging
from typing import Any, List

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OpenListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: httpx.Client | None = None

    def _new_client(self) -> httpx.Client:
        headers, auth = self._build_auth()
        if self._client and not self._client.is_closed:
            self._client.headers.update(headers)
            self._client.auth = auth
            return self._client
        self._client = httpx.Client(
            base_url=self.settings.api_base_url,
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        return self._client

    def _build_auth(self) -> tuple[dict[str, str], httpx._types.AuthTypes | None]:
        headers: dict[str, str] = {}
        auth = None
        if self.settings.token:
            # OpenList expects raw token without Bearer prefix
            headers["Authorization"] = self.settings.token
        if self.settings.username and self.settings.user_password and not self.settings.token:
            auth = (self.settings.username, self.settings.user_password)
        return headers, auth

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
            if self._client and not self._client.is_closed:
                self._client.headers.update({"Authorization": token})
                self._client.auth = None
            return token

    def fetch_files(self, all_pages: bool = False) -> list[dict[str, Any]]:
        """Calls POST /api/fs/list to list entries. If all_pages is True, paginates until exhausted."""
        payload_base = {
            "path": self.settings.dir_path,
            "password": self.settings.password or "",
            "refresh": False,
            "per_page": 50,
        }

        def fetch_page(page: int, auth_retry: bool = True) -> dict[str, Any]:
            payload = dict(payload_base, page=page)
            client = self._new_client()
            try:
                resp = client.post("/api/fs/list", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except httpx.TimeoutException as exc:
                raise RuntimeError("OpenList /api/fs/list timed out") from exc
            if data.get("code") != 200:
                if data.get("code") == 401 and auth_retry and (self.settings.username and self.settings.user_password):
                    if self.settings.token:
                        logger.warning("OpenList token rejected; token=%s", self.settings.token)
                    self.authenticate()
                    return fetch_page(page, auth_retry=False)
                raise RuntimeError(f"OpenList error: {data}")
            return data

        results: list[dict[str, Any]] = []
        page = 1
        while True:
            data = fetch_page(page)
            payload_data = data.get("data") or []

            total = None
            if isinstance(payload_data, dict):
                entries = payload_data.get("content") or []
                total = payload_data.get("total")
            else:
                entries = payload_data

            results.extend(entries or [])

            if not all_pages:
                return entries

            per_page = payload_base["per_page"]
            if total is not None:
                if len(results) >= total:
                    break
            if not entries or len(entries) < per_page:
                break
            page += 1

        return results

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

    def get_download_url(self, path: str) -> str:
        """
        Resolve a file's direct download URL using OpenList's file link endpoint.
        Example: /@file/link/path/path1/file1.mp4 for file /path1/file1.mp4
        """
        norm_path = path.lstrip("/")
        endpoint = f"/@file/link/path/{norm_path}"
        params = {}
        if self.settings.password:
            params["password"] = self.settings.password

        def call_link(auth_retry: bool = True):
            client = self._new_client()
            resp = client.get(endpoint, params=params, follow_redirects=False)
            if resp.status_code == 401 and auth_retry and (self.settings.username and self.settings.user_password):
                self.authenticate()
                return call_link(auth_retry=False)
            return resp

        resp = call_link()

        if resp.is_redirect:
            location = resp.headers.get("Location")
            if location:
                return location

        # Some deployments return a JSON envelope; others may stream or render HTML.
        if resp.headers.get("content-type", "").startswith("text/html"):
            # Fallback to API-based resolution below.
            return self._get_download_url_via_api(norm_path)

        try:
            data = resp.json()
        except Exception:
            # Fallback to API-based resolution; if that fails, surface this response.
            return self._get_download_url_via_api(norm_path)

        if isinstance(data, dict) and data.get("code") == 401 and (self.settings.username and self.settings.user_password):
            # Token invalid; re-auth and retry once.
            self.authenticate()
            resp = call_link(auth_retry=False)
            if resp.is_redirect:
                location = resp.headers.get("Location")
                if location:
                    return location
            try:
                data = resp.json()
            except Exception:
                return self._get_download_url_via_api(norm_path)

        # OpenList often returns {code:int, data:<url|string|dict>}
        if isinstance(data, dict):
            inner = data.get("data") if "data" in data else None
            if isinstance(inner, str) and inner:
                return inner
            if isinstance(inner, dict):
                for key in ("raw_url", "url", "download_url", "link", "proxy_url"):
                    val = inner.get(key)
                    if isinstance(val, str) and val:
                        return val
        if isinstance(data, str) and data:
            return data

        # Try API fallback before giving up.
        return self._get_download_url_via_api(norm_path)

    def _get_download_url_via_api(self, norm_path: str) -> str:
        """
        Fallback: use OpenList's fs/get API to resolve raw or proxy URL.
        """
        payload = {"path": f"/{norm_path}", "password": self.settings.password or ""}

        def call_get(auth_retry: bool = True):
            client = self._new_client()
            resp = client.post("/api/fs/get", json=payload)
            if resp.status_code == 401 and auth_retry and (self.settings.username and self.settings.user_password):
                self.authenticate()
                return call_get(auth_retry=False)
            return resp

        resp = call_get()
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"OpenList /api/fs/get response not JSON: {resp.text}") from exc

        # Some deployments return HTTP 200 with {code:401,...}
        if isinstance(data, dict) and data.get("code") == 401 and (self.settings.username and self.settings.user_password):
            self.authenticate()
            resp = call_get(auth_retry=False)
            data = resp.json()

        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected OpenList /api/fs/get response: {data}")

        inner = data.get("data") if "data" in data else None
        if isinstance(inner, dict):
            for key in ("raw_url", "proxy_url", "url", "download_url", "link"):
                val = inner.get(key)
                if isinstance(val, str) and val:
                    return val
        raise RuntimeError(f"OpenList /api/fs/get did not return download URL: {data}")


_singleton_client: OpenListClient | None = None


def get_openlist_client() -> OpenListClient:
    """
    Provide a singleton OpenListClient for reuse across handlers.
    """
    global _singleton_client
    if _singleton_client is None:
        _singleton_client = OpenListClient(get_settings())
    return _singleton_client
