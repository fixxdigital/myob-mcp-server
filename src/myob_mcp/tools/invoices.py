from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    escape_odata,
    validate_date,
    fix_subtotal,
    pick,
    pick_list,
    INVOICE_LIST_FIELDS,
    INVOICE_DETAIL_FIELDS,
    CREATE_RESULT_FIELDS,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get sales invoices. Can filter by date range, status, customer, "
        "and search by invoice number. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_invoices(
        ctx: Context,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        customer_id: str | None = None,
        search: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if date_from:
            validate_date(date_from, "date_from")
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            validate_date(date_to, "date_to")
            filters.append(f"Date le datetime'{date_to}'")
        if status:
            filters.append(f"Status eq '{escape_odata(status)}'")
        if customer_id:
            filters.append(f"Customer/UID eq guid'{customer_id}'")
        if search:
            filters.append(f"substringof('{escape_odata(search)}', Number) eq true")
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        items = await app.client.request_paged(
            "/Sale/Invoice", params=params, top=top
        )
        return pick_list([fix_subtotal(i) for i in items], INVOICE_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific sales invoice by its UID"
    )
    async def get_invoice(
        ctx: Context,
        invoice_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request("GET", f"/Sale/Invoice/{invoice_id}")
        return pick(fix_subtotal(result), INVOICE_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new sales invoice for a customer"
    )
    async def create_invoice(
        ctx: Context,
        customer_id: str,
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
            "Customer": {"UID": customer_id},
            "Date": date,
            "BalanceDueDate": due_date,
            "Lines": lines,
        }
        if reference:
            body["Number"] = reference
        if notes:
            body["Comment"] = notes

        result = await app.client.request(
            "POST", "/Sale/Invoice/Item", json_body=body
        )
        app.client.cache.invalidate("invoices:")
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result
