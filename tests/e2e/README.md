# End-to-end browser tests

These drive the real pages in headless Chromium against a running backend and
frontend. They create data (products, orders, staff) — run them against a
**development database only**.

## Setup

```bash
pip install playwright && playwright install chromium
```

1. Start the backend with these extra lines in `backend/.env`:
   ```
   PAYSTACK_SECRET_KEY=sk_test_local_mock
   PAYSTACK_PUBLIC_KEY=pk_test_local_mock
   PAYSTACK_BASE_URL=http://127.0.0.1:8765
   ```
2. `python tests/e2e/mock_paystack.py` — stand-in for Paystack on port 8765. Its
   "payment page" immediately redirects back as a successful payment
   (`MOCK_OUTCOME=failed` simulates a declined card).
3. Start the frontend on port 5173 (see the root README).
4. A superuser `owner@starmond.test` / `Owner#Pass2026` must exist, or pass
   `EMAIL=… PW=…` to the admin scripts.

## Scripts

| Script | What it covers |
| --- | --- |
| `storefront_crawl.py <paths…>` | Loads pages anonymously; fails on JS errors, HTTP ≥ 400, or a region stuck loading |
| `admin_crawl.py [paths…]` | Same, signed in as staff. `CLICK=1` also opens the create dialog and every non-destructive row action |
| `shop_e2e.py` | Register → sign in → browse/search → add to cart → wishlist → change quantity → checkout → pay → order list/detail → account → guest order tracking → guest checkout |
| `admin_e2e.py` | Create category, product (+ image, variation), receive stock, shipping zone, delivery method, promotion, role, staff; edit CMS page; banner with image upload; business/homepage/SEO settings; media library; report and table CSV downloads |
| `admin_orders_e2e.py` | Order status change, internal note, printable receipt |

`admin_e2e.py` uses fixed names (e.g. SKU `E2E-HOSE`), so on a second run against
the same database its "create" steps correctly fail with "already exists".
