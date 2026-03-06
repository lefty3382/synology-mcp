"""Multi-NAS configuration from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass
class NasConfig:
    """Configuration for a single Synology NAS."""

    name: str
    host: str
    port: int
    username: str
    password: str
    use_https: bool = True


@dataclass
class AppConfig:
    """Application configuration."""

    nas_configs: list[NasConfig] = field(default_factory=list)
    port: int = 8485
    permission_tier: str = "health"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables.

        NAS units are discovered by scanning for SYNOLOGY_<NAME>_HOST variables.
        For example, SYNOLOGY_TANK_HOST, SYNOLOGY_TANK_PORT, etc.
        """
        configs: list[NasConfig] = []
        seen: set[str] = set()

        for key in os.environ:
            if key.startswith("SYNOLOGY_") and key.endswith("_HOST"):
                name = key[len("SYNOLOGY_"):-len("_HOST")].lower()
                if name in seen:
                    continue
                seen.add(name)
                prefix = f"SYNOLOGY_{name.upper()}"
                host = os.environ.get(f"{prefix}_HOST", "")
                if not host:
                    continue
                configs.append(NasConfig(
                    name=name,
                    host=host,
                    port=int(os.environ.get(f"{prefix}_PORT", "5001")),
                    username=os.environ.get(f"{prefix}_USERNAME", ""),
                    password=os.environ.get(f"{prefix}_PASSWORD", ""),
                    use_https=os.environ.get(f"{prefix}_USE_HTTPS", "true").lower() == "true",
                ))

        return cls(
            nas_configs=configs,
            port=int(os.environ.get("MCP_PORT", "8485")),
            permission_tier=os.environ.get("MCP_PERMISSION_TIER", "health"),
        )
