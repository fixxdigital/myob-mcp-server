from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_JOBS
from ._filters import (
    escape_odata,
    pick_list,
    JOB_LIST_FIELDS,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all jobs. Can filter by active status and search by name or number. "
        "Use top to limit results and orderby to sort. "
        "Use the job UID as job_id on sales order line items."
    )
    async def list_jobs(
        ctx: Context,
        is_active: bool | None = None,
        search: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context

        params: dict[str, str] = {}
        filters: list[str] = []
        if is_active is not None:
            filters.append(f"IsActive eq {'true' if is_active else 'false'}")
        if search:
            safe = escape_odata(search)
            filters.append(
                f"(substringof('{safe}', Name) eq true"
                f" or substringof('{safe}', Number) eq true)"
            )
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        cache_key = f"jobs:{is_active}:{search}:{top}:{orderby}"
        items = await app.client.request_paged(
            "/GeneralLedger/Job",
            params=params,
            top=top,
            cache_key=cache_key,
            cache_ttl=CACHE_TTL_JOBS,
        )
        return pick_list(items, JOB_LIST_FIELDS)
