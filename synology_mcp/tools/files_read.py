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
            path: Absolute directory path (e.g., '/Storage/Film/Anime/Golden Kamuy').
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

    @mcp.tool
    async def list_shared_folders(nas: str | None = None) -> dict:
        """List top-level shared folders on the NAS.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, c in client.direct.get_connections(nas).items():
            try:
                data = await c.call(
                    "SYNO.FileStation.List",
                    "list_share",
                    version=2,
                    additional='["volume_status","time","perm"]',
                )
                shares = []
                for s in data.get("shares", []):
                    additional = s.get("additional", {})
                    vol = additional.get("volume_status", {})
                    shares.append({
                        "name": s.get("name"),
                        "path": s.get("path"),
                        "is_dir": s.get("isdir", True),
                        "total_size": vol.get("totalspace"),
                        "free_size": vol.get("freespace"),
                    })
                results[name] = {"shared_folders": shares}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def search_files(
        nas: str,
        path: str,
        pattern: str,
        extension: str | None = None,
        recursive: bool = True,
        limit: int = 1000,
    ) -> dict:
        """Search for files by name pattern within a directory.

        Starts an async search task, polls until complete, returns results.
        May take several seconds for large directory trees.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Root directory to search from.
            pattern: Filename pattern to search for (e.g., '*.nfo', '*missing*').
            extension: Filter by file extension without dot (e.g., 'nfo', 'mkv'). Optional.
            recursive: Search subdirectories (default: True).
            limit: Max results to return (default: 1000).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        c = conn[name]

        try:
            # Start search task
            start_params = {
                "folder_path": path,
                "pattern": pattern,
                "recursive": str(recursive).lower(),
            }
            if extension:
                start_params["extension"] = extension

            start_data = await c.call(
                "SYNO.FileStation.Search", "start", version=2, **start_params
            )
            task_id = start_data.get("taskid")
            if not task_id:
                return {name: {"error": "Failed to start search task"}}

            # Poll until finished
            import asyncio as _asyncio
            import time as _time

            poll_start = _time.monotonic()
            timeout = 120  # 2 min timeout for searches
            files = []
            finished = False

            while (_time.monotonic() - poll_start) < timeout:
                list_data = await c.call(
                    "SYNO.FileStation.Search",
                    "list",
                    version=2,
                    taskid=task_id,
                    offset=0,
                    limit=limit,
                    additional='["size","time","type"]',
                )
                finished = list_data.get("finished", False)
                if finished:
                    for f in list_data.get("files", []):
                        additional = f.get("additional", {})
                        time_info = additional.get("time", {})
                        files.append({
                            "name": f.get("name"),
                            "path": f.get("path"),
                            "is_dir": f.get("isdir", False),
                            "size": additional.get("size"),
                            "modified": time_info.get("mtime"),
                            "type": additional.get("type", ""),
                        })
                    break
                await _asyncio.sleep(1.5)

            # Clean up
            try:
                await c.call(
                    "SYNO.FileStation.Search", "stop", version=2, taskid=task_id
                )
            except Exception:
                pass

            return {
                name: {
                    "path": path,
                    "pattern": pattern,
                    "total": len(files),
                    "finished": finished,
                    "files": files,
                }
            }
        except Exception as e:
            return {name: {"error": str(e)}}

    @mcp.tool
    async def get_file_content(
        nas: str,
        path: str,
        max_size: int = 1_048_576,
    ) -> dict:
        """Read the text content of a file on the NAS.

        Limited to text files only. Returns the file content as a string.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Absolute path to the file.
            max_size: Maximum file size in bytes (default: 1 MB / 1048576).
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        # Check extension allowlist
        import os
        ext = os.path.splitext(path)[1].lower()
        if ext not in _TEXT_EXTENSIONS:
            return {
                "error": f"Extension '{ext}' not in allowed list. "
                f"Allowed: {', '.join(sorted(_TEXT_EXTENSIONS))}"
            }

        name = nas.lower()
        try:
            raw = await client.direct.download(nas, path, max_size)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")

            return {
                name: {
                    "path": path,
                    "size": len(raw),
                    "content": text,
                }
            }
        except ValueError as e:
            return {name: {"error": str(e)}}
        except Exception as e:
            return {name: {"error": str(e)}}

    @mcp.tool
    async def compare_folders(nas: str, path_a: str, path_b: str) -> dict:
        """Compare contents of two directories on the same NAS.

        Returns files only in A, only in B, and in both (with size/date diffs).
        Useful for finding missing or mismatched files.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path_a: First directory path.
            path_b: Second directory path.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        c = conn[name]

        async def _list_all(folder_path: str) -> dict[str, dict]:
            """List all files in a folder, paginating if needed."""
            entries = {}
            offset = 0
            batch = 2000
            while True:
                data = await c.call(
                    "SYNO.FileStation.List",
                    "list",
                    version=2,
                    folder_path=folder_path,
                    offset=offset,
                    limit=batch,
                    additional='["size","time"]',
                )
                for f in data.get("files", []):
                    additional = f.get("additional", {})
                    time_info = additional.get("time", {})
                    entries[f["name"]] = {
                        "size": additional.get("size"),
                        "modified": time_info.get("mtime"),
                        "is_dir": f.get("isdir", False),
                    }
                total = data.get("total", 0)
                offset += batch
                if offset >= total:
                    break
            return entries

        try:
            files_a = await _list_all(path_a)
            files_b = await _list_all(path_b)

            names_a = set(files_a.keys())
            names_b = set(files_b.keys())

            only_in_a = sorted(names_a - names_b)
            only_in_b = sorted(names_b - names_a)
            common = sorted(names_a & names_b)

            in_both = []
            mismatched = 0
            for fname in common:
                a = files_a[fname]
                b = files_b[fname]
                size_match = a["size"] == b["size"]
                date_match = a["modified"] == b["modified"]
                if not size_match or not date_match:
                    mismatched += 1
                in_both.append({
                    "name": fname,
                    "size_a": a["size"],
                    "size_b": b["size"],
                    "modified_a": a["modified"],
                    "modified_b": b["modified"],
                    "size_match": size_match,
                    "date_match": date_match,
                })

            return {
                name: {
                    "path_a": path_a,
                    "path_b": path_b,
                    "only_in_a": only_in_a,
                    "only_in_b": only_in_b,
                    "in_both": in_both,
                    "summary": {
                        "total_a": len(files_a),
                        "total_b": len(files_b),
                        "only_in_a": len(only_in_a),
                        "only_in_b": len(only_in_b),
                        "in_both": len(common),
                        "mismatched": mismatched,
                    },
                }
            }
        except Exception as e:
            return {name: {"error": str(e)}}

    @mcp.tool
    async def get_folder_size(nas: str, path: str) -> dict:
        """Get recursive size and file count for a directory.

        Starts an async size calculation, polls until complete.
        May take several seconds for large directories.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer').
            path: Directory path.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        conn = client.direct.get_connections(nas)
        if not conn:
            return {"error": f"NAS '{nas}' not found or not connected"}

        name = nas.lower()
        c = conn[name]

        try:
            # Start dir size calculation
            start_data = await c.call(
                "SYNO.FileStation.DirSize", "start", version=2, path=path
            )
            task_id = start_data.get("taskid")
            if not task_id:
                return {name: {"error": "Failed to start dir size task"}}

            # Poll until finished
            result = await c.poll_task(
                "SYNO.FileStation.DirSize", task_id,
                poll_method="status", timeout=120
            )

            total_size = result.get("total_size", 0)
            # Human-readable size
            units = ["B", "KB", "MB", "GB", "TB"]
            size_hr = float(total_size)
            unit_idx = 0
            while size_hr >= 1024 and unit_idx < len(units) - 1:
                size_hr /= 1024
                unit_idx += 1

            return {
                name: {
                    "path": path,
                    "total_size_bytes": total_size,
                    "total_size_human": f"{size_hr:.2f} {units[unit_idx]}",
                    "num_files": result.get("num_file", 0),
                    "num_dirs": result.get("num_dir", 0),
                    "finished": not result.get("timeout", False),
                }
            }
        except Exception as e:
            return {name: {"error": str(e)}}
