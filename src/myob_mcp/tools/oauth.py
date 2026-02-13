from __future__ import annotations

import asyncio
import logging
import webbrowser
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..auth import run_oauth_callback_server

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Start OAuth authorization flow to authenticate with MYOB. "
        "Opens a browser window for user to authorize. "
        "Required before any other tools can be used."
    )
    async def oauth_authorize(ctx: Context) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        url = app.auth.get_authorization_url()
        logger.info("Opening browser for OAuth authorization")
        webbrowser.open(url)
        await run_oauth_callback_server(app.auth)
        result: dict[str, Any] = {
            "status": "authorized",
            "message": "OAuth authorization completed successfully.",
        }
        if app.auth._tokens and app.auth._tokens.get("business_id"):
            result["company_file_id"] = app.auth._tokens["business_id"]
        return result

    @mcp.tool(
        description="Manually refresh the OAuth access token. "
        "This is usually done automatically when needed."
    )
    async def oauth_refresh(ctx: Context) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        tokens = await app.auth.refresh_access_token()
        return {"status": "refreshed", "message": "Token refreshed successfully."}

    @mcp.tool(
        description="Check OAuth authentication status and token information"
    )
    async def oauth_status(ctx: Context) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        return app.auth.get_token_status()
