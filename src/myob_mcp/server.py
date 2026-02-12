from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .api_client import MyobApiClient
from .auth import MyobAuth
from .cache import TTLCache
from .config import MyobConfig, load_config
from .tools import register_all_tools

# Configure logging to stderr (NEVER stdout — MCP uses stdout for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("myob_mcp")


@dataclass
class AppContext:
    config: MyobConfig
    auth: MyobAuth
    client: MyobApiClient


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    logger.info("Starting MYOB MCP server...")
    config = load_config()
    auth = MyobAuth(config)
    cache = TTLCache()
    client = MyobApiClient(config, auth, cache)
    try:
        yield AppContext(config=config, auth=auth, client=client)
    finally:
        await client.close()
        logger.info("MYOB MCP server stopped.")


mcp = FastMCP(
    "myob-business-api",
    instructions=(
        "MYOB AccountRight Live API server. "
        "Use oauth_authorize to authenticate before calling other tools. "
        "Use list_company_files to discover available company files."
    ),
    lifespan=app_lifespan,
)

register_all_tools(mcp)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
