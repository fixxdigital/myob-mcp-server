from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    escape_odata,
    validate_date,
    pick,
    pick_list,
    SALES_ORDER_LIST_FIELDS,
    SALES_ORDER_DETAIL_FIELDS,
    CREATE_RESULT_FIELDS,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get sales orders. Can filter by date range, status, customer, "
        "and search by order number. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_sales_orders(
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
            "/Sale/Order", params=params, top=top
        )
        return pick_list(items, SALES_ORDER_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific sales order by its UID"
    )
    async def get_sales_order(
        ctx: Context,
        sales_order_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request("GET", f"/Sale/Order/{sales_order_id}")
        return pick(result, SALES_ORDER_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new sales order for a customer"
    )
    async def create_sales_order(
        ctx: Context,
        customer_id: str,
        date: str,
        line_items: list[dict[str, Any]],
        number: str | None = None,
        comment: str | None = None,
        ship_to_address: str | None = None,
        is_tax_inclusive: bool | None = None,
        freight: float | None = None,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        lines = []
        for item in line_items:
            line: dict[str, Any] = {
                "Type": "Transaction",
                "Description": item["description"],
                "ShipQuantity": item["ship_quantity"],
                "UnitPrice": item["unit_price"],
                "Total": item["total"],
                "Account": {"UID": item["account_id"]},
            }
            if "tax_code_id" in item:
                line["TaxCode"] = {"UID": item["tax_code_id"]}
            lines.append(line)

        body: dict[str, Any] = {
            "Customer": {"UID": customer_id},
            "Date": date,
            "Lines": lines,
        }
        if number:
            body["Number"] = number
        if comment:
            body["Comment"] = comment
        if ship_to_address:
            body["ShipToAddress"] = ship_to_address
        if is_tax_inclusive is not None:
            body["IsTaxInclusive"] = is_tax_inclusive
        if freight is not None:
            body["Freight"] = freight

        result = await app.client.request(
            "POST", "/Sale/Order/Item", json_body=body
        )
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result

    @mcp.tool(
        description="Edit/update an existing sales order. Only orders with status 'Open' can be edited."
    )
    async def edit_sales_order(
        ctx: Context,
        sales_order_id: str,
        date: str | None = None,
        customer_id: str | None = None,
        line_items: list[dict[str, Any]] | None = None,
        number: str | None = None,
        comment: str | None = None,
        ship_to_address: str | None = None,
        is_tax_inclusive: bool | None = None,
        freight: float | None = None,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        # Fetch full current order (unfiltered — needs RowVersion for PUT)
        current = await app.client.request(
            "GET", f"/Sale/Order/{sales_order_id}"
        )

        if current.get("Status") != "Open":
            raise ValueError(
                f"Cannot edit order with status '{current.get('Status')}'. "
                "Only orders with status 'Open' can be edited."
            )

        body = dict(current)

        if "RowVersion" not in body:
            raise ValueError(
                "Cannot update order: RowVersion missing from fetched order. "
                "The order may have been deleted or the API response format changed."
            )

        if date is not None:
            body["Date"] = date
        if customer_id is not None:
            body["Customer"] = {"UID": customer_id}
        if number is not None:
            body["Number"] = number
        if comment is not None:
            body["Comment"] = comment
        if ship_to_address is not None:
            body["ShipToAddress"] = ship_to_address
        if is_tax_inclusive is not None:
            body["IsTaxInclusive"] = is_tax_inclusive
        if freight is not None:
            body["Freight"] = freight

        if line_items is not None:
            lines = []
            for item in line_items:
                line: dict[str, Any] = {
                    "Type": "Transaction",
                    "Description": item["description"],
                    "ShipQuantity": item["ship_quantity"],
                    "UnitPrice": item["unit_price"],
                    "Total": item["total"],
                    "Account": {"UID": item["account_id"]},
                }
                if "tax_code_id" in item:
                    line["TaxCode"] = {"UID": item["tax_code_id"]}
                lines.append(line)
            body["Lines"] = lines

        result = await app.client.request(
            "PUT", f"/Sale/Order/Item/{sales_order_id}", json_body=body
        )
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result
