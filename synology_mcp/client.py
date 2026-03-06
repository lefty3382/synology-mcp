"""Synology DSM client wrapper for multi-NAS management."""

import aiohttp
from synology_dsm import SynologyDSM

from .config import NasConfig


class SynologyClient:
    """Manages SynologyDSM connections to multiple NAS units."""

    def __init__(self) -> None:
        self._clients: dict[str, SynologyDSM] = {}
        self._configs: dict[str, NasConfig] = {}
        self._session: aiohttp.ClientSession | None = None

    async def connect(self, configs: list[NasConfig]) -> None:
        """Initialize connections to all configured NAS units."""
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False)
        )
        for config in configs:
            self._configs[config.name] = config
            api = SynologyDSM(
                self._session,
                config.host,
                config.port,
                config.username,
                config.password,
                use_https=config.use_https,
            )
            try:
                await api.login()
                self._clients[config.name] = api
                print(f"Connected to {config.name} ({config.host})")
            except Exception as e:
                print(f"Failed to connect to {config.name} ({config.host}): {e}")

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._clients.clear()

    def get_client(self, name: str) -> SynologyDSM | None:
        """Get a specific NAS client by name."""
        return self._clients.get(name.lower())

    def get_clients(self, nas: str | None = None) -> dict[str, SynologyDSM]:
        """Get clients filtered by NAS name, or all if None."""
        if nas:
            name = nas.lower()
            client = self._clients.get(name)
            return {name: client} if client else {}
        return dict(self._clients)

    @property
    def names(self) -> list[str]:
        """List of configured NAS names."""
        return list(self._configs.keys())

    def is_connected(self, name: str) -> bool:
        """Check if a NAS is connected."""
        return name in self._clients
