from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    escape_odata,
    validate_date,
    fix_subtotal,
    pick,
    pick_list,
    build_lines,
    INVOICE_LIST_FIELDS,
    INVOICE_DETAIL_FIELDS,
    CREATE_RESULT_FIELDS,
)


_VALID_LAYOUTS = {"Item", "Service"}


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
        # The generic /Sale/Invoice/{id} endpoint returns a reduced field set
        # (no Lines, etc.).  Fetch it first to discover the layout, then
        # re-fetch from the layout-specific endpoint for full detail.
        summary = await app.client.request("GET", f"/Sale/Invoice/{invoice_id}")
        layout = summary.get("InvoiceType", "Item")
        if layout not in _VALID_LAYOUTS:
            layout = "Item"
        result = await app.client.request(
            "GET", f"/Sale/Invoice/{layout}/{invoice_id}"
        )
        return pick(fix_subtotal(result), INVOICE_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new sales invoice for a customer. "
        "Set invoice_layout to 'Item' (default) for quantity-based invoices "
        "(line items need: description, ship_quantity, unit_price, total, account_id, "
        "optional tax_code_id, optional job_id), or 'Service' for amount-based invoices "
        "(line items need: description, amount, account_id, optional tax_code_id, "
        "optional job_id)."
    )
    async def create_invoice(
        ctx: Context,
        customer_id: str,
        date: str,
        due_date: str,
        line_items: list[dict[str, Any]],
        invoice_layout: str = "Item",
        reference: str | None = None,
        notes: str | None = None,
        is_tax_inclusive: bool | None = None,
        salesperson_id: str | None = None,
    ) -> dict[str, Any]:
        invoice_layout = invoice_layout.capitalize()
        if invoice_layout not in _VALID_LAYOUTS:
            raise ValueError(
                f"Invalid invoice_layout '{invoice_layout}'. Must be 'Item' or 'Service'."
            )

        app = ctx.request_context.lifespan_context

        lines = build_lines(line_items, invoice_layout)

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
        if is_tax_inclusive is not None:
            body["IsTaxInclusive"] = is_tax_inclusive
        if salesperson_id is not None:
            body["Salesperson"] = {"UID": salesperson_id}

        result = await app.client.request(
            "POST", f"/Sale/Invoice/{invoice_layout}", json_body=body
        )
        app.client.cache.invalidate("invoices:")
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result
