# Synology MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for Synology NAS devices. Provides real-time, read-only access to NAS health, storage, and system information via Streamable HTTP transport.

Built with [FastMCP](https://gofastmcp.com/) and [py-synologydsm-api](https://github.com/mib1185/py-synologydsm-api).

## Features

- **Multi-NAS support** — monitor multiple Synology NAS units from a single server
- **Three permission tiers** — health (default), read, write — controlled by one env var
- **Native Streamable HTTP** — no proxy needed, connects directly from Claude Code
- **Single Docker container** — Python slim base, minimal dependencies

## Quick Start

### Docker (recommended)

```bash
# Pull the image
docker pull ghcr.io/lefty3382/synology-mcp:latest

# Run with environment variables
docker run -d \
  --name synology-mcp \
  -p 8485:8485 \
  -e SYNOLOGY_TANK_HOST=10.0.40.2 \
  -e SYNOLOGY_TANK_PORT=5001 \
  -e SYNOLOGY_TANK_USERNAME=mcp-service \
  -e SYNOLOGY_TANK_PASSWORD=yourpassword \
  -e MCP_PORT=8485 \
  -e MCP_PERMISSION_TIER=health \
  ghcr.io/lefty3382/synology-mcp:latest
```

### Claude Code

```bash
claude mcp add synology --transport http http://YOUR_HOST:8485/mcp --scope user
```

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in your values.

### NAS Configuration

Each NAS is configured with a `SYNOLOGY_<NAME>_*` prefix. Add as many NAS units as needed:

```
SYNOLOGY_TANK_HOST=10.0.40.2
SYNOLOGY_TANK_PORT=5001
SYNOLOGY_TANK_USERNAME=mcp-service
SYNOLOGY_TANK_PASSWORD=secret

SYNOLOGY_DOZER_HOST=10.0.40.3
SYNOLOGY_DOZER_PORT=5001
SYNOLOGY_DOZER_USERNAME=mcp-service
SYNOLOGY_DOZER_PASSWORD=secret
```

### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | `8485` | HTTP port for MCP endpoint |
| `MCP_PERMISSION_TIER` | `health` | Tool tier: `health`, `read`, or `write` |

## Permission Tiers

| Tier | Tools | Use Case |
|------|-------|----------|
| `health` (default) | System info, volumes, disks, SMART, shares, network, utilization | Infrastructure monitoring |
| `read` | Health + file listing, file info, shared folders | Browse NAS contents |
| `write` | Health + read + upload, delete | Full file management |

Change the tier by setting `MCP_PERMISSION_TIER` and restarting.

## Tools

### Health Tier (always available)

| Tool | Description |
|------|-------------|
| `list_nas` | List configured NAS units with connection status |
| `get_system_info` | DSM version, model, uptime, serial, temperature |
| `get_utilization` | CPU load, RAM usage, network I/O |
| `get_volumes` | Volume capacity, usage %, RAID status |
| `get_disks` | Disk list with status, temperature |
| `get_smart_status` | SMART health per disk |
| `get_storage_pools` | Storage pool config, RAID type |
| `get_shares` | Shared folder listing |
| `get_network` | Network interfaces, DNS, gateway |
| `get_health_summary` | Aggregated health with alerts |

### Read Tier

| Tool | Description |
|------|-------------|
| `list_directory` | List files/folders in a path |
| `get_file_info` | File/folder metadata |
| `list_shared_folders` | File Station shared folders |

### Write Tier

| Tool | Description |
|------|-------------|
| `upload_file` | Upload a text file |
| `delete_file` | Delete a file |

## NAS Authentication

Create a `mcp-service` local user on each Synology NAS:

1. DSM > Control Panel > User & Group > Create
2. Username: `mcp-service`
3. For health tier: may need admin group membership (DSM storage/SMART APIs often require admin)
4. Restrict application permissions to deny everything except DSM

## Development

```bash
# Clone and set up
git clone https://github.com/lefty3382/synology-mcp.git
cd synology-mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit config
cp .env.example .env

# Run locally
python -m synology_mcp
```

## Planned Additions

- `get_nfs_shares` — NFS export list with permissions (requires direct DSM API calls)
- `get_ups_status` — UPS status via NUT (requires direct DSM API calls)
- File search, create directory, rename, move (not yet supported by py-synologydsm-api)

## License

MIT
