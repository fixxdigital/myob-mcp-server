from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    validate_date,
    pick,
    pick_list,
    CUSTOMER_PAYMENT_CREATE_RESULT_FIELDS,
    CUSTOMER_PAYMENT_DETAIL_FIELDS,
    CUSTOMER_PAYMENT_LIST_FIELDS,
    SALES_ORDER_DEPOSIT_CREATE_RESULT_FIELDS,
    SUPPLIER_PAYMENT_LIST_FIELDS,
    SUPPLIER_PAYMENT_DETAIL_FIELDS,
    SUPPLIER_PAYMENT_CREATE_RESULT_FIELDS,
)


_VALID_PAYMENT_METHODS = {
    "CreditCard",
    "Cash",
    "Cheque",
    "BankDeposit",
    "ElectronicPayments",
}


_VALID_SUPPLIER_PAYMENT_METHODS = {"Account", "ElectronicPayments"}


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get customer payments. Can filter by bank account, date range, "
        "and customer. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_customer_payments(
        ctx: Context,
        bank_account_id: str | None = None,
        customer_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if bank_account_id:
            filters.append(f"Account/UID eq guid'{bank_account_id}'")
        if customer_id:
            filters.append(f"Customer/UID eq guid'{customer_id}'")
        if date_from:
            validate_date(date_from, "date_from")
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            validate_date(date_to, "date_to")
            filters.append(f"Date le datetime'{date_to}'")
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        items = await app.client.request_paged(
            "/Sale/CustomerPayment", params=params, top=top
        )
        return pick_list(items, CUSTOMER_PAYMENT_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific customer payment "
        "by its UID"
    )
    async def get_customer_payment(
        ctx: Context,
        payment_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET", f"/Sale/CustomerPayment/{payment_id}"
        )
        return pick(result, CUSTOMER_PAYMENT_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new customer payment to record money received "
        "from a customer and apply it to one or more outstanding invoices. "
        "Each entry in the invoices array needs: invoice_id (the invoice UID) "
        "and amount_applied (the amount to apply to that invoice)."
    )
    async def create_customer_payment(
        ctx: Context,
        customer_id: str,
        payment_date: str,
        amount: float,
        bank_account_id: str,
        invoices: list[dict[str, Any]],
        memo: str | None = None,
        payment_method: str = "BankDeposit",
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        validate_date(payment_date, "payment_date")

        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be one of: {', '.join(sorted(_VALID_PAYMENT_METHODS))}."
            )

        if not invoices:
            raise ValueError("At least one invoice is required.")

        invoice_lines: list[dict[str, Any]] = []
        for i, inv in enumerate(invoices):
            if "invoice_id" not in inv:
                raise ValueError(
                    f"Invoice entry {i}: 'invoice_id' is required."
                )
            if "amount_applied" not in inv:
                raise ValueError(
                    f"Invoice entry {i}: 'amount_applied' is required."
                )
            invoice_lines.append({
                "UID": inv["invoice_id"],
                "AmountApplied": inv["amount_applied"],
            })

        body: dict[str, Any] = {
            "Customer": {"UID": customer_id},
            "Date": payment_date,
            "AmountReceived": amount,
            "Account": {"UID": bank_account_id},
            "PaymentMethod": payment_method,
            "Invoices": invoice_lines,
        }
        if memo:
            body["Memo"] = memo

        result = await app.client.request(
            "POST", "/Sale/CustomerPayment", json_body=body
        )
        app.client.cache.invalidate("invoices:")
        return (
            pick(result, CUSTOMER_PAYMENT_CREATE_RESULT_FIELDS)
            if isinstance(result, dict)
            else result
        )

    @mcp.tool(
        description="Record a customer deposit/prepayment against a sales order. "
        "Applies a payment to the specified sales order and deposits it into "
        "the given bank account."
    )
    async def create_sales_order_deposit(
        ctx: Context,
        sales_order_id: str,
        customer_id: str,
        payment_date: str,
        amount: float,
        bank_account_id: str,
        memo: str | None = None,
        payment_method: str = "BankDeposit",
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        validate_date(payment_date, "payment_date")

        if payment_method not in _VALID_PAYMENT_METHODS:
            raise ValueError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be one of: {', '.join(sorted(_VALID_PAYMENT_METHODS))}."
            )

        body: dict[str, Any] = {
            "Customer": {"UID": customer_id},
            "Date": payment_date,
            "AmountReceived": amount,
            "DepositTo": "Account",
            "Account": {"UID": bank_account_id},
            "PaymentMethod": payment_method,
            "Invoices": [
                {
                    "UID": sales_order_id,
                    "Type": "Order",
                    "AmountApplied": amount,
                },
            ],
        }
        if memo:
            body["Memo"] = memo

        result = await app.client.request(
            "POST", "/Sale/CustomerPayment", json_body=body
        )
        app.client.cache.invalidate("sales_orders:")
        return (
            pick(result, SALES_ORDER_DEPOSIT_CREATE_RESULT_FIELDS)
            if isinstance(result, dict)
            else result
        )

    @mcp.tool(
        description="Get supplier payments. Can filter by bank account, date range, "
        "and supplier. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_supplier_payments(
        ctx: Context,
        bank_account_id: str | None = None,
        supplier_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        if bank_account_id:
            filters.append("PayFrom eq 'Account'")
            filters.append(f"Account/UID eq guid'{bank_account_id}'")
        if supplier_id:
            filters.append(f"Supplier/UID eq guid'{supplier_id}'")
        if date_from:
            validate_date(date_from, "date_from")
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            validate_date(date_to, "date_to")
            filters.append(f"Date le datetime'{date_to}'")
        if filters:
            params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        items = await app.client.request_paged(
            "/Purchase/SupplierPayment", params=params, top=top
        )
        return pick_list(items, SUPPLIER_PAYMENT_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific supplier payment "
        "by its UID"
    )
    async def get_supplier_payment(
        ctx: Context,
        payment_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET", f"/Purchase/SupplierPayment/{payment_id}"
        )
        return pick(result, SUPPLIER_PAYMENT_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new supplier payment to record money paid to a "
        "supplier and apply it to one or more outstanding bills. Each entry in "
        "the bills array needs: bill_id (the bill UID) and amount_applied "
        "(the amount to apply to that bill)."
    )
    async def create_supplier_payment(
        ctx: Context,
        supplier_id: str,
        payment_date: str,
        amount: float,
        bank_account_id: str,
        bills: list[dict[str, Any]],
        memo: str | None = None,
        payment_method: str = "Account",
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        validate_date(payment_date, "payment_date")

        if payment_method not in _VALID_SUPPLIER_PAYMENT_METHODS:
            raise ValueError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be one of: {', '.join(sorted(_VALID_SUPPLIER_PAYMENT_METHODS))}."
            )

        if not bills:
            raise ValueError("At least one bill is required.")

        bill_lines: list[dict[str, Any]] = []
        for i, bill in enumerate(bills):
            if "bill_id" not in bill:
                raise ValueError(
                    f"Bill entry {i}: 'bill_id' is required."
                )
            if "amount_applied" not in bill:
                raise ValueError(
                    f"Bill entry {i}: 'amount_applied' is required."
                )
            bill_lines.append({
                "UID": bill["bill_id"],
                "AmountApplied": bill["amount_applied"],
            })

        body: dict[str, Any] = {
            "Supplier": {"UID": supplier_id},
            "Date": payment_date,
            "AmountPaid": amount,
            "PayFrom": payment_method,
            "Account": {"UID": bank_account_id},
            "Lines": bill_lines,
        }
        if memo:
            body["Memo"] = memo

        result = await app.client.request(
            "POST", "/Purchase/SupplierPayment", json_body=body
        )
        app.client.cache.invalidate("bills:")
        return (
            pick(result, SUPPLIER_PAYMENT_CREATE_RESULT_FIELDS)
            if isinstance(result, dict)
            else result
        )
