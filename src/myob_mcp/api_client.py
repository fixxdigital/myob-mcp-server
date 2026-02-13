from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .auth import MyobAuth
from .cache import TTLCache
from .config import MyobConfig

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.myob.com/accountright"


class MyobApiError(Exception):
    def __init__(self, status_code: int, message: str, response_body: str = "") -> None:
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"MYOB API Error {status_code}: {message}")


class MyobApiClient:
    def __init__(
        self, config: MyobConfig, auth: MyobAuth, cache: TTLCache
    ) -> None:
        self.config = config
        self.auth = auth
        self.cache = cache
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _build_url(self, path: str, company_file_id: str | None) -> str:
        if company_file_id:
            return f"{API_BASE_URL}/{company_file_id}{path}"
        return f"{API_BASE_URL}/"

    def _resolve_company_file_id(
        self, company_file_id: str | None, required: bool = True
    ) -> str | None:
        cfid = (
            company_file_id
            or self.config.default_company_file_id
            or (self.auth._tokens or {}).get("business_id", "")
        )
        if required and not cfid:
            raise ValueError(
                "No company file ID available. "
                "Re-run oauth_authorize to capture the company file ID, "
                "or set default_company_file_id in config."
            )
        return cfid

    async def _build_headers(self) -> dict[str, str]:
        token = await self.auth.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "x-myobapi-key": self.config.client_id,
            "x-myobapi-version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        company_file_id: str | None = None,
        require_company_file: bool = True,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_ttl: float | None = None,
    ) -> Any:
        # Check cache first
        if cache_key:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        cfid = self._resolve_company_file_id(
            company_file_id, required=require_company_file
        )
        url = self._build_url(path, cfid)

        max_retries = 3
        for attempt in range(max_retries + 1):
            headers = await self._build_headers()
            client = self._get_client()

            try:
                resp = await client.request(
                    method, url, headers=headers, params=params, json=json_body
                )
            except httpx.RequestError as e:
                if attempt < max_retries:
                    wait = 0.5 * (2**attempt)
                    logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                    await asyncio.sleep(wait)
                    continue
                raise MyobApiError(0, f"Request failed: {e}")

            if resp.status_code == 401 and attempt < max_retries:
                logger.info("Got 401, refreshing token and retrying")
                await self.auth.refresh_access_token()
                continue

            if resp.status_code == 429 and attempt < max_retries:
                wait = 0.5 * (2**attempt)
                logger.warning("Rate limited, waiting %.1fs", wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 500 and attempt < max_retries:
                wait = 0.5 * (2**attempt)
                logger.warning("Server error %d, retrying in %.1fs", resp.status_code, wait)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 400:
                raise MyobApiError(
                    resp.status_code,
                    f"{method} {path} failed",
                    resp.text,
                )

            # 200-299 success
            if resp.status_code == 204:
                result = None
            else:
                result = resp.json()

            logger.debug("Response from %s: status=%d body_type=%s", url, resp.status_code, type(result).__name__)

            if cache_key and cache_ttl:
                self.cache.set(cache_key, result, cache_ttl)

            return result

        raise MyobApiError(0, "Max retries exceeded")

    async def request_paged(
        self,
        path: str,
        *,
        company_file_id: str | None = None,
        params: dict[str, str] | None = None,
        max_items: int = 1000,
        cache_key: str | None = None,
        cache_ttl: float | None = None,
    ) -> list[dict[str, Any]]:
        # Check cache first
        if cache_key:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        all_items: list[dict[str, Any]] = []
        page_params = dict(params or {})
        page_params["$top"] = "400"
        skip = 0

        while True:
            if skip > 0:
                page_params["$skip"] = str(skip)

            result = await self.request(
                "GET",
                path,
                company_file_id=company_file_id,
                params=page_params,
            )

            # MYOB returns items as a JSON array or in an Items field
            if isinstance(result, list):
                items = result
            elif isinstance(result, dict) and "Items" in result:
                items = result["Items"]
            else:
                items = [result] if result else []

            all_items.extend(items)

            if len(items) < 400 or len(all_items) >= max_items:
                break

            skip += 400

        if cache_key and cache_ttl:
            self.cache.set(cache_key, all_items, cache_ttl)

        return all_items

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
