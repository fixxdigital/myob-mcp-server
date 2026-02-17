from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    validate_date,
    pick_list,
    BANK_ACCOUNT_LIST_FIELDS,
    BANK_TXN_LIST_FIELDS,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all bank accounts from the chart of accounts. "
        "Use top to limit results and orderby to sort."
    )
    async def list_bank_accounts(
        ctx: Context,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        if orderby:
            params["$orderby"] = orderby
        items = await app.client.request_paged(
            "/Banking/BankAccount", params=params or None, top=top
        )
        return pick_list(items, BANK_ACCOUNT_LIST_FIELDS)

    @mcp.tool(
        description="Get bank transactions for a specific bank account. "
        "Can filter by date range. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_bank_transactions(
        ctx: Context,
        bank_account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        filters.append(f"Account/UID eq guid'{bank_account_id}'")
        if date_from:
            validate_date(date_from, "date_from")
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            validate_date(date_to, "date_to")
            filters.append(f"Date le datetime'{date_to}'")
        params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        items = await app.client.request_paged(
            "/Banking/SpendMoneyTxn", params=params, top=top
        )
        return pick_list(items, BANK_TXN_LIST_FIELDS)
