"""Diagnostic tools for inspecting DSM API capabilities."""

from fastmcp import FastMCP

from ..client import SynologyClient


def register_diagnostic_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register diagnostic tools for API discovery."""

    @mcp.tool
    async def discover_apis(nas: str | None = None) -> dict:
        """List all SYNO.* API endpoints available on NAS unit(s).

        Returns the full API map from SYNO.API.Info including each API's
        CGI path, min/max version, and request format. Useful for discovering
        what endpoints a DSM installation supports.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            api_map = conn.get_api_map()
            results[name] = {
                "api_count": len(api_map),
                "apis": {
                    api_name: info
                    for api_name, info in sorted(api_map.items())
                },
            }
        return results
