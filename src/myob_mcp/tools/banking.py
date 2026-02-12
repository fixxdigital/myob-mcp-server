from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all bank accounts from the chart of accounts"
    )
    async def list_bank_accounts(ctx: Context) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        return await app.client.request_paged("/Banking/BankAccount")

    @mcp.tool(
        description="Get bank transactions for a specific bank account. "
        "Can filter by date range."
    )
    async def list_bank_transactions(
        ctx: Context,
        bank_account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        filters.append(f"Account/UID eq guid'{bank_account_id}'")
        if date_from:
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            filters.append(f"Date le datetime'{date_to}'")
        params["$filter"] = " and ".join(filters)

        return await app.client.request_paged(
            "/Banking/SpendMoneyTxn", params=params
        )
