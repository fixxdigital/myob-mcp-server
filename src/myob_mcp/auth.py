from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import MyobConfig

logger = logging.getLogger(__name__)

AUTH_URL = "https://secure.myob.com/oauth2/account/authorize"
TOKEN_URL = "https://secure.myob.com/oauth2/v1/authorize"


class AuthError(Exception):
    pass


class MyobAuth:
    def __init__(self, config: MyobConfig) -> None:
        self._config = config
        self._tokens: dict[str, Any] | None = self._load_tokens()
        self._oauth_state: str | None = None

    @property
    def _token_file(self) -> Path:
        return Path(self._config.token_path)

    def _load_tokens(self) -> dict[str, Any] | None:
        path = self._token_file
        if not path.exists():
            return None
        try:
            with open(path) as f:
                tokens = json.load(f)
            logger.info("Loaded OAuth tokens from %s", path)
            return tokens
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load tokens: %s", e)
            return None

    def _save_tokens(self, tokens: dict[str, Any]) -> None:
        path = self._token_file
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(tokens, f, indent=2)
        logger.info("Saved OAuth tokens to %s", path)

    def get_authorization_url(self) -> str:
        self._oauth_state = secrets.token_urlsafe(32)
        scopes = " ".join(self._config.scopes)
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "prompt": "consent",
            "state": self._oauth_state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, business_id: str | None = None
    ) -> dict[str, Any]:
        payload = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "redirect_uri": self._config.redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(TOKEN_URL, data=payload, timeout=30.0)

        if resp.status_code != 200:
            raise AuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + int(data.get("expires_in", 1200)),
            "scope": data.get("scope", ""),
        }
        # Save businessId (company file GUID) from OAuth redirect
        if business_id:
            tokens["business_id"] = business_id
            logger.info("Captured company file ID (businessId): %s", business_id)
        self._tokens = tokens
        self._save_tokens(tokens)
        logger.info("OAuth authorization completed successfully")
        return tokens

    async def refresh_access_token(self) -> dict[str, Any]:
        if not self._tokens or not self._tokens.get("refresh_token"):
            raise AuthError("No refresh token available. Run oauth_authorize first.")

        payload = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self._tokens["refresh_token"],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(TOKEN_URL, data=payload, timeout=30.0)

        if resp.status_code != 200:
            raise AuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        tokens = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", self._tokens["refresh_token"]),
            "expires_at": time.time() + int(data.get("expires_in", 1200)),
            "scope": data.get("scope", ""),
        }
        # Preserve businessId across refreshes
        if self._tokens.get("business_id"):
            tokens["business_id"] = self._tokens["business_id"]
        self._tokens = tokens
        self._save_tokens(tokens)
        logger.info("OAuth token refreshed successfully")
        return tokens

    async def get_valid_token(self) -> str:
        if not self._tokens:
            raise AuthError("Not authenticated. Run oauth_authorize first.")

        # Refresh if token expires within 60 seconds
        if time.time() > self._tokens["expires_at"] - 60:
            await self.refresh_access_token()

        return self._tokens["access_token"]

    def get_token_status(self) -> dict[str, Any]:
        if not self._tokens:
            return {
                "authenticated": False,
                "message": "Not authenticated. Run oauth_authorize to connect.",
            }

        expires_at = self._tokens.get("expires_at", 0)
        expires_in = max(0, int(expires_at - time.time()))
        status: dict[str, Any] = {
            "authenticated": True,
            "expires_in_seconds": expires_in,
            "has_refresh_token": bool(self._tokens.get("refresh_token")),
        }
        if self._tokens.get("business_id"):
            status["company_file_id"] = self._tokens["business_id"]
        return status


async def run_oauth_callback_server(auth: MyobAuth, port: int = 33333) -> None:
    """Start a minimal HTTP server to capture the OAuth callback."""
    result: dict[str, Any] = {}
    event = asyncio.Event()

    async def handle_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            request_str = request_line.decode("utf-8", errors="replace")

            # Parse GET /callback?code=...&... HTTP/1.1
            parts = request_str.split(" ")
            if len(parts) >= 2:
                url = urlparse(parts[1])
                params = parse_qs(url.query)

                if "code" in params:
                    # Validate CSRF state parameter
                    callback_state = params.get("state", [None])[0]
                    expected_state = auth._oauth_state
                    auth._oauth_state = None  # Clear after use
                    if not callback_state or callback_state != expected_state:
                        logger.warning(
                            "OAuth state mismatch: possible CSRF attempt"
                        )
                        body = (
                            "<html><body><h1>Authorization Failed</h1>"
                            "<p>Invalid state parameter. "
                            "Please try authorizing again.</p></body></html>"
                        )
                        result["error"] = "OAuth state mismatch"
                    else:
                        code = params["code"][0]
                        business_id = params.get("businessId", [None])[0]
                        try:
                            await auth.exchange_code(
                                code, business_id=business_id
                            )
                            body = (
                                "<html><body>"
                                "<h1>Authorization Successful</h1>"
                                "<p>You can close this tab and "
                                "return to Claude.</p>"
                                "</body></html>"
                            )
                            result["success"] = True
                        except Exception as e:
                            body = (
                                f"<html><body>"
                                f"<h1>Authorization Failed</h1>"
                                f"<p>{e}</p></body></html>"
                            )
                            result["error"] = str(e)
                elif "error" in params:
                    error = params.get("error_description", params["error"])[0]
                    body = (
                        f"<html><body><h1>Authorization Failed</h1>"
                        f"<p>{error}</p></body></html>"
                    )
                    result["error"] = error
                else:
                    body = (
                        "<html><body><h1>Invalid Request</h1>"
                        "<p>No authorization code received.</p></body></html>"
                    )
                    result["error"] = "No authorization code in callback"

                response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{body}"
                )
                writer.write(response.encode())
                await writer.drain()
        finally:
            writer.close()
            event.set()

    server = await asyncio.start_server(handle_connection, "127.0.0.1", port)
    logger.info("OAuth callback server listening on port %d", port)

    try:
        await asyncio.wait_for(event.wait(), timeout=120)
    except asyncio.TimeoutError:
        raise AuthError("OAuth callback timed out after 120 seconds")
    finally:
        server.close()
        await server.wait_closed()

    if "error" in result:
        raise AuthError(result["error"])
