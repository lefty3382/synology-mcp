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

    @mcp.tool
    async def get_nfs_exports(nas: str | None = None) -> dict:
        """Get NFS service status and per-share export rules.

        Checks whether NFS is enabled, then lists share-level export
        rules including host, privilege, squash, and security settings.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                # Get NFS service status
                nfs_data = await conn.call(
                    "SYNO.Core.FileServ.NFS",
                    "get",
                    version=2,
                )
                nfs_enabled = nfs_data.get("nfs_enable", False)

                # Get per-share NFS privileges
                priv_data = await conn.call(
                    "SYNO.Core.FileServ.NFS.SharePrivilege",
                    "list",
                    version=1,
                )
                shares = []
                for share in priv_data.get("shares", []):
                    rules = []
                    for rule in share.get("rules", []):
                        rules.append({
                            "host": rule.get("host"),
                            "privilege": rule.get("privilege"),
                            "squash": rule.get("squash"),
                            "security": rule.get("security"),
                        })
                    shares.append({
                        "name": share.get("name"),
                        "path": share.get("path"),
                        "rules": rules,
                    })

                results[name] = {
                    "nfs_enabled": nfs_enabled,
                    "share_count": len(shares),
                    "shares": shares,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_services_status(nas: str | None = None) -> dict:
        """Get enabled/disabled status for key DSM services.

        Checks NFS, SMB, SSH, rsync, and SNMP service status individually.
        One service failing does not prevent others from being reported.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            services: dict = {}

            # NFS
            try:
                nfs_data = await conn.call(
                    "SYNO.Core.FileServ.NFS", "get", version=2
                )
                services["nfs"] = {
                    "enabled": nfs_data.get("nfs_enable", False),
                }
            except Exception as e:
                services["nfs"] = {"error": str(e)}

            # SMB
            try:
                smb_data = await conn.call(
                    "SYNO.Core.FileServ.SMB", "get", version=3
                )
                services["smb"] = {
                    "enabled": smb_data.get("enable_smb", smb_data.get("smb_enable", False)),
                }
            except Exception as e:
                services["smb"] = {"error": str(e)}

            # SSH
            try:
                ssh_data = await conn.call(
                    "SYNO.Core.Terminal", "get", version=3
                )
                services["ssh"] = {
                    "enabled": ssh_data.get("enable_ssh", False),
                    "port": ssh_data.get("ssh_port"),
                }
            except Exception as e:
                services["ssh"] = {"error": str(e)}

            # rsync
            try:
                rsync_data = await conn.call(
                    "SYNO.Core.FileServ.Rsync", "get", version=2
                )
                services["rsync"] = {
                    "enabled": rsync_data.get("enable_rsync", rsync_data.get("rsync_enable", False)),
                }
            except Exception as e:
                services["rsync"] = {"error": str(e)}

            # SNMP
            try:
                snmp_data = await conn.call(
                    "SYNO.Core.SNMP", "get", version=1
                )
                services["snmp"] = {
                    "enabled": snmp_data.get("snmp_enable", snmp_data.get("enable_snmp", False)),
                }
            except Exception as e:
                services["snmp"] = {"error": str(e)}

            results[name] = {"services": services}
        return results

    @mcp.tool
    async def get_ups_status(nas: str | None = None) -> dict:
        """Get UPS (Uninterruptible Power Supply) status and configuration.

        Reports UPS mode, model, battery charge, estimated runtime,
        and shutdown settings from SYNO.Core.ExternalDevice.UPS.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Core.ExternalDevice.UPS",
                    "get",
                    version=1,
                )
                results[name] = {
                    "enable_ups": data.get("enable_ups", False),
                    "ups_mode": data.get("ups_mode"),
                    "model": data.get("ups_model"),
                    "status": data.get("ups_status"),
                    "battery_charge": data.get("ups_battery_charge"),
                    "battery_runtime_seconds": data.get("ups_battery_runtime"),
                    "server_ip": data.get("ups_server_ip"),
                    "shutdown_mode": data.get("shutdown_mode"),
                    "safe_shutdown_time": data.get("safe_shutdown_time"),
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_hardware_info(nas: str | None = None) -> dict:
        """Get hardware details: fan speeds, power schedule, and beep control.

        Queries multiple SYNO.Core.Hardware.* APIs individually so one
        failure does not prevent others from being reported.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            hw: dict = {}

            # Fan speed
            try:
                fan_data = await conn.call(
                    "SYNO.Core.Hardware.FanSpeed", "get", version=1
                )
                hw["fan_speed_mode"] = fan_data.get("fan_speed_mode")
                hw["fans"] = fan_data.get("fans", [])
            except Exception as e:
                hw["fan_error"] = str(e)

            # Power schedule
            try:
                power_data = await conn.call(
                    "SYNO.Core.Hardware.PowerSchedule", "load", version=1
                )
                hw["power_recovery"] = power_data.get("power_recovery")
                hw["schedule"] = power_data.get("schedule", [])
            except Exception as e:
                hw["power_schedule_error"] = str(e)

            # Beep control
            try:
                beep_data = await conn.call(
                    "SYNO.Core.Hardware.BeepControl", "get", version=1
                )
                hw["beep_enabled"] = beep_data.get("beep_enabled", beep_data.get("enable_beep"))
            except Exception as e:
                hw["beep_error"] = str(e)

            results[name] = hw
        return results

    @mcp.tool
    async def get_recent_logs(
        nas: str | None = None,
        limit: int = 50,
        severity: str | None = None,
        keyword: str | None = None,
    ) -> dict:
        """Get recent DSM system log entries with optional filtering.

        Retrieves syslog entries from the NAS. Supports filtering by severity
        level and keyword search.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
            limit: Maximum number of log entries to return (default 50).
            severity: Filter by severity level: 'info', 'warn', or 'error'.
            keyword: Filter logs containing this keyword string.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        severity_map = {"info": 0, "warn": 1, "error": 2}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                # Build params for primary API
                params: dict = {"limit": limit, "offset": 0}
                if severity and severity.lower() in severity_map:
                    params["level"] = severity_map[severity.lower()]
                if keyword:
                    params["keyword"] = keyword

                # Try primary API: SYNO.Core.SyslogClient.Status
                data = None
                try:
                    data = await conn.call(
                        "SYNO.Core.SyslogClient.Status",
                        "list",
                        version=1,
                        **params,
                    )
                except Exception:
                    pass

                # Fallback if primary fails or returns empty
                items = []
                if data:
                    items = data.get("items", data.get("logs", []))

                if not items:
                    try:
                        fallback_data = await conn.call(
                            "SYNO.Core.SyslogClient.Log",
                            "get",
                            version=1,
                            **params,
                        )
                        items = fallback_data.get("items", fallback_data.get("logs", []))
                    except Exception:
                        pass

                logs = []
                for entry in items:
                    logs.append({
                        "timestamp": entry.get("time", entry.get("timestamp")),
                        "severity": entry.get("level_str", entry.get("level")),
                        "user": entry.get("who", entry.get("user")),
                        "event": entry.get("descr", entry.get("desc", entry.get("msg"))),
                        "ip": entry.get("ip"),
                    })

                results[name] = {
                    "total": data.get("total", len(logs)) if data else len(logs),
                    "logs": logs,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_notifications(nas: str | None = None) -> dict:
        """Get notification configuration and recent warning/error alerts.

        Returns push/mail notification settings and recent high-severity
        log entries (warnings and errors).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                # Get notification configuration
                notification_config = {}
                try:
                    notif_data = await conn.call(
                        "SYNO.Core.Notification.Push.Mail",
                        "get",
                        version=1,
                    )
                    notification_config = {
                        "push_enabled": notif_data.get("push_enabled", notif_data.get("enable_push", False)),
                        "mail_enabled": notif_data.get("mail_enabled", notif_data.get("enable_mail", False)),
                    }
                except Exception as e:
                    notification_config = {"error": str(e)}

                # Get recent warning+ logs (level=1 means warn and above)
                recent_alerts = []
                try:
                    log_data = await conn.call(
                        "SYNO.Core.SyslogClient.Status",
                        "list",
                        version=1,
                        limit=50,
                        offset=0,
                        level=1,
                    )
                    items = log_data.get("items", log_data.get("logs", []))
                    for entry in items:
                        recent_alerts.append({
                            "timestamp": entry.get("time", entry.get("timestamp")),
                            "severity": entry.get("level_str", entry.get("level")),
                            "event": entry.get("descr", entry.get("desc", entry.get("msg"))),
                        })
                except Exception:
                    pass

                results[name] = {
                    "notification_config": notification_config,
                    "recent_alerts": recent_alerts,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_active_connections(nas: str | None = None) -> dict:
        """Get active login sessions and connections to the NAS.

        Lists all current connections including connection type, source IP,
        user, login time, and description.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Core.CurrentConnection",
                    "list",
                    version=1,
                    limit=200,
                    offset=0,
                )
                connections = []
                for item in data.get("items", []):
                    connections.append({
                        "type": item.get("type"),
                        "ip": item.get("ip"),
                        "who": item.get("who"),
                        "time": item.get("time"),
                        "descr": item.get("descr"),
                    })

                results[name] = {
                    "total": data.get("total", len(connections)),
                    "connections": connections,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_users(nas: str | None = None) -> dict:
        """Get local user accounts on the NAS.

        Lists all local DSM user accounts with name, UID, description,
        email, expiry status, and whether they are administrators.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Core.User",
                    "list",
                    version=1,
                    offset=0,
                    limit=200,
                    type="local",
                )
                users = []
                for user in data.get("users", []):
                    groups = user.get("groups", [])
                    is_admin = "administrators" in groups
                    users.append({
                        "name": user.get("name"),
                        "uid": user.get("uid"),
                        "description": user.get("description"),
                        "email": user.get("email"),
                        "expired": user.get("expired"),
                        "admin": is_admin,
                    })

                results[name] = {
                    "total": data.get("total", len(users)),
                    "users": users,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_update_status(nas: str | None = None) -> dict:
        """Check for available DSM firmware updates.

        Reports current firmware version, whether an update is available,
        the update version, reboot requirements, and release notes URL.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        if not client.direct:
            return {"error": "Direct API client not initialized"}

        results = {}
        for name, conn in client.direct.get_connections(nas).items():
            try:
                data = await conn.call(
                    "SYNO.Core.Upgrade.Server",
                    "check",
                    version=1,
                )
                results[name] = {
                    "current_version": data.get("firmware_version"),
                    "update_available": data.get("available", False),
                    "update_version": data.get("version"),
                    "reboot_needed": data.get("reboot_needed", data.get("reboot")),
                    "release_notes": data.get("release_notes_url"),
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results
