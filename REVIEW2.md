# MYOB MCP Server - Code Review (Round 2)

## Bugs / Correctness

### ~~1. `create_contact` always creates company contacts, never individuals~~ FIXED
**Severity:** Medium
**Files:** `contacts.py`, `_filters.py`

Every contact is created with `IsIndividual: False` and the `display_name` param is mapped to `CompanyName`. There is no way to create an individual contact (which uses `FirstName`/`LastName` instead). If an LLM is asked to create "John Smith" as a customer, it will silently create a company named "John Smith".

**Fix:** Added `is_individual`, `first_name`, `last_name` params. When `is_individual=True`, uses `FirstName`/`LastName` from explicit params or falls back to splitting `display_name`. Extended `CREATE_RESULT_FIELDS` with `FirstName`, `LastName`, `IsIndividual`.

---

### ~~2. Jobs search is case-sensitive (inconsistent with contacts/employees)~~ FIXED
**Severity:** Medium
**Files:** `jobs.py`

The jobs `substringof` filter doesn't wrap either side in `tolower()`, unlike `contacts.py` and `employees.py` which do. Searching for "marketing" won't match a job named "Marketing".

**Fix:** Applied `.lower()` to escaped search term and wrapped `Name`/`Number` in `tolower()`, matching the contacts/employees pattern.

---

### 3. Invoice/bill/sales order number search is case-sensitive
**Severity:** Low
**Files:** `invoices.py:50`, `bills.py:50`, `sales_orders.py:96`

The `substringof` filter on `Number` doesn't use `tolower()`. Less impactful since invoice numbers are usually alphanumeric, but inconsistent with the contacts/employees pattern.

**Fix:** Wrap in `tolower()` for consistency, same as the jobs fix above.

---

### ~~4. `edit_sales_order` echoes full API response back on PUT~~ FIXED
**Severity:** Medium
**Files:** `sales_orders.py`

This shallow-copied the entire GET response (including URI, nested object URIs, and potentially read-only fields) and sent it all back on PUT. MYOB may reject unexpected or read-only fields with a 400 error.

**Fix:** Added `_PUT_SAFE_FIELDS` whitelist and `_strip_uris()` helper. PUT body is now built from whitelisted mutable fields only, with nested `URI` keys recursively stripped.

---

### 5. `create_invoice`/`create_bill` don't validate `date`/`due_date`
**Severity:** Low
**Files:** `invoices.py:76-82`, `bills.py:76-82`

The `list_*` tools validate dates with `validate_date()`, but `create_invoice` and `create_bill` accept `date` and `due_date` without validation. Invalid dates only fail at the MYOB API level with opaque errors.

**Fix:** Add `validate_date(date, "date")` and `validate_date(due_date, "due_date")` at the start of both create functions.

---

### 6. UID params (`account_id`, `customer_id`, etc.) are never validated
**Severity:** Low
**Files:** Throughout all tools

IDs like `customer_id`, `supplier_id`, `account_id`, `invoice_id` etc. are passed directly to MYOB as `{"UID": value}` or interpolated into URL paths. A typo or garbage string produces a confusing MYOB error.

**Fix:** Add a simple UUID format check helper and apply it to all `*_id` params for clearer error messages.

---

### 7. `bank_account_id` not escaped in OData filter
**Severity:** Low
**Files:** `banking.py:51`

```python
filters.append(f"Account/UID eq guid'{bank_account_id}'")
```

The ID is interpolated directly without `escape_odata()`. Same pattern in `invoices.py:48` (`customer_id`), `bills.py:48` (`supplier_id`), and `sales_orders.py:94` (`customer_id`). Low risk since GUIDs shouldn't contain quotes, but inconsistent with the `search` param handling.

