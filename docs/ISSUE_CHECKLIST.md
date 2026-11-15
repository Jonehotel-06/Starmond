# Integration issue checklist

What was wrong when the frontend and backend were first put together, and what
was done about each item. "Verified" means exercised in a browser or by an
automated test in this work; see `TESTING_REPORT.md` for how.

## Blocking defects (the app could not run or was unsafe)

| # | Problem | Fix | Status |
|---|---------|-----|--------|
| 1 | `backend/apps/media/` was missing from the repository (a `.gitignore` rule for `media/` swallowed it), so Django could not start | Rebuilt the app: model, upload/list/update/remove/signed-URL endpoints, migration; narrowed the ignore rule to `/media/` | Verified |
| 2 | `config/settings/production.py` raised `ImportError` on load | Fixed the import; kept the production hardening | Loads; not run against real infrastructure |
| 3 | **Any** staff account passed **every** admin permission check | Permission class now requires the specific permission; superusers only bypass | Verified (regression test) |
| 4 | `GET /api/orders/` (customer's own orders) was shadowed by the admin router and unreachable | Router changed so both routes resolve | Verified |
| 5 | Paystack: verify/callback/webhook handling had mismatches that would have left paid orders unpaid | Corrected verification, callback URL and webhook-secret handling; gateway base URL and callback URL are now configurable | Verified against a local mock gateway only |
| 6 | Service errors lost their message, so users saw a generic failure | Message and code are now preserved | Verified |

## Frontend ↔ backend contract mismatches

| # | Problem | Fix | Status |
|---|---------|-----|--------|
| 7 | Frontend called `/api/v1/…`; backend serves `/api/…` | Frontend default, tools and env example changed to `/api` | Verified |
| 8 | Frontend expected JWT; backend uses session cookie + CSRF | Auth layer rewritten for sessions; added `GET /api/auth/csrf/`; cookie/CORS settings made configurable | Verified |
| 9 | User object lacked what the UI needs to show/hide admin features | `/auth/me/` now returns `is_superuser` and `permissions[]` | Verified |
| 10 | Storefront modules (catalogue, cart, wishlist, checkout, payments, orders, account, reviews, contact, newsletter, CMS pages) called endpoints that did not exist or read the wrong field names | Every module rewritten against the real API | Verified end to end |
| 11 | Endpoints the storefront genuinely needs did not exist | Added: delivery states, checkout price preview, product facets, related products, recent reviews, "my reviews" | Verified |
| 12 | Product list lacked `has_variations`, price ordering, brand and on-sale filters | Added | Verified |
| 13 | Links in emails pointed to URLs without `.html` | Fixed | Checked in code; no mail server here |
| 14 | Admin console called `/admin/<module>/`, `bulk/` and `export/` routes that do not exist, with permission names the backend does not use | Admin data layer, module definitions, dashboard, reports, media library and settings rewritten against real routes and permission codenames; CSV export of tables is done in the browser; report downloads use the backend's CSV/Excel/PDF output | Verified |
| 15 | Admin pages existed for features with no backend (standalone variations, discounts, notifications) | Pages removed. Variations are managed inside a product; discount codes live under Promotions | Done |
| 16 | No admin screens for things the backend does support | Added: Roles & permissions, Pages & policies, Banners, Homepage sections; image fields upload to the media library | Verified |
| 17 | `/api/admin-panel/customers/` returned HTTP 500 | Fixed | Verified |
| 18 | Staff category list had no search, filters or parent names | Added | Verified |

## Defects found while testing the integrated app

| # | Problem | Fix |
|---|---------|-----|
| 19 | Creating a product or promotion with an optional number left blank caused a server error / rejection | Blank optional numbers now fall back to the server default |
| 20 | Editing a record did not preselect dropdowns loaded from the API (e.g. a product's category), so saving failed with "required" | Fixed |
| 21 | Form errors showed "Please correct the highlighted fields" (or a request ID) instead of the real reason | The actual server message is always shown |
| 22 | Staff order view offered customer-only actions ("Request refund") | Hidden in staff mode |
| 23 | Dashboard links such as "Awaiting payment → View" did not apply their filter | Tables now read filters from the URL |
| 24 | Uploaded images returned 404 in local development | Dev server and deploy examples now proxy `/media/` as well as `/api/` |
| 25 | Reports with a malformed date caused a server error | Now a clear 400 |
| 26 | Closed mobile menu leaked a shadow on the page edge and stayed reachable by keyboard | Fixed |
| 27 | Homepage reviews area stayed in a loading state when there were no reviews | Fixed |
| 28 | Sidebar showed empty section headings for staff with few permissions | Hidden |
