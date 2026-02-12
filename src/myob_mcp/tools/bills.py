from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get purchase bills. Can filter by date range, status, and supplier."
    )
    async def list_bills(
        ctx: Context,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        supplier_id: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if date_from:
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            filters.append(f"Date le datetime'{date_to}'")
        if status:
            filters.append(f"Status eq '{status}'")
        if supplier_id:
            filters.append(f"Supplier/UID eq guid'{supplier_id}'")
        if filters:
            params["$filter"] = " and ".join(filters)

        return await app.client.request_paged(
            "/Purchase/Bill", params=params
        )

    @mcp.tool(
        description="Get detailed information about a specific purchase bill by its UID"
    )
    async def get_bill(
        ctx: Context,
        bill_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        return await app.client.request("GET", f"/Purchase/Bill/{bill_id}")

    @mcp.tool(
        description="Create a new purchase bill from a supplier"
    )
    async def create_bill(
        ctx: Context,
        supplier_id: str,
        date: str,
        due_date: str,
        line_items: list[dict[str, Any]],
        reference: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        lines = []
        for item in line_items:
            line: dict[str, Any] = {
                "Description": item["description"],
                "Quantity": item["quantity"],
                "UnitPrice": item["unit_price"],
                "Account": {"UID": item["account_id"]},
            }
            if "tax_code_id" in item:
                line["TaxCode"] = {"UID": item["tax_code_id"]}
            lines.append(line)

        body: dict[str, Any] = {
            "Supplier": {"UID": supplier_id},
            "Date": date,
            "BalanceDueDate": due_date,
            "Lines": lines,
        }
        if reference:
            body["Number"] = reference
        if notes:
            body["Comment"] = notes

        return await app.client.request(
            "POST", "/Purchase/Bill/Item", json_body=body
        )
