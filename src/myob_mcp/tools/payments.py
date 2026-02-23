from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    validate_date,
    pick,
    CUSTOMER_PAYMENT_CREATE_RESULT_FIELDS,
    SALES_ORDER_DEPOSIT_CREATE_RESULT_FIELDS,
)


_VALID_PAYMENT_METHODS = {
    "CreditCard",
    "Cash",
    "Cheque",
    "BankDeposit",
    "ElectronicPayments",
}


def register(mcp: FastMCP) -> None:

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
