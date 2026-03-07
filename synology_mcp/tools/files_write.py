"""File mutation tools for Synology NAS (write tier)."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import SynologyClient


def register_write_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register file writing/mutation tools (write tier)."""

    @mcp.tool
    async def create_folder(
        nas: str,
        path: str,
        name: str,
        create_parents: bool = True,
    ) -> dict:
        """Create a new directory on the NAS.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Parent directory path (e.g., '/volume1/Storage/Film/Anime').
            name: Name of the new folder to create.
            create_parents: Create intermediate directories if missing (default: True).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        nas_name = nas.lower()
        c = conn[nas_name]

        try:
            data = await c.call(
                "SYNO.FileStation.CreateFolder",
                "create",
                version=2,
                folder_path=path,
                name=name,
                force_parent=str(create_parents).lower(),
            )
            folders = data.get("folders", [])
            if folders:
                created = folders[0]
                return {
                    nas_name: {
                        "success": True,
                        "name": created.get("name"),
                        "path": created.get("path"),
                    }
                }
            return {nas_name: {"success": True, "path": f"{path}/{name}"}}
        except Exception as e:
            return {nas_name: {"error": str(e)}}

    @mcp.tool
    async def rename(nas: str, path: str, new_name: str) -> dict:
        """Rename a file or folder on the NAS.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Current absolute path of the file or folder.
            new_name: New name (just the filename, not a full path).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        nas_name = nas.lower()
        c = conn[nas_name]

        try:
            data = await c.call(
                "SYNO.FileStation.Rename",
                "rename",
                version=2,
                path=path,
                name=new_name,
                additional='["size","time"]',
            )
            files = data.get("files", [])
            if files:
                f = files[0]
                additional = f.get("additional", {})
                return {
                    nas_name: {
                        "success": True,
                        "old_path": path,
                        "new_path": f.get("path"),
                        "name": f.get("name"),
                        "size": additional.get("size"),
                    }
                }
            return {nas_name: {"success": True, "old_path": path, "new_name": new_name}}
        except Exception as e:
            return {nas_name: {"error": str(e)}}
