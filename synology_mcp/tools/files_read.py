"""File browsing tools for Synology NAS (read tier)."""

from fastmcp import FastMCP

from ..client import SynologyClient


def register_read_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register file reading tools."""

    @mcp.tool
    async def list_directory(
        path: str, nas: str | None = None, offset: int = 0, limit: int = 100
    ) -> dict:
        """List files and folders in a directory on the NAS.

        Args:
            path: Directory path (e.g., '/volume1/Film')
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
            offset: Pagination offset (default: 0)
            limit: Max items to return (default: 100)
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                files = await api.file.get_files(path, offset=offset, limit=limit)
                if files is not None:
                    results[name] = {
                        "path": path,
                        "files": [
                            {
                                "name": f.name,
                                "path": f.path,
                                "is_dir": f.is_dir,
                                "size": f.additional.size if f.additional else None,
                            }
                            for f in files
                        ],
                    }
                else:
                    results[name] = {"path": path, "files": [], "error": "Path not found or access denied"}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_file_info(path: str, filename: str, nas: str) -> dict:
        """Get metadata for a specific file on a NAS.

        Args:
            path: Parent directory path (e.g., '/volume1/Film')
            filename: Name of the file
            nas: NAS name (e.g., 'tank' or 'dozer')
        """
        api = client.get_client(nas)
        if not api:
            return {"error": f"NAS '{nas}' not found or not connected"}
        try:
            files = await api.file.get_files(path, limit=1000)
            if files:
                for f in files:
                    if f.name == filename:
                        result = {
                            "name": f.name,
                            "path": f.path,
                            "is_dir": f.is_dir,
                        }
                        if f.additional:
                            result["size"] = f.additional.size
                            if f.additional.time:
                                result["modified"] = f.additional.time.mtime
                                result["created"] = f.additional.time.crtime
                            if f.additional.owner:
                                result["owner"] = f.additional.owner.user
                                result["group"] = f.additional.owner.group
                        return result
            return {"error": f"File '{filename}' not found in '{path}'"}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool
    async def list_shared_folders(nas: str | None = None) -> dict:
        """List all shared folders accessible via File Station.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                folders = await api.file.get_shared_folders()
                if folders is not None:
                    results[name] = {
                        "shared_folders": [
                            {"name": f.name, "path": f.path}
                            for f in folders
                        ],
                    }
                else:
                    results[name] = {"shared_folders": [], "error": "Access denied"}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results
