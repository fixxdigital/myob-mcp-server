from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from ._filters import (
    pick_list,
    ATTACHMENT_LIST_FIELDS,
    ATTACHMENT_UPLOAD_RESULT_FIELDS,
)

ALLOWED_EXTENSIONS = {"pdf", "tiff", "tif", "jpg", "jpeg", "png"}
MAX_FILE_SIZE_BYTES = 3 * 1024 * 1024  # 3 MB
_VALID_BILL_LAYOUTS = {"Item", "Service"}


def _validate_attachment(file_name: str, file_base64_content: str) -> None:
    if not file_name or not file_name.strip():
        raise ValueError("file_name must not be empty.")
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '.{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if not file_base64_content or not file_base64_content.strip():
        raise ValueError("file_base64_content must not be empty.")
    approx_bytes = len(file_base64_content) * 3 / 4
    if approx_bytes > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File too large (~{approx_bytes / (1024 * 1024):.1f} MB). "
            f"Maximum is 3 MB."
        )


def _attachment_body(file_name: str, file_base64_content: str) -> dict[str, Any]:
    return {
        "Attachments": [
            {
                "OriginalFileName": file_name,
                "FileBase64Content": file_base64_content,
            }
        ]
    }


def _extract_attachments(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "Attachments" in result:
        return result["Attachments"]
    return []


def register(mcp: FastMCP) -> None:

    # -- Spend money attachment tools --

    @mcp.tool(
        description="Attach a file (receipt, invoice image, etc.) to a spend "
        "money transaction. The file must be base64-encoded. Accepted formats: "
        "PDF, TIFF, JPG, JPEG, PNG. Maximum size: 3 MB. "
        "Call multiple times to attach multiple files."
    )
    async def upload_spend_money_attachment(
        ctx: Context,
        transaction_id: str,
        file_name: str,
        file_base64_content: str,
    ) -> list[dict[str, Any]]:
        _validate_attachment(file_name, file_base64_content)
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "POST",
            f"/Banking/SpendMoneyTxn/{transaction_id}/Attachment",
            json_body=_attachment_body(file_name, file_base64_content),
        )
        return pick_list(_extract_attachments(result), ATTACHMENT_UPLOAD_RESULT_FIELDS)

    @mcp.tool(
        description="List file attachments on a spend money transaction. "
        "Returns attachment UIDs and original file names. "
        "Note: file content is not returned by the API."
    )
    async def list_spend_money_attachments(
        ctx: Context,
        transaction_id: str,
    ) -> list[dict[str, Any]]:
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET",
            f"/Banking/SpendMoneyTxn/{transaction_id}/Attachment",
        )
        return pick_list(_extract_attachments(result), ATTACHMENT_LIST_FIELDS)

    @mcp.tool(
        description="Remove a file attachment from a spend money transaction. "
        "Use list_spend_money_attachments to find the attachment UID first."
    )
    async def delete_spend_money_attachment(
        ctx: Context,
        transaction_id: str,
        attachment_id: str,
    ) -> dict[str, str]:
        app = ctx.request_context.lifespan_context
        await app.client.request(
            "DELETE",
            f"/Banking/SpendMoneyTxn/{transaction_id}/Attachment/{attachment_id}",
        )
        return {"status": "deleted", "attachment_id": attachment_id}

    # -- Bill attachment tools --

    @mcp.tool(
        description="Attach a file (receipt, invoice image, etc.) to a purchase "
        "bill. Set bill_layout to 'Item' (default) or 'Service' to match "
        "the bill's layout. Accepted formats: PDF, TIFF, JPG, JPEG, PNG. "
        "Maximum size: 3 MB. Call multiple times to attach multiple files."
    )
    async def upload_bill_attachment(
        ctx: Context,
        bill_id: str,
        file_name: str,
        file_base64_content: str,
        bill_layout: str = "Item",
    ) -> list[dict[str, Any]]:
        layout = bill_layout.capitalize()
        if layout not in _VALID_BILL_LAYOUTS:
            raise ValueError(
                f"Invalid bill_layout '{bill_layout}'. "
                f"Must be 'Item' or 'Service'."
            )
        _validate_attachment(file_name, file_base64_content)
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "POST",
            f"/Purchase/Bill/{layout}/{bill_id}/Attachment",
            json_body=_attachment_body(file_name, file_base64_content),
        )
        return pick_list(_extract_attachments(result), ATTACHMENT_UPLOAD_RESULT_FIELDS)

    @mcp.tool(
        description="List file attachments on a purchase bill. "
        "Set bill_layout to 'Item' (default) or 'Service' to match "
        "the bill's layout. Returns attachment UIDs and original file names."
    )
    async def list_bill_attachments(
        ctx: Context,
        bill_id: str,
        bill_layout: str = "Item",
    ) -> list[dict[str, Any]]:
        layout = bill_layout.capitalize()
        if layout not in _VALID_BILL_LAYOUTS:
            raise ValueError(
                f"Invalid bill_layout '{bill_layout}'. "
                f"Must be 'Item' or 'Service'."
            )
        app = ctx.request_context.lifespan_context
        result = await app.client.request(
            "GET",
            f"/Purchase/Bill/{layout}/{bill_id}/Attachment",
        )
        return pick_list(_extract_attachments(result), ATTACHMENT_LIST_FIELDS)

    @mcp.tool(
        description="Remove a file attachment from a purchase bill. "
        "Set bill_layout to 'Item' (default) or 'Service' to match "
        "the bill's layout. Use list_bill_attachments to find the "
        "attachment UID first."
    )
    async def delete_bill_attachment(
        ctx: Context,
        bill_id: str,
        attachment_id: str,
        bill_layout: str = "Item",
    ) -> dict[str, str]:
        layout = bill_layout.capitalize()
        if layout not in _VALID_BILL_LAYOUTS:
            raise ValueError(
                f"Invalid bill_layout '{bill_layout}'. "
                f"Must be 'Item' or 'Service'."
            )
        app = ctx.request_context.lifespan_context
        await app.client.request(
            "DELETE",
            f"/Purchase/Bill/{layout}/{bill_id}/Attachment/{attachment_id}",
        )
        return {"status": "deleted", "attachment_id": attachment_id}