**Fix:** Either escape all interpolated values, or validate them as UUIDs (see #6).

---

### 8. Unused variable in `oauth_refresh`
**Severity:** Low
**Files:** `oauth.py:42`

```python
tokens = await app.auth.refresh_access_token()
```

The return value is captured but never used. The tool returns a hardcoded success message.

**Fix:** Either drop the variable (`await app.auth.refresh_access_token()`) or return useful info from `tokens` (e.g. `expires_in`).

---

## Efficiency

### 9. New `httpx.AsyncClient` created for every token exchange/refresh
**Severity:** Medium
**Files:** `auth.py:79, 111`

```python
async with httpx.AsyncClient() as client:
    resp = await client.post(TOKEN_URL, data=payload, timeout=30.0)
```

Each OAuth operation creates and tears down a fresh HTTP client. The server already maintains a persistent `httpx.AsyncClient` in `MyobApiClient`. Reusing a shared client would benefit from connection pooling and avoid TCP setup overhead on every token refresh (which happens every 20 minutes).

**Fix:** Pass a shared `httpx.AsyncClient` into `MyobAuth`, or give `MyobAuth` its own persistent client that gets closed in the lifespan teardown.

---

### 10. `_build_headers` called on every retry attempt
**Severity:** Low
**Files:** `api_client.py:105`

Inside the retry loop, `await self._build_headers()` is called on every iteration. This calls `get_valid_token()` which may trigger a redundant token refresh check. Only the 401 path actually needs to rebuild headers.

**Fix:** Build headers before the loop. Only rebuild after a 401 retry.

---

### 11. No caching on `list_bank_accounts`
**Severity:** Low
**Files:** `banking.py:30-32`

`list_bank_accounts` calls `request_paged` without `cache_key` or `cache_ttl`. Bank accounts rarely change, so this is an easy caching win — similar to accounts, tax codes, and jobs which are all cached.

**Fix:** Add `cache_key` and `cache_ttl` (e.g. `CACHE_TTL_ACCOUNTS`) to the `list_bank_accounts` call.

---

### 12. Token file I/O is synchronous
**Severity:** Low
**Files:** `auth.py:41, 53`

`_load_tokens` and `_save_tokens` use synchronous `open()` in an async server. For a small JSON file this is negligible but technically blocks the event loop.

**Fix:** Use `asyncio.to_thread()` or `aiofiles` if this ever becomes a concern. Low priority.

---

## Design / Robustness

### 13. `_resolve_company_file_id` accesses private `auth._tokens`
**Severity:** Low
**Files:** `api_client.py:54`

```python
or (self.auth._tokens or {}).get("business_id", "")
```

This breaks encapsulation by reaching into the auth module's private state. The auth module already has `get_token_status()` which exposes `company_file_id`.

**Fix:** Add a public `auth.get_business_id()` method and use it instead.

---

### 14. Duplicate default scope lists
**Severity:** Low
**Files:** `config.py:20-29`, `config.py:88-97`

The default scopes list is defined twice: once in the `MyobConfig` dataclass default and once in `load_config()`'s `data.get("scopes", [...])` fallback. Adding a new scope requires updating both places.

**Fix:** Extract to a module-level constant (e.g. `DEFAULT_SCOPES`) and reference it in both locations.

---

### 15. Config env var substitution silently leaves unresolved placeholders
**Severity:** Low
**Files:** `config.py:41-53`
*(Carried from REVIEW.md #7)*

If an env var doesn't exist, `${UNDEFINED_VAR}` stays as the literal string in the config value. This was the root cause of 400 errors in testing when `${MYOB_COMPANY_FILE_ID}` ended up in API URLs.

**Fix:** After substitution, scan for remaining `${...}` patterns and log a warning.

---

### 16. Error response body truncated at 500 chars
**Severity:** Low
**Files:** `api_client.py:24-25`
*(Carried from REVIEW.md #8)*

`MyobApiError` truncates the response body at 500 characters. Usually fine but could hide detail on verbose MYOB validation errors.

**Fix:** Consider increasing to 1000 chars, or log the full body at DEBUG level before truncating.

---

### 17. Token refresh 60s buffer adds latency in burst scenarios
**Severity:** Low
**Files:** `auth.py:137`
*(Carried from REVIEW.md #9)*

Every request within 60s of token expiry triggers a refresh. Fine for low-throughput MCP but adds latency if multiple tools are called in quick succession.

**Fix:** Use a lock to prevent concurrent refreshes, or reduce the buffer to 30s.

---

### 18. Banking endpoint only covers SpendMoneyTxn
**Severity:** Low
**Files:** `banking.py:63`
*(Carried from REVIEW.md #10)*

`list_bank_transactions` only queries `/Banking/SpendMoneyTxn`, which returns spend-money transactions only — not receipts (`ReceiveMoneyTxn`), transfers (`TransferMoney`), or other transaction types.

**Fix:** Either rename to `list_spend_transactions` for clarity, or add additional tools for other transaction types (`list_receive_transactions`, `list_transfers`).

---

## Summary

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| ~~1~~ | ~~`create_contact` can't create individuals~~ | ~~Medium~~ | ~~Bug~~ | **FIXED** |
| ~~2~~ | ~~Jobs search is case-sensitive~~ | ~~Medium~~ | ~~Bug~~ | **FIXED** |
| 3 | Invoice/bill/order number search case-sensitive | Low | Bug |
| ~~4~~ | ~~`edit_sales_order` echoes full response on PUT~~ | ~~Medium~~ | ~~Bug~~ | **FIXED** |
| 5 | Create invoice/bill missing date validation | Low | Bug |
| 6 | UID params never validated | Low | Bug |
| 7 | ID params not escaped in OData filters | Low | Bug |
| 8 | Unused variable in `oauth_refresh` | Low | Bug |
| 9 | New HTTP client per token operation | Medium | Efficiency |
| 10 | Headers rebuilt on every retry | Low | Efficiency |
| 11 | No caching on `list_bank_accounts` | Low | Efficiency |
| 12 | Synchronous token file I/O | Low | Efficiency |
| 13 | API client accesses private `auth._tokens` | Low | Design |
| 14 | Duplicate default scope lists | Low | Design |
| 15 | Unresolved env var placeholders silent | Low | Design |
| 16 | Error body truncated at 500 chars | Low | Design |
| 17 | Token refresh 60s buffer / no concurrency guard | Low | Design |
| 18 | Banking only covers SpendMoneyTxn | Low | Design |
