from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    escape_odata,
    validate_date,
    fix_subtotal,
    pick,
    pick_list,
    SALES_ORDER_LIST_FIELDS,
    SALES_ORDER_DETAIL_FIELDS,
    CREATE_RESULT_FIELDS,
)


_VALID_LAYOUTS = {"Item", "Service"}


def _build_lines(
    line_items: list[dict[str, Any]], layout: str
) -> list[dict[str, Any]]:
    """Build MYOB API line objects from user-provided line item dicts.

    Item layout lines require: description, ship_quantity, unit_price, total, account_id
    Service layout lines require: description, amount, account_id
    Both accept optional: tax_code_id, job_id
    """
    lines: list[dict[str, Any]] = []
    for i, item in enumerate(line_items):
        line: dict[str, Any] = {
            "Type": "Transaction",
            "Description": item.get("description", ""),
            "Account": {"UID": item["account_id"]},
        }

        if layout == "Item":
            for field in ("ship_quantity", "unit_price", "total"):
                if field not in item:
                    raise ValueError(
                        f"Line item {i}: '{field}' is required for Item layout orders."
                    )
            line["ShipQuantity"] = item["ship_quantity"]
            line["UnitPrice"] = item["unit_price"]
            line["Total"] = item["total"]
        else:  # Service
            if "amount" not in item:
                raise ValueError(
                    f"Line item {i}: 'amount' is required for Service layout orders."
                )
            line["Total"] = item["amount"]

        if "tax_code_id" in item:
            line["TaxCode"] = {"UID": item["tax_code_id"]}
        if "job_id" in item:
            line["Job"] = {"UID": item["job_id"]}

        lines.append(line)

    return lines


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
        return pick_list([fix_subtotal(i) for i in items], SALES_ORDER_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific sales order by its UID"
    )
    async def get_sales_order(
        ctx: Context,
        sales_order_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request("GET", f"/Sale/Order/{sales_order_id}")
        return pick(fix_subtotal(result), SALES_ORDER_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new sales order for a customer. "
        "Set order_layout to 'Item' (default) for quantity-based orders "
        "(line items need: description, ship_quantity, unit_price, total, account_id, "
        "optional tax_code_id, optional job_id), or 'Service' for amount-based orders "
        "(line items need: description, amount, account_id, optional tax_code_id, "
        "optional job_id). "
        "Use salesperson_id (employee UID) to assign a salesperson. "
        "Use customer_purchase_order_number for the customer's PO reference."
    )
    async def create_sales_order(
        ctx: Context,
        customer_id: str,
        date: str,
        line_items: list[dict[str, Any]],
        order_layout: str = "Item",
        number: str | None = None,
        comment: str | None = None,
        ship_to_address: str | None = None,
        is_tax_inclusive: bool | None = None,
        freight: float | None = None,
        customer_purchase_order_number: str | None = None,
        salesperson_id: str | None = None,
    ) -> dict[str, Any]:
        order_layout = order_layout.capitalize()
        if order_layout not in _VALID_LAYOUTS:
            raise ValueError(
                f"Invalid order_layout '{order_layout}'. Must be 'Item' or 'Service'."
            )

        app = ctx.request_context.lifespan_context

        lines = _build_lines(line_items, order_layout)

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
        if customer_purchase_order_number is not None:
            body["CustomerPurchaseOrderNumber"] = customer_purchase_order_number
        if salesperson_id is not None:
            body["Salesperson"] = {"UID": salesperson_id}

        result = await app.client.request(
            "POST", f"/Sale/Order/{order_layout}", json_body=body
        )
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result

    @mcp.tool(
        description="Edit/update an existing sales order. Only orders with status 'Open' "
        "can be edited. Set order_layout to match the order's layout: 'Item' (default) "
        "for quantity-based orders, or 'Service' for amount-based orders. "
        "Item line items need: description, ship_quantity, unit_price, total, account_id. "
        "Service line items need: description, amount, account_id. "
        "Both accept optional tax_code_id and job_id. "
        "Use salesperson_id (employee UID) to assign a salesperson. "
        "Use customer_purchase_order_number for the customer's PO reference."
    )
    async def edit_sales_order(
        ctx: Context,
        sales_order_id: str,
        order_layout: str = "Item",
        date: str | None = None,
        customer_id: str | None = None,
        line_items: list[dict[str, Any]] | None = None,
        number: str | None = None,
        comment: str | None = None,
        ship_to_address: str | None = None,
        is_tax_inclusive: bool | None = None,
        freight: float | None = None,
        customer_purchase_order_number: str | None = None,
        salesperson_id: str | None = None,
    ) -> dict[str, Any]:
        order_layout = order_layout.capitalize()
        if order_layout not in _VALID_LAYOUTS:
            raise ValueError(
                f"Invalid order_layout '{order_layout}'. Must be 'Item' or 'Service'."
            )

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

        actual_layout = current.get("Layout")
        if actual_layout and actual_layout != order_layout:
            raise ValueError(
                f"Layout mismatch: order has layout '{actual_layout}' but "
                f"order_layout='{order_layout}' was specified."
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
        if customer_purchase_order_number is not None:
            body["CustomerPurchaseOrderNumber"] = customer_purchase_order_number
        if salesperson_id is not None:
            body["Salesperson"] = {"UID": salesperson_id}

        if line_items is not None:
            body["Lines"] = _build_lines(line_items, order_layout)

        result = await app.client.request(
            "PUT", f"/Sale/Order/{order_layout}/{sales_order_id}", json_body=body
        )
        return pick(result, CREATE_RESULT_FIELDS) if isinstance(result, dict) else result
