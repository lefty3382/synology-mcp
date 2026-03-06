"""Entry point for the Synology MCP server."""

import asyncio

from .config import AppConfig
from .client import SynologyClient
from .server import create_server


async def main() -> None:
    config = AppConfig.from_env()
    client = SynologyClient()
    try:
        await client.connect(config.nas_configs)
        mcp = create_server(config, client)
        await mcp.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=config.port,
            stateless_http=True,
        )
    finally:
        await client.disconnect()


asyncio.run(main())
