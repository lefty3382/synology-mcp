"""File mutation tools for Synology NAS (write tier)."""

from fastmcp import FastMCP

from ..client import SynologyClient


def register_write_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register file writing tools."""

    @mcp.tool
    async def upload_file(path: str, filename: str, content: str, nas: str) -> dict:
        """Upload a text file to the NAS.

        Args:
            path: Target directory (e.g., '/volume1/share')
            filename: Name for the file
            content: Text content to upload
            nas: NAS name (e.g., 'tank' or 'dozer')
        """
        api = client.get_client(nas)
        if not api:
            return {"error": f"NAS '{nas}' not found or not connected"}
        try:
            result = await api.file.upload_file(path, filename, content.encode())
            return {"success": bool(result), "path": f"{path}/{filename}", "nas": nas}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool
    async def delete_file(path: str, filename: str, nas: str) -> dict:
        """Delete a file on the NAS.

        Args:
            path: Directory containing the file (e.g., '/volume1/share')
            filename: Name of the file to delete
            nas: NAS name (e.g., 'tank' or 'dozer')
        """
        api = client.get_client(nas)
        if not api:
            return {"error": f"NAS '{nas}' not found or not connected"}
        try:
            result = await api.file.delete_file(path, filename)
            return {"success": bool(result), "deleted": f"{path}/{filename}", "nas": nas}
        except Exception as e:
            return {"error": str(e)}
