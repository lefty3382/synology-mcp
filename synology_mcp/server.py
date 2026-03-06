"""FastMCP server factory."""

from fastmcp import FastMCP

from .config import AppConfig
from .client import SynologyClient
from .tools.health import register_health_tools
from .tools.files_read import register_read_tools
from .tools.files_write import register_write_tools


def create_server(config: AppConfig, client: SynologyClient) -> FastMCP:
    """Create and configure the FastMCP server with tools based on permission tier."""
    mcp = FastMCP(
        "Synology MCP Server",
        instructions=(
            "Provides read-only access to Synology NAS health, storage, "
            "and system information. Query one or all configured NAS units."
        ),
    )

    # Health tier — always registered
    register_health_tools(mcp, client)

    # Read tier — file browsing
    if config.permission_tier in ("read", "write"):
        register_read_tools(mcp, client)

    # Write tier — file mutations
    if config.permission_tier == "write":
        register_write_tools(mcp, client)

    return mcp
