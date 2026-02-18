from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    from . import accounts, banking, bills, company, contacts, invoices, oauth, sales_orders, tax_codes

    oauth.register(mcp)
    company.register(mcp)
    accounts.register(mcp)
    tax_codes.register(mcp)
    contacts.register(mcp)
    invoices.register(mcp)
    bills.register(mcp)
    banking.register(mcp)
    sales_orders.register(mcp)
