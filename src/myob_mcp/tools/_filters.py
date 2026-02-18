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


# ---------------------------------------------------------------------------
# Field specs — whitelists per entity type and operation
# ---------------------------------------------------------------------------

_CUSTOMER_REF: dict[str, Any] = {"UID": True, "Name": True}
_SUPPLIER_REF: dict[str, Any] = {"UID": True, "Name": True}
_TAXCODE_REF: dict[str, Any] = {"UID": True, "Code": True}
_ACCOUNT_REF: dict[str, Any] = {"UID": True, "Name": True}

# -- List tool specs (aggressive) --

ACCOUNT_LIST_FIELDS: dict[str, Any] = {
    "UID": True,
    "Name": True,
    "Number": True,
    "Type": True,
    "IsActive": True,
    "Classification": True,
    "CurrentBalance": True,
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

_INVOICE_LINE: dict[str, Any] = {
    "Description": True,
    "Quantity": True,
    "UnitPrice": True,
    "Total": True,
    "TaxCode": _TAXCODE_REF,
    "Account": _ACCOUNT_REF,
}

INVOICE_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "BalanceDueDate": True,
    "Status": True,
    "Customer": _CUSTOMER_REF,
    "Lines": _INVOICE_LINE,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "BalanceDueAmount": True,
    "Comment": True,
    "IsTaxInclusive": True,
    "JournalMemo": True,
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
    "Amount": True,
    "TaxCode": _TAXCODE_REF,
    "Account": _ACCOUNT_REF,
}

SALES_ORDER_DETAIL_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Date": True,
    "Status": True,
    "Customer": _CUSTOMER_REF,
    "Lines": _SALES_ORDER_LINE,
    "Subtotal": True,
    "TotalTax": True,
    "TotalAmount": True,
    "Comment": True,
    "ShipToAddress": True,
    "IsTaxInclusive": True,
    "Freight": True,
}

# -- Create/edit confirmation (most aggressive) --

CREATE_RESULT_FIELDS: dict[str, Any] = {
    "UID": True,
    "Number": True,
    "Status": True,
    "CompanyName": True,
    "Type": True,
}
