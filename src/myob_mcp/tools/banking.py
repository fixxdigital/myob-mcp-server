from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    validate_date,
    pick,
    pick_list,
    BANK_ACCOUNT_LIST_FIELDS,
    BANK_TXN_LIST_FIELDS,
    SPEND_MONEY_DETAIL_FIELDS,
    SPEND_MONEY_CREATE_RESULT_FIELDS,
)


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
        description="Get bank transactions for a specific bank account. "
        "Can filter by date range. Use top to limit results and orderby to sort "
        "(e.g. orderby='Date desc' for most recent first)."
    )
    async def list_bank_transactions(
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
            "/Banking/SpendMoneyTxn", params=params, top=top
        )
        return pick_list(items, BANK_TXN_LIST_FIELDS)

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
