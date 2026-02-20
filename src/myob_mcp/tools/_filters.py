from __future__ import annotations

import re
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def escape_odata(value: str) -> str:
    """Escape single quotes for OData string literals."""
    return value.replace("'", "''")


def validate_date(value: str, param_name: str) -> str:
    """Validate ISO 8601 date format (YYYY-MM-DD)."""
    if not _DATE_RE.match(value):
        raise ValueError(
            f"Invalid date format for {param_name}: '{value}'. Expected YYYY-MM-DD."
        )
    return value


# ---------------------------------------------------------------------------
# Response filtering — whitelist-based field extraction
# ---------------------------------------------------------------------------

_STRIP_KEYS = {"URI", "RowVersion"}


def pick(obj: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Keep only whitelisted fields from a dict, recursively.

    ``fields`` maps key names to either:
    - ``True``   — keep the value as-is
    - a ``dict`` — recurse into the nested object (or each item if it's a list)
    """
    out: dict[str, Any] = {}
    for key, spec in fields.items():
        if key not in obj:
            continue
        val = obj[key]
        if spec is True:
            out[key] = val
        elif isinstance(spec, dict):
            if isinstance(val, dict):
                out[key] = pick(val, spec)
            elif isinstance(val, list):
                out[key] = [pick(item, spec) for item in val if isinstance(item, dict)]
    return out


def pick_list(items: list[dict[str, Any]], fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply ``pick`` to every item in a list."""
    return [pick(item, fields) for item in items]


def fix_subtotal(item: dict[str, Any]) -> dict[str, Any]:
    """Correct Subtotal to always be the pre-tax (exclusive) amount.

    When IsTaxInclusive is True, MYOB sets Subtotal equal to TotalAmount
    (the tax-inclusive total). This corrects it to TotalAmount - TotalTax
    so callers always receive the pre-tax subtotal regardless of tax mode.
    """
    if item.get("IsTaxInclusive"):
        total = item.get("TotalAmount") or 0
        tax = item.get("TotalTax") or 0
        return {**item, "Subtotal": round(total - tax, 2)}
    return item


def strip_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    """Remove URI and RowVersion from top-level keys."""
    return {k: v for k, v in obj.items() if k not in _STRIP_KEYS}


def build_lines(
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
                        f"Line item {i}: '{field}' is required for Item layout."
                    )
            line["ShipQuantity"] = item["ship_quantity"]
            line["UnitPrice"] = item["unit_price"]
            line["Total"] = item["total"]
        else:  # Service
            if "amount" not in item:
                raise ValueError(
                    f"Line item {i}: 'amount' is required for Service layout."
                )
            line["Total"] = item["amount"]

        if "tax_code_id" in item:
            line["TaxCode"] = {"UID": item["tax_code_id"]}
        if "job_id" in item:
            line["Job"] = {"UID": item["job_id"]}

        lines.append(line)

    return lines


# ---------------------------------------------------------------------------
# Field specs — whitelists per entity type and operation
# ---------------------------------------------------------------------------

_CUSTOMER_REF: dict[str, Any] = {"UID": True, "Name": True}
_SUPPLIER_REF: dict[str, Any] = {"UID": True, "Name": True}
_EMPLOYEE_REF: dict[str, Any] = {"UID": True, "Name": True}
_TAXCODE_REF: dict[str, Any] = {"UID": True, "Code": True}
_ACCOUNT_REF: dict[str, Any] = {"UID": True, "Name": True}
_JOB_REF: dict[str, Any] = {"UID": True, "Number": True, "Name": True}

# -- List tool specs (aggressive) --

ACCOUNT_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Name": True,
    "DisplayID": True,
    "Number": True,
    "Type": True,
    "IsActive": True,
    "Classification": True,
    "CurrentBalance": True,
}

TAX_CODE_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Code": True,
    "Description": True,
    "Type": True,
    "Rate": True,
}

CONTACT_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "CompanyName": True,
    "FirstName": True,
    "LastName": True,
    "IsIndividual": True,
    "IsActive": True,
    "Type": True,
}

EMPLOYEE_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "DisplayID": True,
    "FirstName": True,
    "LastName": True,
    "IsActive": True,
}

JOB_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Name": True,
    "IsActive": True,
    "Description": True,
}

