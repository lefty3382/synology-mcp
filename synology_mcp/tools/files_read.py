"""File browsing and inspection tools for Synology NAS (read tier)."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import SynologyClient


# Extensions allowed for text content reading
_TEXT_EXTENSIONS = frozenset({
    ".nfo", ".xml", ".srt", ".json", ".txt", ".log", ".ini",
    ".yaml", ".yml", ".csv", ".md", ".conf", ".cfg",
    ".properties", ".sub", ".ass", ".ssa", ".vtt",
})


def register_read_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register file reading/browsing tools (read tier)."""

    @mcp.tool
    async def list_files(
        nas: str,
        path: str,
        sort_by: str = "name",
        sort_direction: str = "asc",
        limit: int = 200,
        offset: int = 0,
        pattern: str | None = None,
    ) -> dict:
        """Browse a directory on the NAS. Returns files/folders with name, size, type, modified date.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Absolute directory path (e.g., '/volume1/Storage/Film/Anime/Golden Kamuy').
            sort_by: Sort field — 'name', 'size', 'mtime', or 'type' (default: 'name').
            sort_direction: 'asc' or 'desc' (default: 'asc').
            limit: Max items to return, max 2000 (default: 200).
            offset: Pagination offset (default: 0).
            pattern: Glob filter for filenames (e.g., '*.nfo', '*.mkv'). Optional.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        c = conn[name]

        sort_map = {"name": "name", "size": "size", "mtime": "mtime", "type": "type"}
        sort_field = sort_map.get(sort_by, "name")
        direction = "asc" if sort_direction.lower() == "asc" else "desc"

        try:
            params = {
                "folder_path": path,
                "offset": offset,
                "limit": min(limit, 2000),
                "sort_by": sort_field,
                "sort_direction": direction,
                "filetype": "all",
                "additional": '["size","time","type","perm"]',
            }
            if pattern:
                params["pattern"] = pattern

            data = await c.call(
                "SYNO.FileStation.List", "list", version=2, **params
            )

            files = []
            for f in data.get("files", []):
                additional = f.get("additional", {})
                time_info = additional.get("time", {})
                entry = {
                    "name": f.get("name"),
                    "path": f.get("path"),
                    "is_dir": f.get("isdir", False),
                    "size": additional.get("size"),
                    "modified": time_info.get("mtime"),
                    "created": time_info.get("crtime"),
                    "type": additional.get("type", ""),
                }
                files.append(entry)

            return {
                name: {
                    "path": path,
                    "total": data.get("total", len(files)),
                    "offset": data.get("offset", offset),
                    "limit": limit,
                    "files": files,
                }
            }
        except Exception as e:
            return {name: {"error": str(e)}}

    @mcp.tool
    async def get_file_info(nas: str, path: str) -> dict:
        """Get metadata for a specific file or folder on the NAS.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Absolute path to the file or folder.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        c = conn[name]

        try:
            data = await c.call(
                "SYNO.FileStation.List",
                "getinfo",
                version=2,
                path=path,
                additional='["size","time","type","perm","owner_group"]',
            )
            files = data.get("files", [])
            if not files:
                return {name: {"error": f"Path not found: {path}"}}

            f = files[0]
            additional = f.get("additional", {})
            time_info = additional.get("time", {})
            owner_info = additional.get("owner", {})
            perm_info = additional.get("perm", {})

            return {
                name: {
                    "name": f.get("name"),
                    "path": f.get("path"),
                    "is_dir": f.get("isdir", False),
                    "size": additional.get("size"),
                    "modified": time_info.get("mtime"),
                    "accessed": time_info.get("atime"),
                    "created": time_info.get("crtime"),
                    "changed": time_info.get("ctime"),
                    "type": additional.get("type", ""),
                    "owner": owner_info.get("user"),
                    "group": owner_info.get("group"),
                    "posix": perm_info.get("posix"),
                    "acl_enabled": perm_info.get("acl_enable", False),
                }
            }
        except Exception as e:
            return {name: {"error": str(e)}}
