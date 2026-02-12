from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_ACCOUNTS


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all accounts from the chart of accounts. "
        "Can filter by account type (Asset, Liability, Income, Expense, Equity) "
        "and active status."
    )
    async def list_accounts(
        ctx: Context,
        filter: str | None = None,
        is_active: bool | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if filter:
            filters.append(f"Type eq '{filter}'")
        if is_active is not None:
            filters.append(f"IsActive eq {'true' if is_active else 'false'}")
        if filters:
            params["$filter"] = " and ".join(filters)

        cache_key = f"accounts:{filter}:{is_active}"
        return await app.client.request_paged(
            "/GeneralLedger/Account",
            params=params,
            cache_key=cache_key,
            cache_ttl=CACHE_TTL_ACCOUNTS,
        )

    @mcp.tool(
        description="Get detailed information about a specific account by its UID"
    )
    async def get_account(
        ctx: Context,
        account_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        return await app.client.request(
            "GET", f"/GeneralLedger/Account/{account_id}"
        )
