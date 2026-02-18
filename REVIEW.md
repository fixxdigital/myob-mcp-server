# MYOB MCP Server - Codebase Review

## High Priority

### 1. OData Injection via single quotes in search params
**Status:** Fixed
**Files:** `contacts.py:37`, `invoices.py:37`, `bills.py:37`, `sales_orders.py:37`

All `search` and `substringof` filters interpolate user input directly into OData filter strings. A search for `O'Brien` produces invalid OData: `substringof('O'Brien', CompanyName) eq true`.

**Fix:** Escape single quotes by doubling them (`'` → `''`) in all OData string interpolations.

---

### 2. No input validation on date params
**Status:** Fixed
**Files:** `invoices.py:28-31`, `bills.py:28-31`, `sales_orders.py:28-31`, `banking.py:44-47`

`date_from`/`date_to` are interpolated into OData `datetime'...'` expressions without format validation. Invalid strings produce confusing 400 errors from MYOB instead of clear client-side errors.

**Fix:** Validate ISO 8601 date format (YYYY-MM-DD) before including in filters.

---

### 3. Missing RowVersion validation in edit_sales_order
**Status:** Fixed
**Files:** `sales_orders.py:125`

The code copies the fetched order into `body` (which should include RowVersion), but never explicitly checks it exists before the PUT. If the GET response shape changes or RowVersion is absent, the PUT will fail with a confusing MYOB error.

**Fix:** Add explicit check: `if "RowVersion" not in body: raise ValueError(...)`.

---

## Medium Priority

### 4. OAuth callback has no CSRF/state parameter
**Status:** Fixed
**Files:** `auth.py`

The local callback server on port 33333 doesn't validate a `state` parameter. Any request to `localhost:33333/callback?code=X` would be accepted.

**Fix:** Generate a random `state` token, include it in the auth URL, and validate it in the callback.

---

### 5. Cache not invalidated after invoice/bill creation
**Status:** Fixed
**Files:** `invoices.py`, `bills.py`

`create_contact` invalidates the contacts cache, but `create_invoice` and `create_bill` don't invalidate anything. A create followed by an immediate list could return stale cached data.

**Fix:** Add `app.client.cache.invalidate(...)` after POST operations in invoices and bills.

---

### 6. No Retry-After header handling on 429s
**Status:** Fixed
**Files:** `api_client.py:120-124`

Uses fixed exponential backoff on 429 (rate limit) instead of reading the `Retry-After` header from MYOB's response.

**Fix:** Read `Retry-After` header and use it as the wait time when present.

---

## Low Priority

### 7. Config env var substitution silently leaves unresolved placeholders
**Status:** Open
**Files:** `config.py`

If an env var doesn't exist, `${UNDEFINED_VAR}` stays as the literal string in the config. This was the root cause of the 400 errors seen in testing (`${MYOB_COMPANY_FILE_ID}` in the URL).

**Fix:** Log a warning when a substitution pattern is left unresolved.

---

### 8. Error response body truncated at 500 chars
**Status:** Open
**Files:** `api_client.py:24-25`

The `MyobApiError` message truncates the response body at 500 characters. Usually fine but could hide detail on verbose MYOB errors.

---

### 9. Token refresh 60s buffer
**Status:** Open
**Files:** `auth.py:133`

Every request within 60s of token expiry triggers a refresh. Fine for low-throughput MCP but adds latency in burst scenarios.

---

### 10. Banking endpoint only covers SpendMoneyTxn
**Status:** Open
**Files:** `banking.py:53`

`/Banking/SpendMoneyTxn` only returns spend-money transactions, not receipts, transfers, etc. May need additional endpoints depending on use case.
