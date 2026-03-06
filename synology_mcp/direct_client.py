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
