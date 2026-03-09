from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    validate_date,
    pick,
    pick_list,
    BANK_ACCOUNT_LIST_FIELDS,
    SPEND_MONEY_DETAIL_FIELDS,
    SPEND_MONEY_CREATE_RESULT_FIELDS,
    RECEIVE_MONEY_LIST_FIELDS,
    RECEIVE_MONEY_DETAIL_FIELDS,
    RECEIVE_MONEY_CREATE_RESULT_FIELDS,
)


# ---------------------------------------------------------------------------
# Helpers for the unified list_bank_transactions tool
# ---------------------------------------------------------------------------


def _build_date_filters(
    date_from: str | None, date_to: str | None
) -> list[str]:
    """Build OData date range filter clauses."""
    parts: list[str] = []
    if date_from:
        validate_date(date_from, "date_from")
        parts.append(f"Date ge datetime'{date_from}'")
    if date_to:
        validate_date(date_to, "date_to")
        parts.append(f"Date le datetime'{date_to}'")
    return parts


def _contact_ref(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract {UID, Name} from a contact-like object, or return None."""
    if obj and "UID" in obj:
        return {"UID": obj["UID"], "Name": obj.get("Name", "")}
    return None


def _normalize_spend_money(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "UID": item.get("UID"),
        "Date": item.get("Date"),
        "Type": "SpendMoney",
        "TotalAmount": item.get("Amount"),
        "Memo": item.get("Memo"),
        "Contact": _contact_ref(item.get("Contact")),
        "Account": _contact_ref(item.get("Account")),
    }


def _normalize_receive_money(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "UID": item.get("UID"),
        "Date": item.get("Date"),
        "Type": "ReceiveMoney",
        "TotalAmount": item.get("AmountReceived"),
        "Memo": item.get("Memo"),
        "Contact": _contact_ref(item.get("Contact")),
        "Account": _contact_ref(item.get("Account")),
    }


def _normalize_customer_payment(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "UID": item.get("UID"),
        "Date": item.get("Date"),
        "Type": "CustomerPayment",
        "TotalAmount": item.get("AmountReceived"),
        "Memo": item.get("Memo"),
        "Contact": _contact_ref(item.get("Customer")),
        "Account": _contact_ref(item.get("Account")),
    }


def _normalize_supplier_payment(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "UID": item.get("UID"),
        "Date": item.get("Date"),
        "Type": "SupplierPayment",
        "TotalAmount": item.get("AmountPaid"),
        "Memo": item.get("Memo"),
        "Contact": _contact_ref(item.get("Supplier")),
        "Account": _contact_ref(item.get("Account")),
    }


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all bank accounts from the chart of accounts. "
        "Use top to limit results and orderby to sort."
    )
    async def list_bank_accounts(
        ctx: Context,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        if orderby:
            params["$orderby"] = orderby
        items = await app.client.request_paged(
            "/Banking/BankAccount", params=params or None, top=top
        )
        return pick_list(items, BANK_ACCOUNT_LIST_FIELDS)

    @mcp.tool(
        description="Get all bank transactions for a specific bank account. "
        "Returns all transaction types: spend money, receive money, "
        "customer payments, and supplier payments. Results are sorted by "
        "date descending (newest first). Can filter by date range. "
        "Use top to limit total results."
    )
    async def list_bank_transactions(
        ctx: Context,
        bank_account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        top: int | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        date_filters = _build_date_filters(date_from, date_to)
        acct_filter = f"Account/UID eq guid'{bank_account_id}'"

        spend_filter = " and ".join([acct_filter] + date_filters)
        receive_filter = " and ".join(
            ["DepositTo eq 'Account'", acct_filter] + date_filters
        )
        cust_pay_filter = " and ".join([acct_filter] + date_filters)
        supp_pay_filter = " and ".join(
            ["PayFrom eq 'Account'", acct_filter] + date_filters
        )

        spend_items, receive_items, cust_items, supp_items = (
            await asyncio.gather(
                app.client.request_paged(
                    "/Banking/SpendMoneyTxn",
                    params={"$filter": spend_filter},
                ),
                app.client.request_paged(
                    "/Banking/ReceiveMoneyTxn",
                    params={"$filter": receive_filter},
                ),
                app.client.request_paged(
                    "/Sale/CustomerPayment",
                    params={"$filter": cust_pay_filter},
                ),
                app.client.request_paged(
                    "/Purchase/SupplierPayment",
                    params={"$filter": supp_pay_filter},
                ),
            )
        )

        merged: list[dict[str, Any]] = []
        merged.extend(_normalize_spend_money(i) for i in spend_items)
        merged.extend(_normalize_receive_money(i) for i in receive_items)
        merged.extend(_normalize_customer_payment(i) for i in cust_items)
        merged.extend(_normalize_supplier_payment(i) for i in supp_items)

        merged.sort(key=lambda x: x.get("Date", ""), reverse=True)

        if top is not None:
            merged = merged[:top]

        return merged

    @mcp.tool(
        description="Get receive money (deposit) transactions for a specific "
        "bank account. Returns credit-side transactions (money received). "
        "Can filter by date range. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_receive_money_transactions(
        ctx: Context,
        bank_account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        top: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        params: dict[str, str] = {}
        filters: list[str] = []
        filters.append("DepositTo eq 'Account'")
        filters.append(f"Account/UID eq guid'{bank_account_id}'")
        if date_from:
            validate_date(date_from, "date_from")
            filters.append(f"Date ge datetime'{date_from}'")
        if date_to:
            validate_date(date_to, "date_to")
            filters.append(f"Date le datetime'{date_to}'")
        params["$filter"] = " and ".join(filters)
        if orderby:
            params["$orderby"] = orderby

        items = await app.client.request_paged(
            "/Banking/ReceiveMoneyTxn", params=params, top=top
        )
        return pick_list(items, RECEIVE_MONEY_LIST_FIELDS)

    @mcp.tool(
        description="Get detailed information about a specific receive money "
        "transaction by its UID"
    )
    async def get_receive_money_transaction(
        ctx: Context,
        transaction_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET", f"/Banking/ReceiveMoneyTxn/{transaction_id}"
        )
        return pick(result, RECEIVE_MONEY_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new receive money transaction. Records money "
        "received into a bank account. Each line item allocates part of the "
        "receipt to an income or liability account. Line items need: account_id "
        "(income/liability account UID), amount. Optional per-line: description, "
        "tax_code_id, job_id."
    )
    async def create_receive_money_transaction(
        ctx: Context,
        bank_account_id: str,
        date: str,
        line_items: list[dict[str, Any]],
        contact_id: str | None = None,
        memo: str | None = None,
        is_tax_inclusive: bool | None = None,
        payment_method: str = "Account",
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        valid_methods = {"Account", "ElectronicPayments"}
        if payment_method not in valid_methods:
            raise ValueError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be 'Account' or 'ElectronicPayments'."
            )

        lines: list[dict[str, Any]] = []
        for i, item in enumerate(line_items):
            if "account_id" not in item:
                raise ValueError(f"Line item {i}: 'account_id' is required.")
            if "amount" not in item:
                raise ValueError(f"Line item {i}: 'amount' is required.")
            line: dict[str, Any] = {
                "Account": {"UID": item["account_id"]},
                "Amount": item["amount"],
            }
            if "description" in item:
                line["Memo"] = item["description"]
            if "tax_code_id" in item:
                line["TaxCode"] = {"UID": item["tax_code_id"]}
            if "job_id" in item:
                line["Job"] = {"UID": item["job_id"]}
            lines.append(line)

        body: dict[str, Any] = {
            "Date": date,
            "DepositTo": "Account",
            "Account": {"UID": bank_account_id},
            "PaymentMethod": payment_method,
            "Lines": lines,
        }
        if contact_id:
            body["Contact"] = {"UID": contact_id}
        if memo:
            body["Memo"] = memo
        if is_tax_inclusive is not None:
            body["IsTaxInclusive"] = is_tax_inclusive

        result = await app.client.request(
            "POST", "/Banking/ReceiveMoneyTxn", json_body=body
        )
        app.client.cache.invalidate("banking:")
        return (
            pick(result, RECEIVE_MONEY_CREATE_RESULT_FIELDS)
            if isinstance(result, dict)
            else result
        )

    @mcp.tool(
        description="Get detailed information about a specific spend money "
        "transaction by its UID"
    )
    async def get_spend_money_transaction(
        ctx: Context,
        transaction_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET", f"/Banking/SpendMoneyTxn/{transaction_id}"
        )
        return pick(result, SPEND_MONEY_DETAIL_FIELDS)

    @mcp.tool(
        description="Create a new spend money transaction. Records money paid "
        "out from a bank account. Each line item allocates part of the spend "
        "to an expense or asset account. Line items need: account_id "
        "(expense/asset account UID), amount. Optional per-line: description, "
        "tax_code_id, job_id."
    )
    async def create_spend_money_transaction(
        ctx: Context,
        bank_account_id: str,
        date: str,
        line_items: list[dict[str, Any]],
        contact_id: str | None = None,
        memo: str | None = None,
        is_tax_inclusive: bool | None = None,
        payment_method: str = "Account",
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        valid_methods = {"Account", "ElectronicPayments"}
        if payment_method not in valid_methods:
            raise ValueError(
                f"Invalid payment_method '{payment_method}'. "
                f"Must be 'Account' or 'ElectronicPayments'."
            )

        lines: list[dict[str, Any]] = []
        for i, item in enumerate(line_items):
            if "account_id" not in item:
                raise ValueError(f"Line item {i}: 'account_id' is required.")
            if "amount" not in item:
                raise ValueError(f"Line item {i}: 'amount' is required.")
            line: dict[str, Any] = {
                "Account": {"UID": item["account_id"]},
                "Amount": item["amount"],
            }
            if "description" in item:
                line["Memo"] = item["description"]
            if "tax_code_id" in item:
                line["TaxCode"] = {"UID": item["tax_code_id"]}
            if "job_id" in item:
                line["Job"] = {"UID": item["job_id"]}
            lines.append(line)

        body: dict[str, Any] = {
            "Date": date,
            "PayFrom": payment_method,
            "Account": {"UID": bank_account_id},
            "Lines": lines,
        }
        if contact_id:
            body["Contact"] = {"UID": contact_id}
        if memo:
            body["Memo"] = memo
        if is_tax_inclusive is not None:
            body["IsTaxInclusive"] = is_tax_inclusive

        result = await app.client.request(
            "POST", "/Banking/SpendMoneyTxn", json_body=body
        )
        app.client.cache.invalidate("banking:")
        return (
            pick(result, SPEND_MONEY_CREATE_RESULT_FIELDS)
            if isinstance(result, dict)
            else result
        )
