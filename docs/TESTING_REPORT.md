# Testing report

Date: 15 November 2026. Environment: Python 3.13, Django 5.2, SQLite, Node 20,
headless Chromium (Playwright). Frontend served by `frontend/tools/serve.py`
proxying `/api/` and `/media/` to Django.

## Results

| Suite | Result |
|-------|--------|
| Backend API tests (`manage.py test tests`) | **127 passed**, 1 skipped (the skip is a MySQL-only concurrency test) |
| of which new contract tests (`tests/test_integration_contract.py`) | 15 passed |
| Storefront page crawl, anonymous (all 31 pages) | No JavaScript errors, no failed requests, nothing stuck loading. The only non-200 is the expected "not signed in" answer on account, orders and wishlist |
| Admin page crawl, signed in as owner (all 27 pages) | Clean |
| Admin dialogs (create form + every non-destructive row action on every table) | All open without errors |
| Customer journey (`tests/e2e/shop_e2e.py`) | All steps pass — see below |
| Admin operations (`tests/e2e/admin_e2e.py`, `admin_orders_e2e.py`) | All steps pass on a fresh database — see below |
| Restricted staff account (inventory + dashboard only) | Sees only permitted screens and actions; other admin APIs answer 403 |

### Customer journey — exercised through the real pages

Register → sign in → shop and search listings → product page → add to cart →
wishlist → change quantity in cart → checkout (address, delivery option, terms) →
redirect to payment → return → **"Payment confirmed"**, order marked paid, cart
emptied → order appears in "My orders" and its detail page → account page →
guest order tracking by reference + email → a second, fully guest checkout and
payment.

### Admin operations — exercised through the real forms

Create category · create product, edit its sale price, upload a product image,
add a variation · receive stock · create shipping zone, delivery method,
promotion, role (with permissions) and staff account · edit a CMS page · create
a banner with an image upload · save business settings, homepage hero and SEO
settings · media library lists uploads · download a report as CSV · export a
table as CSV · change an order's status · add an internal order note · open the
printable receipt.

## Not verified here — check on staging before launch

These need services that were not available in this environment.

1. **Real Paystack.** Payment was tested against `tests/e2e/mock_paystack.py`,
   which imitates initialize/verify/refund. Not tested: real card flow, the
   webhook with a real signature, declined/abandoned payments from the real
   gateway, and refunds reaching Paystack.
2. **MySQL.** Everything ran on SQLite. The stock-locking concurrency test only
   runs on MySQL and was skipped.
3. **Redis** (cache/throttling) and **object storage** (uploads were stored on
   local disk).
4. **Email delivery.** Emails are generated and logged (visible under Admin →
   Email logs) but no SMTP server was used; links inside emails were checked in
   code only.
5. **Production deployment.** `production.py` imports cleanly; the nginx/Netlify/
   Vercel examples in `frontend/deploy/` were updated but not deployed.
6. **Refund approval flow in the browser.** The refund screens load and their
   dialogs open; the approve/reject path is covered by backend tests but was not
   driven through the UI.
7. **Review moderation and enquiries in the browser** — same: screens load,
   backend tests cover the logic, no UI-driven run with real records.
8. **Real mobile devices and browsers other than Chromium.** Responsive layouts
   were checked in Chromium at phone width only.

## Reproducing

See the root `README.md` (run locally) and `tests/e2e/README.md` (browser tests).
