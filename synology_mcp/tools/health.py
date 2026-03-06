"""Health monitoring tools for Synology NAS."""

from fastmcp import FastMCP

from ..client import SynologyClient


def register_health_tools(mcp: FastMCP, client: SynologyClient) -> None:
    """Register health monitoring tools."""

    @mcp.tool
    async def list_nas() -> dict:
        """List all configured Synology NAS units with connection status."""
        return {
            "nas_units": [
                {"name": name, "connected": client.is_connected(name)}
                for name in client.names
            ]
        }

    @mcp.tool
    async def get_system_info(nas: str | None = None) -> dict:
        """Get system information for NAS unit(s): model, DSM version, uptime, temperature.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.information.update()
                results[name] = {
                    "model": api.information.model,
                    "serial": api.information.serial,
                    "temperature": api.information.temperature,
                    "temperature_warn": api.information.temperature_warn,
                    "uptime": api.information.uptime,
                    "version": api.information.version_string,
                    "ram_mb": api.information.ram,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_utilization(nas: str | None = None) -> dict:
        """Get current CPU, memory, and network utilization for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.utilisation.update()
                results[name] = {
                    "cpu_load_percent": api.utilisation.cpu_total_load,
                    "memory_usage_percent": api.utilisation.memory_real_usage,
                    "network_up": api.utilisation.network_up(),
                    "network_down": api.utilisation.network_down(),
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_volumes(nas: str | None = None) -> dict:
        """Get volume capacity, usage percentage, and RAID status for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.storage.update()
                volumes = []
                for vol_id in api.storage.volumes_ids:
                    volumes.append({
                        "id": vol_id,
                        "status": api.storage.volume_status(vol_id),
                        "device_type": api.storage.volume_device_type(vol_id),
                        "size_total": api.storage.volume_size_total(vol_id, human_readable=True),
                        "size_used": api.storage.volume_size_used(vol_id, human_readable=True),
                        "percentage_used": api.storage.volume_percentage_used(vol_id),
                        "avg_disk_temp": api.storage.volume_disk_temp_avg(vol_id),
                        "max_disk_temp": api.storage.volume_disk_temp_max(vol_id),
                    })
                results[name] = {"volumes": volumes}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_disks(nas: str | None = None) -> dict:
        """Get disk list with status, SMART health, and temperature for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.storage.update()
                disks = []
                for disk_id in api.storage.disks_ids:
                    disks.append({
                        "id": disk_id,
                        "name": api.storage.disk_name(disk_id),
                        "device": api.storage.disk_device(disk_id),
                        "status": api.storage.disk_status(disk_id),
                        "smart_status": api.storage.disk_smart_status(disk_id),
                        "temperature": api.storage.disk_temp(disk_id),
                        "exceed_bad_sector_threshold": api.storage.disk_exceed_bad_sector_thr(disk_id),
                        "below_remain_life_threshold": api.storage.disk_below_remain_life_thr(disk_id),
                    })
                results[name] = {"disks": disks}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_smart_status(nas: str | None = None) -> dict:
        """Get SMART health status for all disks on NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.storage.update()
                disks = []
                for disk_id in api.storage.disks_ids:
                    disks.append({
                        "id": disk_id,
                        "name": api.storage.disk_name(disk_id),
                        "smart_status": api.storage.disk_smart_status(disk_id),
                        "exceed_bad_sector_threshold": api.storage.disk_exceed_bad_sector_thr(disk_id),
                        "below_remain_life_threshold": api.storage.disk_below_remain_life_thr(disk_id),
                        "temperature": api.storage.disk_temp(disk_id),
                    })
                results[name] = {"disks": disks}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_storage_pools(nas: str | None = None) -> dict:
        """Get storage pool configuration and RAID type for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.storage.update()
                pools = []
                for pool in api.storage.storage_pools:
                    pool_data = {}
                    for attr in ["id", "status", "size", "device_type"]:
                        val = pool.get(attr) if isinstance(pool, dict) else getattr(pool, attr, None)
                        if val is not None:
                            pool_data[attr] = val
                    pools.append(pool_data)
                results[name] = {"storage_pools": pools}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_shares(nas: str | None = None) -> dict:
        """Get shared folder listing for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.share.update()
                shares = []
                for uuid in api.share.shares_uuids:
                    shares.append({
                        "uuid": uuid,
                        "name": api.share.share_name(uuid),
                        "path": api.share.share_path(uuid),
                        "size": api.share.share_size(uuid, human_readable=True),
                        "recycle_bin": api.share.share_recycle_bin(uuid),
                    })
                results[name] = {"shares": shares}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_network(nas: str | None = None) -> dict:
        """Get network interface information for NAS unit(s).

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.network.update()
                interfaces = []
                for iface in api.network.interfaces:
                    iface_data = {}
                    for attr in ["id", "ip", "ipv6", "mac", "type"]:
                        val = iface.get(attr) if isinstance(iface, dict) else getattr(iface, attr, None)
                        if val is not None:
                            iface_data[attr] = val
                    interfaces.append(iface_data)
                results[name] = {
                    "hostname": api.network.hostname,
                    "dns": api.network.dns,
                    "gateway": api.network.gateway,
                    "workgroup": api.network.workgroup,
                    "interfaces": interfaces,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    @mcp.tool
    async def get_health_summary(nas: str | None = None) -> dict:
        """Get aggregated health summary: system info, disk temps, volume usage, SMART alerts.

        Args:
            nas: NAS name (e.g., 'tank' or 'dozer'). If omitted, queries all.
        """
        results = {}
        for name, api in client.get_clients(nas).items():
            try:
                await api.information.update()
                await api.storage.update()
                await api.utilisation.update()

                alerts: list[str] = []
                disk_temps: list[dict] = []

                for disk_id in api.storage.disks_ids:
                    disk_name = api.storage.disk_name(disk_id)
                    temp = api.storage.disk_temp(disk_id)
                    smart = api.storage.disk_smart_status(disk_id)

                    if temp is not None:
                        disk_temps.append({"disk": disk_name, "temp": temp})
                    if smart and smart.lower() != "normal":
                        alerts.append(f"Disk {disk_name}: SMART status is {smart}")
                    if api.storage.disk_exceed_bad_sector_thr(disk_id):
                        alerts.append(f"Disk {disk_name}: exceeded bad sector threshold")
                    if api.storage.disk_below_remain_life_thr(disk_id):
                        alerts.append(f"Disk {disk_name}: below remaining life threshold")

                volume_usage: list[dict] = []
                for vol_id in api.storage.volumes_ids:
                    pct = api.storage.volume_percentage_used(vol_id)
                    status = api.storage.volume_status(vol_id)
                    volume_usage.append({
                        "id": vol_id,
                        "percentage_used": pct,
                        "status": status,
                    })
                    if status and status.lower() != "normal":
                        alerts.append(f"Volume {vol_id}: status is {status}")
                    if pct is not None and pct > 90:
                        alerts.append(f"Volume {vol_id}: usage at {pct}%")

                sys_temp = api.information.temperature
                warn_temp = api.information.temperature_warn
                if sys_temp and warn_temp and sys_temp >= warn_temp:
                    alerts.append(f"System temperature {sys_temp}C exceeds warning threshold")

                # Enhanced checks via direct API (if available)
                if client.direct:
                    conn_map = client.direct.get_connections(name)
                    conn = conn_map.get(name)
                    if conn:
                        # SSD cache health
                        try:
                            storage_data = await conn.call(
                                "SYNO.Storage.CGI.Storage",
                                "load_info",
                                version=1,
                                cache_key="storage_load_info",
                            )
                            for d in storage_data.get("disks", []):
                                if d.get("isSsd") and d.get("allocation_role", "").startswith("shared_cache"):
                                    if d.get("status") != "normal" or d.get("tray_status") == "not join":
                                        alerts.append(
                                            f"SSD Cache {d.get('name')}: status={d.get('status')}, "
                                            f"tray={d.get('tray_status')}"
                                        )
                        except Exception:
                            pass

                        # UPS status
                        try:
                            ups_data = await conn.call(
                                "SYNO.Core.ExternalDevice.UPS", "get", version=1
                            )
                            if ups_data.get("enable_ups"):
                                status = ups_data.get("ups_status", "")
                                charge = ups_data.get("ups_battery_charge")
                                if status and "ol" not in status.lower():
                                    alerts.append(f"UPS: status is {status}")
                                if charge is not None and int(charge) < 50:
                                    alerts.append(f"UPS: battery at {charge}%")
                        except Exception:
                            pass

                        # NFS service running (requires admin — skip if unreliable)
                        try:
                            nfs_data = await conn.call(
                                "SYNO.Core.FileServ.NFS", "get", version=2
                            )
                            # Only alert if the API returns meaningful data
                            # Non-admin users get empty/false responses
                            if nfs_data.get("nfs_enable") is False and len(nfs_data) > 1:
                                alerts.append("NFS service is disabled")
                        except Exception:
                            pass

                results[name] = {
                    "model": api.information.model,
                    "version": api.information.version_string,
                    "uptime": api.information.uptime,
                    "system_temp": sys_temp,
                    "cpu_load_percent": api.utilisation.cpu_total_load,
                    "memory_usage_percent": api.utilisation.memory_real_usage,
                    "disk_temperatures": disk_temps,
                    "volume_usage": volume_usage,
                    "alerts": alerts,
                    "healthy": len(alerts) == 0,
                }
            except Exception as e:
                results[name] = {"error": str(e)}
        return results
