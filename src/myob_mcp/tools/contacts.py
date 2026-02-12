from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ..cache import CACHE_TTL_CONTACTS


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        description="Get all contacts (customers and suppliers). "
        "Can filter by contact type, active status, and search by name."
    )
    async def list_contacts(
        ctx: Context,
        contact_type: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context

        if contact_type == "Customer":
            path = "/Contact/Customer"
        elif contact_type == "Supplier":
            path = "/Contact/Supplier"
        else:
            path = "/Contact"

        params: dict[str, str] = {}
        filters: list[str] = []
        if is_active is not None:
            filters.append(f"IsActive eq {'true' if is_active else 'false'}")
        if search:
            filters.append(
                f"substringof('{search}', CompanyName) eq true"
            )
        if filters:
            params["$filter"] = " and ".join(filters)

        cache_key = f"contacts:{contact_type}:{is_active}:{search}"
        return await app.client.request_paged(
            path,
            params=params,
            cache_key=cache_key,
            cache_ttl=CACHE_TTL_CONTACTS,
        )

    @mcp.tool(
        description="Get detailed information about a specific contact by its UID"
    )
    async def get_contact(
        ctx: Context,
        contact_id: str,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context
        return await app.client.request("GET", f"/Contact/{contact_id}")

    @mcp.tool(
        description="Create a new contact (customer or supplier)"
    )
    async def create_contact(
        ctx: Context,
        display_name: str,
        contact_type: str,
        email: str | None = None,
        phone: str | None = None,
        address: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        app = ctx.request_context.lifespan_context

        if contact_type == "Customer":
            path = "/Contact/Customer"
        elif contact_type == "Supplier":
            path = "/Contact/Supplier"
        else:
            raise ValueError("contact_type must be 'Customer' or 'Supplier'")

        body: dict[str, Any] = {
            "CompanyName": display_name,
            "IsIndividual": False,
        }

        addresses: list[dict[str, Any]] = []
        addr_entry: dict[str, Any] = {"Location": 1}
        if email:
            addr_entry["Email"] = email
        if phone:
            addr_entry["Phone1"] = phone
        if address:
            if "street" in address:
                addr_entry["Street"] = address["street"]
            if "city" in address:
                addr_entry["City"] = address["city"]
            if "state" in address:
                addr_entry["State"] = address["state"]
            if "postcode" in address:
                addr_entry["PostCode"] = address["postcode"]
            if "country" in address:
                addr_entry["Country"] = address["country"]

        if len(addr_entry) > 1:  # More than just Location
            addresses.append(addr_entry)
            body["Addresses"] = addresses

        result = await app.client.request(
            "POST", path, json_body=body
        )
        app.client.cache.invalidate("contacts:")
        return result
