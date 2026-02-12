from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_COMPANY_FILES


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all company files the authenticated user has access to. "
        "Useful for discovering available company file IDs."
    )
    async def list_company_files(ctx: Context) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET",
            "/",
            require_company_file=False,
            cache_key="company_files",
            cache_ttl=CACHE_TTL_COMPANY_FILES,
        )
        if isinstance(result, list):
            return result
        return [result] if result else []
