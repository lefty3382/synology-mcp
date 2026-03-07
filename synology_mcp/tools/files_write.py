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

    @mcp.tool
    async def move(
        nas: str,
        source_path: str | list[str],
        dest_path: str,
        overwrite: bool = False,
    ) -> dict:
        """Move files or folders to a new location on the same NAS.

        For large moves, this runs as an async task and polls for completion.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            source_path: Path or list of paths to move.
            dest_path: Destination directory path.
            overwrite: Overwrite existing files at destination (default: False).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        nas_name = nas.lower()
        c = conn[nas_name]

        # Normalize source to comma-separated string
        if isinstance(source_path, list):
            src = ",".join(source_path)
        else:
            src = source_path

        try:
            start_data = await c.call(
                "SYNO.FileStation.CopyMove",
                "start",
                version=3,
                path=src,
                dest_folder_path=dest_path,
                overwrite=str(overwrite).lower(),
                remove_src="true",
            )
            task_id = start_data.get("taskid")
            if not task_id:
                return {nas_name: {"error": "Failed to start move task"}}

            result = await c.poll_task(
                "SYNO.FileStation.CopyMove", task_id, timeout=300
            )

            return {
                nas_name: {
                    "success": not result.get("timeout", False),
                    "source": source_path,
                    "destination": dest_path,
                    "finished": not result.get("timeout", False),
                }
            }
        except Exception as e:
            return {nas_name: {"error": str(e)}}

    @mcp.tool
    async def copy(
        nas: str,
        source_path: str | list[str],
        dest_path: str,
        overwrite: bool = False,
    ) -> dict:
        """Copy files or folders to a new location on the same NAS.

        For large copies, this runs as an async task. Times out after 5 minutes
        for very large operations.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            source_path: Path or list of paths to copy.
            dest_path: Destination directory path.
            overwrite: Overwrite existing files at destination (default: False).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        nas_name = nas.lower()
        c = conn[nas_name]

        if isinstance(source_path, list):
            src = ",".join(source_path)
        else:
            src = source_path

        try:
            start_data = await c.call(
                "SYNO.FileStation.CopyMove",
                "start",
                version=3,
                path=src,
                dest_folder_path=dest_path,
                overwrite=str(overwrite).lower(),
                remove_src="false",
            )
            task_id = start_data.get("taskid")
            if not task_id:
                return {nas_name: {"error": "Failed to start copy task"}}

            result = await c.poll_task(
                "SYNO.FileStation.CopyMove", task_id, timeout=300
            )

            timed_out = result.get("timeout", False)
            resp = {
                nas_name: {
                    "success": not timed_out,
                    "source": source_path,
                    "destination": dest_path,
                    "finished": not timed_out,
                }
            }
            if timed_out:
                resp[nas_name]["task_id"] = result.get("task_id")
                resp[nas_name]["message"] = (
                    "Copy still in progress. Large file copy may take longer. "
                    "Check DSM File Station for status."
                )
            return resp
        except Exception as e:
            return {nas_name: {"error": str(e)}}
