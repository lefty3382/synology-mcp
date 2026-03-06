# Changelog

All notable changes to the Synology MCP Server are documented in this file.

## [1.0.1] - 2026-03-05

### Fixed
- Added `PYTHONUNBUFFERED=1` to Dockerfile so NAS connection logs are visible in `docker compose logs`

### Changed
- Renamed `mcp-readonly` to `mcp-service` in README and `.env.example` — the server supports write tier, so the old name was misleading

## [1.0.0] - 2026-03-05

### Added
- Initial release
- FastMCP server with native Streamable HTTP transport (port 8485)
- Multi-NAS support via `SYNOLOGY_<NAME>_HOST` environment variable discovery
- Three permission tiers controlled by `MCP_PERMISSION_TIER` env var:
  - `health` (default): 10 tools — system info, volumes, disks, SMART, shares, network, utilization, health summary
  - `read`: health + 3 tools — list directory, get file info, list shared folders
  - `write`: health + read + 2 tools — upload file, delete file
- Docker image published to GHCR (`ghcr.io/lefty3382/synology-mcp`)
- GitHub Actions workflow for automated Docker image builds on tag push
