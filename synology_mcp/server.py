"""FastMCP server factory."""

from fastmcp import FastMCP

from .config import AppConfig
from .client import SynologyClient
from .tools.health import register_health_tools
from .tools.diagnostic import register_diagnostic_tools
from .tools.files_read import register_read_tools
from .tools.files_write import register_write_tools
from .tools.power import register_power_tools


def create_server(config: AppConfig, client: SynologyClient) -> FastMCP:
    """Create and configure the FastMCP server with tools based on permission tier."""
    tier = config.permission_tier

    if tier == "write":
        desc = (
            "Provides full access to Synology NAS: health monitoring, "
            "storage diagnostics, file browsing, file management, and power management. "
            "Query one or all configured NAS units."
        )
    elif tier == "read":
        desc = (
            "Provides read access to Synology NAS: health monitoring, "
            "storage diagnostics, and file browsing. "
            "Query one or all configured NAS units."
        )
    else:
        desc = (
            "Provides read-only access to Synology NAS health, storage, "
            "and system information. Query one or all configured NAS units."
        )

    mcp = FastMCP("Synology MCP Server", instructions=desc)

    # Health tier — always registered
    register_health_tools(mcp, client)
    register_diagnostic_tools(mcp, client)

    # Read tier — file browsing
    if tier in ("read", "write"):
        register_read_tools(mcp, client)

    # Write tier — file mutations + power management
    if tier == "write":
        register_write_tools(mcp, client)
        register_power_tools(mcp, client)

    return mcp
