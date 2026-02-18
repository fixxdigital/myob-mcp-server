from __future__ import annotations

import time
from typing import Any

CACHE_TTL_ACCOUNTS = 1800  # 30 minutes
CACHE_TTL_TAX_CODES = 1800  # 30 minutes
CACHE_TTL_CONTACTS = 900  # 15 minutes
CACHE_TTL_COMPANY_FILES = 3600  # 1 hour


class TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self, default_ttl: float = 300) -> None:
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        expires_at = time.time() + (ttl if ttl is not None else self._default_ttl)
        self._store[key] = (expires_at, value)

    def invalidate(self, prefix: str = "") -> None:
        """Remove all entries whose key starts with prefix. Empty prefix clears all."""
        if not prefix:
            self._store.clear()
        else:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
