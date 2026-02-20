from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_ACCOUNTS
from ._filters import escape_odata, pick_list, strip_metadata, ACCOUNT_LIST_FIELDS


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all accounts from the chart of accounts. "
        "Can filter by account type (Asset, Liability, Income, Expense, Equity) "
        "and active status. Use search to find accounts by number or name "
        "(e.g. search='5-1104' or search='electricity'). "
        "Combine filter and search to narrow results "
        "(e.g. filter='Expense', search='1104'). "
        "Use top to limit results and orderby to sort."
    )
    async def list_accounts(
        ctx: Context,
        filter: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if filter:
            filters.append(f"Type eq '{filter}'")
        if is_active is not None:
            filters.append(f"IsActive eq {'true' if is_active else 'false'}")
        if search:
            safe = escape_odata(search).lower()
            filters.append(
                f"(substringof('{safe}', tolower(DisplayID)) eq true"
                f" or substringof('{safe}', tolower(Name)) eq true)"
            )
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        cache_key = f"accounts:{filter}:{is_active}:{search}:{top}:{orderby}"
        items = await app.client.request_paged(
            "/GeneralLedger/Account",
            params=params,
            top=top,
            cache_key=cache_key,
            cache_ttl=CACHE_TTL_ACCOUNTS,
        )
        return pick_list(items, ACCOUNT_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific account by its UID"
    )
    async def get_account(
        ctx: Context,
        account_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET", f"/GeneralLedger/Account/{account_id}"
        )
        return strip_metadata(result)
