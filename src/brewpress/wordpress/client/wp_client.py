"""WordPress REST API client — single source of truth for HTTP communication.

Features:
- Application Password auth via requests.Session
- Retry on ConnectionError/Timeout with exponential backoff
- No retry on 4xx errors
- User-Agent: brewpress-wordpress-agent/1.0
"""
from __future__ import annotations

import time
from typing import Any

import requests


class WPClient:
    """Low-level WordPress REST API client.

    Args:
        base_url:    WordPress site base URL (trailing slash stripped internally).
        auth:        Tuple of (username, application_password).
                     IMPORTANT: Do not strip the password — spaces are significant.
        timeout:     Request timeout in seconds (default 30).
        max_retries: Max retry attempts on connection errors (default 3).
    """

    _USER_AGENT = "brewpress-wordpress-agent/1.0"
    _API_PREFIX = "/wp-json/wp/v2"

    def __init__(
        self,
        base_url: str,
        auth: tuple[str, str],
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._session = requests.Session()
        self._session.auth = auth
        self._session.headers.update({
            "User-Agent": self._USER_AGENT,
            "Accept": "application/json",
        })

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}{self._API_PREFIX}/{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Execute an HTTP request with retry on transient errors.

        Retries on ConnectionError and Timeout with exponential backoff.
        Does NOT retry on 4xx or 5xx HTTP responses.
        """
        url = self._url(path)
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    files=files,
                    headers=headers,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(0.5 * (2 ** attempt))  # 0.5s, 1s before retries
            except requests.HTTPError:
                raise  # never retry on HTTP errors (4xx/5xx)

        raise last_exc  # type: ignore[misc]

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._request("POST", path, json=json, files=files, headers=headers)

    def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json=json)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", path, params=params)
