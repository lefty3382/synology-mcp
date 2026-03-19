"""Power management tools for Synology NAS (write tier)."""

from fastmcp import FastMCP

from ..client import SynologyClient


def register_power_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register power management tools (shutdown, reboot)."""

    @mcp.tool
    async def shutdown_nas(nas: str, confirm: bool = False) -> dict:
        """Gracefully shut down a Synology NAS.

        This initiates a clean shutdown of the specified NAS unit.
        All services, file transfers, and connections will be terminated.
        The NAS must be physically powered on or woken via WoL to recover.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). Required — cannot
                 shut down all NAS units at once.
            confirm: Safety gate. Must be True to execute. When False,
                     returns a preview of what will happen.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        connections = client.direct.get_connections(nas)
        if not connections:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        conn = connections[name]

        if not confirm:
            return {
                "preview": True,
                "action": "shutdown",
                "nas": name,
                "warning": (
                    f"This will gracefully shut down '{name}'. "
                    "All services and connections will be terminated. "
                    "The NAS must be physically powered on or woken via WoL to recover. "
                    "Set confirm=True to proceed."
                ),
            }

        try:
            await conn.call("SYNO.Core.System", "shutdown", version=1)
            return {
                "success": True,
                "action": "shutdown",
                "nas": name,
                "message": f"Shutdown initiated for '{name}'. The NAS will power off shortly.",
            }
        except Exception as e:
            return {"error": str(e), "nas": name}

    @mcp.tool
    async def reboot_nas(nas: str, confirm: bool = False) -> dict:
        """Gracefully reboot a Synology NAS.

        This initiates a clean reboot of the specified NAS unit.
        All services and connections will be briefly interrupted
        during the restart (typically 3-5 minutes).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). Required — cannot
                 reboot all NAS units at once.
            confirm: Safety gate. Must be True to execute. When False,
                     returns a preview of what will happen.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        connections = client.direct.get_connections(nas)
        if not connections:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        conn = connections[name]

        if not confirm:
            return {
                "preview": True,
                "action": "reboot",
                "nas": name,
                "warning": (
                    f"This will gracefully reboot '{name}'. "
                    "All services and connections will be interrupted during restart "
                    "(typically 3-5 minutes). "
                    "Set confirm=True to proceed."
                ),
            }

        try:
            await conn.call("SYNO.Core.System", "reboot", version=1)
            return {
                "success": True,
                "action": "reboot",
                "nas": name,
                "message": f"Reboot initiated for '{name}'. The NAS will be back online in a few minutes.",
            }
        except Exception as e:
            return {"error": str(e), "nas": name}
