from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_TAX_CODES
from ._filters import pick_list, TAX_CODE_LIST_FIELDS


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all tax codes for the company file. "
        "Returns UID, Code, Description, Type, and Rate for each tax code. "
        "Use the UID when setting tax codes on invoice, bill, or sales order line items. "
        "Common codes include GST, FRE (GST-Free), and N-T (No Tax)."
    )
    async def list_tax_codes(
        ctx: Context,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        items = await app.client.request_paged(
            "/GeneralLedger/TaxCode",
            cache_key="tax_codes",
            cache_ttl=CACHE_TTL_TAX_CODES,
        )
        return pick_list(items, TAX_CODE_LIST_FIELDS)
