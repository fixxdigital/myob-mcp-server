from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_EMPLOYEES
from ._filters import (
    escape_odata,
    pick_list,
    EMPLOYEE_LIST_FIELDS,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all employees. Can filter by active status and search by name. "
        "Use top to limit results and orderby to sort. "
        "Use the employee UID as salesperson_id when creating sales orders."
    )
    async def list_employees(
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
                f"(substringof('{safe}', FirstName) eq true"
                f" or substringof('{safe}', LastName) eq true)"
            )
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        cache_key = f"employees:{is_active}:{search}:{top}:{orderby}"
        items = await app.client.request_paged(
            "/Contact/Employee",
            params=params,
            top=top,
            cache_key=cache_key,
            cache_ttl=CACHE_TTL_EMPLOYEES,
        )
        return pick_list(items, EMPLOYEE_LIST_FIELDS)