INVOICE_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "Status": True,
    "Customer": _CUSTOMER_REF,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "BalanceDueAmount": True,
}

BILL_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "Status": True,
    "Supplier": _SUPPLIER_REF,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "BalanceDueAmount": True,
}

SALES_ORDER_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "Status": True,
    "Customer": _CUSTOMER_REF,
    "Salesperson": _EMPLOYEE_REF,
    "CustomerPurchaseOrderNumber": True,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
}

BANK_ACCOUNT_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Name": True,
    "Number": True,
    "CurrentBalance": True,
    "IsActive": True,
    "BSBNumber": True,
}

BANK_TXN_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Date": True,
    "Amount": True,
    "Description": True,
    "Memo": True,
    "PayeeName": True,
    "Account": _ACCOUNT_REF,
}

# -- Get/detail tool specs (moderate) --

_SPEND_MONEY_LINE: dict[str, Any] = {
    "Amount": True,
    "Memo": True,
    "Account": _ACCOUNT_REF,
    "TaxCode": _TAXCODE_REF,
    "Job": _JOB_REF,
}

SPEND_MONEY_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "PaymentNumber": True,
    "Date": True,
    "PayFrom": True,
    "Account": _ACCOUNT_REF,
    "Contact": {"UID": True, "Name": True, "Type": True},
    "Memo": True,
    "Lines": _SPEND_MONEY_LINE,
    "Amount": True,
    "IsTaxInclusive": True,
    "TotalTax": True,
}

SPEND_MONEY_CREATE_RESULT_FIELDS: dict[str, Any] = {
    "UID": True,
    "PaymentNumber": True,
    "Date": True,
    "Amount": True,
    "Memo": True,
    "Account": _ACCOUNT_REF,
}

_INVOICE_LINE: dict[str, Any] = {
    "Type": True,
    "Description": True,
    "ShipQuantity": True,   # Item layout
    "UnitCount": True,      # Service layout
    "UnitPrice": True,
    "Total": True,
    "TaxCode": _TAXCODE_REF,
    "Account": _ACCOUNT_REF,
    "Job": _JOB_REF,
}

INVOICE_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "BalanceDueDate": True,
    "Status": True,
    "Layout": True,
    "Customer": _CUSTOMER_REF,
    "Lines": _INVOICE_LINE,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "BalanceDueAmount": True,
    "Comment": True,
    "IsTaxInclusive": True,
    "JournalMemo": True,
    "ShipToAddress": True,
    "CustomerPurchaseOrderNumber": True,
    "Salesperson": _EMPLOYEE_REF,
}

_BILL_LINE: dict[str, Any] = {
    "Description": True,
    "Quantity": True,
    "UnitPrice": True,
    "Total": True,
    "TaxCode": _TAXCODE_REF,
    "Account": _ACCOUNT_REF,
}

BILL_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "BalanceDueDate": True,
    "Status": True,
    "Supplier": _SUPPLIER_REF,
    "Lines": _BILL_LINE,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "BalanceDueAmount": True,
    "Comment": True,
    "IsTaxInclusive": True,
    "JournalMemo": True,
}

_SALES_ORDER_LINE: dict[str, Any] = {
    "Type": True,
    "Description": True,
    "ShipQuantity": True,
    "UnitPrice": True,
    "Total": True,
    "TaxCode": _TAXCODE_REF,
    "Account": _ACCOUNT_REF,
    "Job": _JOB_REF,
}

SALES_ORDER_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "Status": True,
    "Customer": _CUSTOMER_REF,
    "Salesperson": _EMPLOYEE_REF,
    "CustomerPurchaseOrderNumber": True,
    "Lines": _SALES_ORDER_LINE,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "Comment": True,
    "ShipToAddress": True,
    "IsTaxInclusive": True,
    "BalanceDueDate": True,
}

# -- Create/edit confirmation (most aggressive) --

CREATE_RESULT_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Status": True,
    "CompanyName": True,
    "FirstName": True,
    "LastName": True,
    "IsIndividual": True,
    "Type": True,
}

ATTACHMENT_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "OriginalFileName": True,
}

ATTACHMENT_UPLOAD_RESULT_FIELDS: dict[str, Any] = {
    "UID": True,
    "OriginalFileName": True,
}
