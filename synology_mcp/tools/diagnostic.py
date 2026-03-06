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

    @mcp.tool
    async def get_disk_details(nas: str | None = None) -> dict:
        """Get full per-disk hardware details: model, serial, firmware, SMART, temperature, allocation.

        Returns comprehensive disk information from SYNO.Storage.CGI.Storage
        including hardware identifiers, health status, and pool membership.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Storage.CGI.Storage",
                    "load_info",
                    version=1,
                    cache_key="storage_load_info",
                )
                disks = []
                for disk in data.get("disks", []):
                    disks.append({
                        "id": disk.get("id"),
                        "name": disk.get("name"),
                        "model": disk.get("model"),
                        "serial": disk.get("serial"),
                        "vendor": disk.get("vendor"),
                        "firmware": disk.get("firm"),
                        "size_bytes": disk.get("size_total"),
                        "disk_type": disk.get("diskType"),
                        "is_ssd": disk.get("isSsd", False),
                        "status": disk.get("status"),
                        "overview_status": disk.get("overview_status"),
                        "smart_status": disk.get("smart_status"),
                        "tray_status": disk.get("tray_status"),
                        "allocation_role": disk.get("container", {}).get("str") if isinstance(disk.get("container"), dict) else disk.get("container"),
                        "used_by": disk.get("used_by"),
                        "slot_id": disk.get("slot_id"),
                        "temperature": disk.get("temp"),
                        "unc": disk.get("unc"),
                        "disk_code": disk.get("disk_code"),
                    })
                results[name] = {"disk_count": len(disks), "disks": disks}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_ssd_cache(nas: str | None = None) -> dict:
        """Get SSD cache pool status and per-disk health.

        Identifies SSD cache disks, groups them by pool, and reports
        health status for each cache member.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Storage.CGI.Storage",
                    "load_info",
                    version=1,
                    cache_key="storage_load_info",
                )

                # Find SSD cache disks
                cache_disks: list[dict] = []
                for disk in data.get("disks", []):
                    tray = disk.get("tray_status", "")
                    is_ssd = disk.get("isSsd", False)
                    if is_ssd and tray in ("ssd_cache", "ssd cache", "not_join", "not join"):
                        healthy = (
                            disk.get("status", "").lower() == "normal"
                            and tray in ("ssd_cache", "ssd cache")
                        )
                        role = disk.get("container", {}).get("str") if isinstance(disk.get("container"), dict) else disk.get("container")
                        cache_disks.append({
                            "id": disk.get("id"),
                            "name": disk.get("name"),
                            "model": disk.get("model"),
                            "size_bytes": disk.get("size_total"),
                            "status": disk.get("status"),
                            "tray_status": tray,
                            "allocation_role": role,
                            "healthy": healthy,
                        })

                # Group by pool
                pools_map: dict[str, list[dict]] = {}
                for cd in cache_disks:
                    pool_id = cd.get("allocation_role") or "unassigned"
                    pools_map.setdefault(pool_id, []).append(cd)

                # Check for cache pool metadata from ssdCaches or storagePools
                cache_pool_meta: list[dict] = []
                for cache in data.get("ssdCaches", []):
                    cache_pool_meta.append({
                        "id": cache.get("id"),
                        "status": cache.get("status"),
                        "size": cache.get("size"),
                    })
                if not cache_pool_meta:
                    for pool in data.get("storagePools", []):
                        if "cache" in str(pool.get("id", "")).lower() or "cache" in str(pool.get("device_type", "")).lower():
                            cache_pool_meta.append({
                                "id": pool.get("id"),
                                "status": pool.get("status"),
                                "size": pool.get("size"),
                            })

                cache_pools = []
                for pool_id, members in pools_map.items():
                    cache_pools.append({
                        "pool_id": pool_id,
                        "disk_count": len(members),
                        "all_healthy": all(d["healthy"] for d in members),
                        "disks": members,
                    })

                results[name] = {
                    "has_cache": len(cache_disks) > 0,
                    "cache_disk_count": len(cache_disks),
                    "cache_pools": cache_pools,
                    "cache_pool_meta": cache_pool_meta,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_storage_pool_members(nas: str | None = None) -> dict:
        """Get per-pool disk membership with cross-referenced hardware details.

        For each storage pool, lists member disks with model, status,
        temperature, and checks for active scrub/rebuild operations.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Storage.CGI.Storage",
                    "load_info",
                    version=1,
                    cache_key="storage_load_info",
                )

                # Build disk lookup by ID
                disk_map: dict[str, dict] = {}
                for disk in data.get("disks", []):
                    disk_id = disk.get("id")
                    if disk_id:
                        disk_map[disk_id] = {
                            "name": disk.get("name"),
                            "model": disk.get("model"),
                            "status": disk.get("status"),
                            "tray_status": disk.get("tray_status"),
                            "temperature": disk.get("temp"),
                        }

                pools = []
                for pool in data.get("storagePools", []):
                    pool_disks = []
                    for disk_ref in pool.get("disks", []):
                        # disk_ref may be a string ID or a dict with an id key
                        if isinstance(disk_ref, dict):
                            did = disk_ref.get("id", "")
                        else:
                            did = str(disk_ref)
                        info = disk_map.get(did, {})
                        pool_disks.append({
                            "disk_id": did,
                            "name": info.get("name"),
                            "model": info.get("model"),
                            "status": info.get("status"),
                            "tray_status": info.get("tray_status"),
                            "temperature": info.get("temperature"),
                        })

                    # Check for scrub/rebuild flags
                    is_scrubbing = pool.get("is_scrubbing", False) or pool.get("scrubing", False)
                    is_rebuilding = pool.get("is_rebuilding", False) or pool.get("repairing", False)

                    pools.append({
                        "pool_id": pool.get("id"),
                        "status": pool.get("status"),
                        "raid_type": pool.get("raidType") or pool.get("raid_type"),
                        "disk_count": len(pool_disks),
                        "is_scrubbing": is_scrubbing,
                        "is_rebuilding": is_rebuilding,
                        "disks": pool_disks,
                    })

                results[name] = {"pool_count": len(pools), "pools": pools}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results
