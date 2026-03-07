"""Direct DSM API client for endpoints not covered by py-synologydsm-api."""

import time
from typing import Any

import aiohttp

from .config import NasConfig


class DirectApiClient:
    """Lightweight HTTP client for raw SYNO.* API calls."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._connections: dict[str, _NasConnection] = {}

    async def connect(self, config: NasConfig) -> None:
        """Authenticate to a NAS and discover available APIs."""
        conn = _NasConnection(config, self._session)
        await conn.login()
        await conn.discover()
        self._connections[config.name] = conn

    def get_connections(
        self, nas: str | None = None
    ) -> dict[str, "_NasConnection"]:
        """Get connections filtered by NAS name, or all if None."""
        if nas:
            name = nas.lower()
            conn = self._connections.get(name)
            return {name: conn} if conn else {}
        return dict(self._connections)

    async def poll_task(
        self,
        nas: str,
        api: str,
        task_id: str,
        poll_method: str = "status",
        timeout: int = 60,
        interval: float = 1.5,
    ) -> dict:
        """Poll an async task on a specific NAS."""
        conn = self._connections.get(nas.lower())
        if not conn:
            return {"error": f"NAS '{nas}' not connected"}
        return await conn.poll_task(api, task_id, poll_method, timeout, interval)

    async def download(
        self, nas: str, path: str, max_size: int = 1_048_576
    ) -> bytes:
        """Download a file from a specific NAS."""
        conn = self._connections.get(nas.lower())
        if not conn:
            raise RuntimeError(f"NAS '{nas}' not connected")
        return await conn.download(path, max_size)


class _NasConnection:
    """Single NAS connection with auth session and API map."""

    _CACHE_TTL = 30  # seconds

    def __init__(
        self, config: NasConfig, session: aiohttp.ClientSession
    ) -> None:
        self._config = config
        self._session = session
        self._sid: str | None = None
        self._api_map: dict[str, dict[str, Any]] = {}
        self._cache: dict[str, tuple[float, Any]] = {}

    @property
    def _base_url(self) -> str:
        scheme = "https" if self._config.use_https else "http"
        return f"{scheme}://{self._config.host}:{self._config.port}"

    async def login(self) -> None:
        """Authenticate and obtain session ID."""
        url = f"{self._base_url}/webapi/auth.cgi"
        params = {
            "api": "SYNO.API.Auth",
            "version": "6",
            "method": "login",
            "account": self._config.username,
            "passwd": self._config.password,
            "format": "sid",
        }
        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
        if not data.get("success"):
            raise ConnectionError(
                f"Auth failed for {self._config.name}: {data}"
            )
        self._sid = data["data"]["sid"]

    async def discover(self) -> None:
        """Query SYNO.API.Info to build API-to-CGI-path map."""
        url = f"{self._base_url}/webapi/query.cgi"
        params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": "ALL",
        }
        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("success"):
            self._api_map = data["data"]

    async def call(
        self,
        api: str,
        method: str,
        version: int = 1,
        cache_key: str | None = None,
        **params: Any,
    ) -> dict:
        """Call a SYNO.* API endpoint. Returns the 'data' dict."""
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < self._CACHE_TTL:
                return cached[1]

        result = await self._raw_call(api, method, version, **params)

        # Retry once on session expiry (error 119)
        if not result.get("success") and result.get("error", {}).get("code") == 119:
            await self.login()
            result = await self._raw_call(api, method, version, **params)

        if not result.get("success"):
            raise RuntimeError(
                f"API call failed: {api}.{method} -> {result}"
            )

        data = result.get("data", {})
        if cache_key:
            self._cache[cache_key] = (time.monotonic(), data)
        return data

    async def poll_task(
        self,
        api: str,
        task_id: str,
        poll_method: str = "status",
        timeout: int = 60,
        interval: float = 1.5,
    ) -> dict:
        """Poll an async FileStation task until completion or timeout.

        Args:
            api: The SYNO.FileStation.* API that started the task.
            task_id: The taskid returned by the start method.
            poll_method: Method name for status check (default: 'status').
            timeout: Max seconds to wait (default: 60).
            interval: Seconds between polls (default: 1.5).

        Returns:
            The final status response data dict. Includes 'timeout': True
            if the task did not complete within the timeout.
        """
        import asyncio as _asyncio

        start = time.monotonic()
        result = {}
        while (time.monotonic() - start) < timeout:
            result = await self.call(api, poll_method, version=2, taskid=task_id)
            if result.get("finished"):
                # Clean up the task
                try:
                    await self.call(api, "stop", version=2, taskid=task_id)
                except Exception:
                    pass  # Best-effort cleanup
                return result
            await _asyncio.sleep(interval)

        # Timeout — return partial result with flag
        result["timeout"] = True
        result["task_id"] = task_id
        try:
            await self.call(api, "stop", version=2, taskid=task_id)
        except Exception:
            pass
        return result

    async def download(
        self,
        path: str,
        max_size: int = 1_048_576,
    ) -> bytes:
        """Download a file's raw bytes via SYNO.FileStation.Download.

        Args:
            path: Absolute file path on the NAS.
            max_size: Maximum allowed file size in bytes (default 1 MB).

        Returns:
            Raw file bytes.

        Raises:
            ValueError: If file exceeds max_size.
            RuntimeError: If download fails.
        """
        api_info = self._api_map.get("SYNO.FileStation.Download", {})
        cgi_path = api_info.get("path", "entry.cgi")

        url = f"{self._base_url}/webapi/{cgi_path}"
        params = {
            "api": "SYNO.FileStation.Download",
            "version": "2",
            "method": "download",
            "path": path,
            "mode": "download",
            "_sid": self._sid,
        }
        async with self._session.get(url, params=params) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # If JSON response, it's an error
            if "application/json" in content_type:
                data = await resp.json()
                raise RuntimeError(f"Download failed: {data}")
            # If HTML response, it's a DSM error page (e.g., file not found)
            if "text/html" in content_type:
                raise RuntimeError(f"Download failed: file not found or access denied (path: {path})")
            # Check size before reading full body
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_size:
                raise ValueError(
                    f"File size {int(content_length)} bytes exceeds "
                    f"max_size {max_size} bytes"
                )
            body = await resp.read()
            if len(body) > max_size:
                raise ValueError(
                    f"File size {len(body)} bytes exceeds "
                    f"max_size {max_size} bytes"
                )
            return body

    async def _raw_call(
        self,
        api: str,
        method: str,
        version: int,
        **params: Any,
    ) -> dict:
        """Execute raw HTTP call to DSM API."""
        api_info = self._api_map.get(api, {})
        cgi_path = api_info.get("path", "entry.cgi")

        url = f"{self._base_url}/webapi/{cgi_path}"
        query = {
            "api": api,
            "version": str(version),
            "method": method,
            "_sid": self._sid,
            **{k: str(v) for k, v in params.items()},
        }
        async with self._session.get(url, params=query) as resp:
            return await resp.json()

    def get_api_map(self) -> dict[str, dict[str, Any]]:
        """Return the discovered API map."""
        return dict(self._api_map)
