# STARMOND TECHNOLOGY LIMITED — E-Commerce Backend

Production-ready, API-first backend for a single-owner, multi-category online retail
business. Built with **Python / Django / Django REST Framework / MySQL 8+**, paid via
**Paystack**, media stored on **Backblaze B2**, transactional email via any provider
(Brevo, SES, Mailgun, SendGrid, Postmark, SMTP), async tasks via **Celery + Redis**,
deployed with **Docker + Docker Compose**.

> This backend is the **single source of truth** for products, prices, stock, carts,
> orders, payments, refunds, customers, staff permissions, financial records, SEO data
> and business reports. The frontend (pure HTML/CSS/Vanilla JS, deployed separately)
> communicates exclusively through the documented REST APIs.

---

## Table of contents

1. [Business model](#business-model)
2. [Technology stack](#technology-stack)
3. [Architecture](#architecture)
4. [Project structure](#project-structure)
5. [Quick start (Docker)](#quick-start-docker)
6. [Quick start (local, no Docker)](#quick-start-local-no-docker)
7. [Environment variables](#environment-variables)
8. [Creating the first administrator](#creating-the-first-administrator)
9. [Authentication model](#authentication-model)
10. [API map & documentation](#api-map--documentation)
11. [Managing categories](#managing-categories)
12. [Managing products, variations & images](#managing-products-variations--images)
13. [Managing stock](#managing-stock)
14. [Cart, Buy Now & checkout](#cart-buy-now--checkout)
15. [Paystack setup & webhooks](#paystack-setup--webhooks)
16. [Orders, refunds & receipts](#orders-refunds--receipts)
17. [Shipping configuration](#shipping-configuration)
18. [Promotions](#promotions)
19. [Reviews, wishlist, newsletter, enquiries](#reviews-wishlist-newsletter-enquiries)
20. [Staff roles & permissions (RBAC)](#staff-roles--permissions-rbac)
21. [Backblaze B2 media storage](#backblaze-b2-media-storage)
22. [Email provider setup](#email-provider-setup)
23. [Redis & Celery](#redis--celery)
24. [SEO management & sitemap](#seo-management--sitemap)
25. [Dashboard & reports](#dashboard--reports)
26. [Testing](#testing)
27. [Production deployment](#production-deployment)
28. [Database backups](#database-backups)
29. [Monitoring guidance](#monitoring-guidance)
30. [Troubleshooting](#troubleshooting)

---

## Business model

Single-owner retail. **No vendors, no commissions, no vendor withdrawals, no payment
splitting, no seller dashboards.** All operations belong to STARMOND TECHNOLOGY
LIMITED. Categories are fully dynamic (electrical, fashion, electronics, accessories,
home, and any category the owner adds later — no code changes required).

## Technology stack

| Concern | Choice |
|---|---|
| Language / framework | Python 3.12, Django 5.2 LTS, Django REST Framework |
| Database | MySQL 8+ (InnoDB, utf8mb4, CHECK constraints, FK integrity). SQLite permitted for local dev/tests only (`DB_ENGINE=sqlite`) |
| Payments | Paystack (initialize, verify, webhook, refunds) — all server-side |
| Media | Backblaze B2 via S3-compatible API (`django-storages` + `boto3`); local storage fallback in dev |
| Async | Celery + Redis (emails, expiry jobs, retries) |
| Email | Any provider via Django email backend (SMTP relays of Brevo/SES/Mailgun/SendGrid/Postmark) |
| Docs | drf-spectacular OpenAPI 3 schema + Swagger UI |
| Deploy | Docker, Docker Compose, gunicorn |

## Architecture

Every request follows the same pipeline:

```
REQUEST → VALIDATION → AUTHORIZATION → SERVICE → DATABASE TRANSACTION
        → AUDIT → SECONDARY NOTIFICATION → API RESPONSE
```

Business logic lives in a **service layer** (`backend/services/` and app-level
`services.py` modules), never inside fat views or serializers:

| Service | Responsibility |
|---|---|
| `ProductService` | Product create/update, SKU/slug integrity, safe delete→archive |
| `CategoryService` | Hierarchy validation, depth limit, slug uniqueness, safe delete, reorder |
| `InventoryService` | Row-locked reserve/confirm/release/restore/adjust, movement log, status sync |
| `CartService` | Guest + authenticated carts, merge rules, stock validation |
| `PricingService` | The ONLY source of money math (Decimal only; client input never trusted) |
| `CheckoutService` | Cart checkout + Buy Now, idempotency, reservations, snapshots |
| `OrderService` | Validated lifecycle state machine, cancellation, expiry |
| `PaymentService` | Paystack orchestration, verification, idempotent webhook processing |
| `PaystackService` | The only component that talks to Paystack (secret key never leaves server) |
| `RefundService` | Policy-bound requests, provider-confirmed outcomes, optional restock |
| `ShippingService` | Zone/method quoting, provider extension point |
| `PromotionService` | Eligibility, limits, caps, single-promotion-per-order (no stacking) |
| `CustomerService` | Profile/address/order-history helpers |
| `NotificationService` | In-app notifications + transactional email orchestration with dedupe keys |
| `EmailService` | Queued, logged, retried, provider-independent email delivery |
| `SEOService` | Metadata assembly, JSON-LD (never fabricated), sitemap, cache invalidation |
| `ReportService` | Financial aggregation — revenue counted once, from verified payments only |
| `AuditService` | Append-only audit trail for sensitive actions |
| `MediaService` | Upload validation, safe naming, thumbnails/WebP, private signed URLs, cleanup |

### Security posture (summary)

- Backend-authoritative pricing, shipping, discounts and stock — client totals ignored.
- `SELECT ... FOR UPDATE` + `transaction.atomic()` + DB CHECK constraints prevent
  overselling and negative inventory.
- Paystack webhook: HMAC SHA-512 signature verification, event-id dedupe table,
  independent server-side `verify` call before money movement.
- RBAC enforced on every staff endpoint (25 permission codenames, configurable roles).
- Idempotency keys on checkout and payment initialization.
- Secure cookies, CSRF, restricted CORS, throttling, audit logs, non-sequential
  public references (`ORD-YYYYMMDD-XXXX`), signed expiring guest order tokens.
- Uploads validated by content (Pillow), MIME, size and dimension limits; private
  uploads served only via short-lived signed URLs.

## Project structure

```
backend/
├── config/                  # settings (base/development/production), urls, celery, wsgi/asgi
├── apps/
│   ├── core/                # env, error contract, pagination, RBAC, money, idempotency, references
│   ├── accounts/            # custom User, Role, Permission, StaffProfile, auth APIs
│   ├── customers/           # CustomerProfile, Address, Wishlist (+ staff customer directory)
│   ├── categories/          # dynamic nested categories + SEO
│   ├── products/            # Product, images, attributes, variations, search
│   ├── inventory/           # Inventory, InventoryMovement, tasks
│   ├── cart/                # Cart, CartItem
│   ├── orders/              # Order, OrderItem, status log, checkout view
│   ├── payments/            # Payment, webhook events, Paystack client & service
│   ├── refunds/             # Refund workflow (provider-confirmed)
│   ├── shipping/            # ShippingZone, ShippingMethod
│   ├── promotions/          # Promotion engine + usage ledger
│   ├── reviews/             # moderated reviews, verified purchase
│   ├── notifications/       # in-app notifications, newsletter, enquiries
│   ├── emails/              # EmailLog + EmailService + Celery tasks + templates
│   ├── dashboard/           # owner dashboard overview API
│   ├── reports/             # sales/product/payment/refund reports + CSV/XLSX/PDF export
│   ├── cms/                 # business settings, pages, homepage sections, banners
│   ├── media/               # MediaAsset + MediaService (Backblaze B2)
│   ├── seo/                 # SEO settings, sitemap.xml, robots.txt, JSON-LD, pre-render
│   └── audit/               # AuditLog
├── services/                # cross-app service layer (see table above)
├── tests/                   # 112 automated tests (business workflows, security, SEO, perf)
├── docs/openapi-schema.yml  # generated OpenAPI 3 contract
├── requirements.txt / requirements-dev.txt
├── Dockerfile / docker-compose.yml / docker-compose.production.yml
├── .env.example / .dockerignore / .gitignore
└── manage.py
```

## Quick start (Docker)

Prerequisites: Docker + Docker Compose, and a `.env` file.

```bash
cd backend
cp .env.example .env          # then edit secrets (DB_PASSWORD, DJANGO_SECRET_KEY, Paystack test keys...)
docker compose up --build
```

The compose stack runs MySQL 8.4, Redis 7, the API (migrates + seeds roles on boot),
a Celery worker and Celery beat. API available at `http://localhost:8000`.

```bash
docker compose exec api python manage.py createsuperuser      # business owner
docker compose exec api python manage.py seed_demo_catalog    # OPTIONAL dev/staging demo data
```

## Quick start (local, no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # set DB_ENGINE=sqlite for zero-setup local dev
export DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py migrate
python manage.py seed_roles
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

For MySQL locally, set `DB_ENGINE=mysql` plus `DB_*` vars and create the database:
`CREATE DATABASE starmond CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`

## Environment variables

See [`.env.example`](.env.example) for the complete annotated contract (Django, MySQL,
Paystack, Backblaze B2, email, Redis/Celery, CORS/CSRF, business rules, throttling).
Secrets are **never** committed. Production settings **fail fast at startup** if the
secret key, Paystack keys, MySQL engine or a real email backend are missing.

## Creating the first administrator

```bash
python manage.py createsuperuser
```

The superuser is the **Business Owner / Super Administrator** and bypasses all role
checks. Additional staff are created via `POST /api/admin-panel/staff/` (email, name,
role, temporary password) — they receive role-scoped permissions only.

Seed the permission catalog and the 7 default roles at any time (idempotent):

```bash
python manage.py seed_roles
```

## Authentication model

Two supported mechanisms (documented for the frontend team):

1. **Session cookies** (recommended for same-site frontends): `POST /api/auth/login/`
   starts a session. State-changing requests need the CSRF header
   (`X-CSRFToken` from the `csrftoken` cookie). Cookies are HttpOnly; `Secure` and
   HSTS are enforced in production settings.
2. **Token auth** (recommended for independently deployed frontends): the login
   response includes `auth_token`; send `Authorization: Token <key>`. Tokens are
   revoked on logout and on password reset. Credentials must never be stored in
   `localStorage`; keep the token in memory or a secure cookie.

Sensitive auth endpoints are rate-limited (`THROTTLE_AUTH`, default 10/hour/IP-user).
Registration triggers an email-verification link (signed, 3-day expiry). Password
reset uses Django's token generator; responses are enumeration-safe.

## API map & documentation

Interactive docs: **`GET /api/docs/`** (Swagger UI) · schema: **`GET /api/schema/`** ·
static contract: [`docs/openapi-schema.yml`](docs/openapi-schema.yml) (190 operations).

| Area | Base path | Auth |
|---|---|---|
| Health | `GET /api/health/` | none |
| Auth | `/api/auth/` (register, verify-email, resend-verification, login, logout, password/reset/request, password/reset/confirm, password/change, me) | per endpoint |
| Customers | `/api/customers/profile/`, `/api/customers/addresses/`, `/api/customers/wishlist/` (+ `remove`, `move-to-cart`) | customer |
| Categories | `GET /api/categories/`, `GET /api/categories/{slug}/` | public |
| Products | `GET /api/products/` (filters: category, min_price, max_price, featured, new_arrivals, best_sellers, brand, in_stock, q; ordering: created_at, name, regular_price), `GET /api/products/{slug}/`, `GET /api/products/search/?q=` | public |
| Cart | `GET/POST/DELETE /api/cart/`, `PATCH/DELETE /api/cart/items/{id}/`, `POST /api/cart/merge/` | public (guest via `X-Cart-Token` header) |
| Checkout | `POST /api/checkout/` (source.type = `cart` or `buy_now`; `Idempotency-Key` header supported) | public (guest allowed) |
| Orders | `GET /api/orders/`, `GET|POST /api/orders/{reference}/`, `POST /api/orders/lookup/` | customer/guest-token |
| Payments | `POST /api/payments/paystack/initialize/`, `POST /api/payments/paystack/verify/`, `POST /api/payments/paystack/webhook/`, `GET /api/payments/mine/` | mixed (see docs) |
| Refunds | `GET|POST /api/refunds/requests/`, `/api/refunds/admin/` (+ `approve`, `reject`, `check-status`) | customer / staff |
| Shipping | `GET /api/shipping/options/?state=&subtotal=` (public quote); `/api/shipping/zones/`, `/api/shipping/methods/` (staff `shipping.manage`) | mixed |
| Promotions | `POST /api/promotions/validate/` (public preview); CRUD requires `promotions.manage` | mixed |
| Reviews | `GET /api/reviews/product/{slug}/`, `POST /api/reviews/`, `/api/reviews/admin/` (+ `approve`, `reject`) | mixed |
| Notifications | `/api/notifications/mine/`, `POST /api/notifications/newsletter/`, `POST /api/notifications/enquiries/`, staff enquiry/newsletter admin | mixed |
| CMS | `GET /api/cms/settings/`, `GET /api/cms/homepage/`, `GET /api/cms/pages/`, `GET /api/cms/pages/{slug}/`; staff CRUD under `/api/cms/admin/...` | mixed |
| Media | `POST /api/media/uploads/` (staff `media.manage`; customers: private `reference_image` only), `/api/media/assets/` (+ `signed-url`) | mixed |
| SEO | `GET /api/seo/structured-data/{kind}/`, staff: `/api/seo/settings/`, `/api/seo/preview-snippet/`, `/api/seo/products/{slug}/`, `/api/seo/categories/{slug}/` | mixed |
| Inventory | `/api/inventory/` (+ `adjust`, `receive`, `movements`), `/api/inventory/movements/` | staff |
| Dashboard | `GET /api/dashboard/overview/?range=` | staff |
| Reports | `/api/reports/{sales,categories,products,payments,refunds,orders}/?range=&format={json,csv,xlsx,pdf}` | staff |
| Admin panel | `/api/admin-panel/{permissions,roles,staff}/`, `/api/admin-panel/customers/` | staff |
| Audit | `GET /api/audit/logs/` | staff `audit.view` |
| Products (staff) | `/api/products/admin/` (+ `images`, `images/{id}/set-main`, `images/reorder`, `variations`, `activate`, `deactivate`, `archive`) | staff |
| Categories (staff) | `/api/categories/admin/` (+ `reorder`, `activate`, `deactivate`) | staff |
| Orders (staff) | `/api/orders/admin/` (+ `{reference}/status`, `{reference}/notes`, `{reference}/receipt`) | staff |
| SEO (public) | `GET /robots.txt`, `GET /sitemap.xml`, `GET /shop/...` (pre-rendered crawlable pages) | none |

### Response contract

Successful collection responses:
```json
{"status": "success", "count": 57, "page": 1, "page_size": 20, "total_pages": 3, "results": [...]}
```
Errors (all statuses ≥ 400, never leaking internals):
```json
{"status": "error",
 "error": {"code": "stock_unavailable", "message": "Only 2 unit(s) available.", "fields": null},
 "request_id": "a1b2c3d4e5f6"}
```
Money is **always serialized as decimal strings** (`"59500.00"`), currency `NGN`.
Every response carries `X-Request-ID` and `X-Response-Time-Ms` headers.

### Idempotency requirements

- `POST /api/checkout/` — send `Idempotency-Key` (unique per checkout attempt);
  replays return the original order instead of creating duplicates.
- Payment initialization reuses an in-flight pending payment for the same order.
- Webhooks are deduplicated by Paystack event id (`PaymentWebhookEvent`).
- Email sends are deduplicated per business event via `dedupe_key`.

## Managing categories

Staff with `categories.manage`:

- Create: `POST /api/categories/admin/` `{name, description?, parent?, slug?, seo_*...}`.
  Slugs auto-generate and are guaranteed unique; nesting is capped at
  `MAX_CATEGORY_DEPTH` (default 3); cycles are rejected.
- Reorder: `POST /api/categories/admin/reorder/` `{"items":[{"id":1,"display_order":0}]}`
- Deactivate a whole tree: `POST /api/categories/admin/{id}/deactivate/`
- Delete is blocked while products or subcategories are linked (data integrity);
  deactivate instead.

Public URLs are meaningful: `/shop/electrical/`, `/shop/electrical/cables/`.

## Managing products, variations & images

Staff with `products.manage` (reads need `products.view`):

- Create/update via `POST|PATCH /api/products/admin/` (JSON or multipart).
  `stock_quantity` sets opening stock. Statuses: `draft`, `active`, `inactive`,
  `out_of_stock` (auto-synced from real inventory), `archived`. Only `active`
  products appear in public APIs. `cost_price` is visible **only** to holders of
  `finance.view`.
- Images: `POST /api/products/admin/{id}/images/` (multipart `images[]`), reorder,
  set main, delete. Stored via the configured storage backend (B2 in production).
- Variations (size/colour/voltage/storage/…): `POST /api/products/admin/{id}/variations/`
  with `sku`, `options` (e.g. `{"Size":"XL","Colour":"Red"}`), and **either** absolute
  `price` **or** `price_adjustment`; `stock_quantity` creates variation-level inventory.
  Each variation is a full DB record with its own SKU, pricing and stock.
- Made-to-order (custom fashion): set `supports_customization: true` and define
  `customization_schema`, e.g.
  `[{"field":"size","label":"Clothing size","type":"select","required":true,"options":["S","M","L","XL"]},
    {"field":"measurements","label":"Measurements","type":"text","required":false},
    {"field":"fabric","label":"Fabric","type":"select","required":true,"options":["Ankara","Lace","Cotton"]}]`.
  Customers upload reference images privately via `POST /api/media/uploads/`
  (`kind=reference_image`) and pass `customization` + `_reference_image_id` in the
  Buy Now source payload. Customization is validated server-side against the schema
  and snapshotted onto the order item.
- Delete: products with order history are **archived**, never hard-deleted
  (financial history preserved).

## Managing stock

- Inventory is authoritative at product/variation level:
  `AVAILABLE = ON_HAND − RESERVED` (CHECK-constrained, never negative).
- Checkout **reserves**; verified payment **converts reservation to sale**;
  cancellation/expiry **releases**; authorized returns **restore**.
- Adjustments: `POST /api/inventory/{id}/adjust/` `{"delta": -2, "reason": "Damaged"}`
  — reason mandatory, audited, cannot go below active reservations.
- Receipts: `POST /api/inventory/{id}/receive/` `{"quantity": 50}`.
- Every mutation writes an `InventoryMovement` (before/after, type, order, actor, reason).
- Beat task `release_expired_reservations` runs every 5 minutes and expires stale
  pending orders (`PENDING_ORDER_EXPIRY_MINUTES`, default 60).

## Cart, Buy Now & checkout

- Guest carts are identified by the `X-Cart-Token` header (returned by cart APIs);
  authenticated carts bind to the user. `POST /api/cart/merge/` merges a guest cart
  on login (identical lines sum, stock revalidated, duplicates impossible).
- **Buy Now** bypasses the cart entirely: `POST /api/checkout/` with
  `"source": {"type": "buy_now", "product_id": ..., "variation_id": ..., "quantity": ...}`.
  The customer's existing cart is **never modified**. Cart checkout uses
  `"source": {"type": "cart"}`. Both flows share the same order/payment services.
- Checkout collects contact + delivery info, quotes shipping server-side, applies at
  most one promotion, creates a `pending_payment` order with an expiry, and reserves
  stock atomically. Prices/totals sent by the client are ignored.

## Paystack setup & webhooks

1. Create test/live keys at dashboard.paystack.co. Put them in `.env`
   (`PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY`, `PAYSTACK_WEBHOOK_SECRET`).
   **Never use live keys in development.**
2. In the Paystack dashboard → Settings → Developer Settings → Webhook URL, set:
   `https://api.yourdomain.com/api/payments/paystack/webhook/`
   Copy the secret into `PAYSTACK_WEBHOOK_SECRET`.
3. Flow: checkout creates the order → `POST /api/payments/paystack/initialize/`
   returns `authorization_url` → customer pays on Paystack → frontend calls
   `POST /api/payments/paystack/verify/` **and** Paystack sends the webhook.
   Success requires server-side verification (signature + amount + currency +
   reference). Redirects alone never mark an order paid.
4. Amounts are converted to kobo internally; `Payment` records keep full history
   (statuses: pending, successful, failed, abandoned, reversed, refunded,
   partially refunded).

## Orders, refunds & receipts

- References are human-readable and unique: `ORD-20261114-W3Q1`. Sequential IDs are
  never exposed.
- Lifecycle: `pending_payment → paid → processing → packed → shipped →
  out_for_delivery → delivered → completed`, plus `cancelled`, `payment_failed`,
  `expired`, `refund_requested`, `partially_refunded`, `refunded`. Every transition is
  validated; financial statuses can only be set by the payment/refund services.
- Staff: filtered/searchable list, status updates with notes, tracking reference,
  internal notes, payment history, and `GET /api/orders/admin/{ref}/receipt/`
  returning receipt/invoice data (business info, line items, verified payments,
  refunds) for printing.
- Customers: own order list/detail, cancel while `pending_payment`, request refunds
  within `refund_window_days` (business setting, default 7). Guests use
  `POST /api/orders/lookup/` (reference + email) to obtain an expiring signed token.
- Refunds execute via the official Paystack refund API; a refund is `successful` only
  after the provider confirms (immediately, via `check-status`, or via
  `refund.processed` webhooks). Optional `restock_items` restores inventory.

## Shipping configuration

- `ShippingZone`s group states; `ShippingMethod`s attach fees, free-delivery
  thresholds, delivery windows and kinds (`standard`, `express`, `pickup`) to zones
  (or globally, e.g. pickup). Public quotes: `GET /api/shipping/options/?state=&subtotal=`.
- `ShippingService.providers` exposes a `ShippingProvider` abstraction for future
  carrier integrations. Tracking events are never invented — only real provider data.

## Promotions

Create via `/api/promotions/` (staff): percentage or fixed codes, scopes (all /
specific products / specific categories), minimum purchase, maximum discount cap,
start/end window, total and per-customer usage limits, first-time-customer option,
sale-item compatibility flag, banner image. Public preview endpoint
`POST /api/promotions/validate/`; authoritative application happens at checkout.
One promotion per order (no stacking).

## Reviews, wishlist, newsletter, enquiries

- Reviews: authenticated customers, 1–5 rating, one per product per customer,
  verified-purchase derived from real paid orders, admin moderation required before
  public display, rate-limited.
- Wishlist: add/remove/list/move-to-cart per customer.
- Newsletter: `POST /api/notifications/newsletter/` (subscribe/unsubscribe consent).
- Enquiries: public form endpoint + staff queue with statuses and response notes.

## Staff roles & permissions (RBAC)

Default roles seeded by `seed_roles`: **Super Administrator** (owner, all 25
permissions), **Manager**, **Product Manager**, **Inventory Manager**,
**Order Manager**, **Customer Support**, **Accountant**. Roles are fully editable via
`/api/admin-panel/roles/`; permission catalog at `/api/admin-panel/permissions/`.
Permission checks are enforced server-side on every endpoint — frontend button
visibility is irrelevant. Sensitive actions are written to `/api/audit/logs/`.
Privilege escalation is prevented: staff cannot grant themselves roles
(`staff.manage` is required), cannot deactivate the owner, and cannot alter paid
order totals (no endpoint exists to do so; adjustments only occur via the
audited payment/refund services).

## Backblaze B2 media storage

- Set `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME` (public),
  `B2_MEDIA_PRIVATE_BUCKET` (private), `B2_ENDPOINT_URL`, `B2_REGION`, and
  `B2_PUBLIC_BASE_URL` (your CDN or friendly bucket domain). When configured, the
  default storage backend becomes S3-compatible B2 for **all** `ImageField`s and
  `MediaService` uploads; binaries never touch MySQL (only object keys + metadata).
- Public bucket: product/category/banner images, served via `B2_PUBLIC_BASE_URL`.
  Private bucket: customer reference images — accessed only via short-lived
  presigned URLs (`POST /api/media/assets/{id}/signed-url/`, 10-minute expiry).
- Uploads are content-validated with Pillow (MIME sniffing), size-capped
  (`MAX_UPLOAD_SIZE_MB`), dimension-capped, safely renamed (random suffix), and get
  WebP + thumbnail derivatives generated asynchronously-friendly at upload time.
- Bucket CORS/lifecycle should be configured in the B2 console; hide the key id/secret
  from any client. Orphaned FAILED assets are cleaned by `MediaService.cleanup_orphans`.

## Email provider setup

Provider-independent via Django's email backend:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend   # or provider SDK backend
EMAIL_HOST=smtp-relay.brevo.com                             # Brevo/SES/Mailgun/SendGrid/Postmark SMTP
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL="STARMOND TECHNOLOGY LIMITED <no-reply@yourdomain.com>"
```

Every message is logged in `EmailLog` (recipient, template, subject, status,
attempts, error, related order/payment) and delivered through Celery with bounded
exponential retries; a beat task requeues failures. Duplicate sends are impossible
(unique `dedupe_key` per business event, e.g. `payment_successful:PAY-...`).
**Email failure never invalidates a payment or order** — sending happens after commit.
Branded HTML + plain-text templates live in `apps/emails/templates/emails/`.
Staff can inspect logs at `/api/emails/logs/` (message bodies are not exposed).

## Redis & Celery

- `REDIS_URL` (cache + idempotency store), `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
- Worker: `celery -A config worker -l info` · Beat: `celery -A config beat -l info`
  (both included in compose).
- Beat schedule: reservation release (5 min), stale-order expiry (10 min), failed
  email retry (15 min). Tasks are idempotent with retry limits; financial integrity
  never depends on a task succeeding (payment/order writes are transactional).
- Without Redis, dev falls back to locmem cache and eager Celery — fine for
  development, **not** for production.

## SEO management & sitemap

- **Pre-rendered crawlable HTML**: `GET /shop/...` routes serve server-rendered
  category/product pages (title, meta, canonical, Open Graph, JSON-LD, real price &
  availability) directly from the database — no frontend framework required. Toggle
  with `enable_prerender` in `/api/seo/settings/`.
- `GET /sitemap.xml` — homepage, categories, subcategories, active products,
  published pages only (never admin/cart/checkout/API/private URLs), with accurate
  `lastmod`; version-bumped cache invalidation fires on catalogue changes.
- `GET /robots.txt` — allows the site, disallows `/api/`, `/django-admin/`, cart,
  checkout and account areas; declares the sitemap.
- Structured data: `Organization`, `WebSite` + `SearchAction`, `BreadcrumbList`,
  `Product` + `Offer` (real price/availability), `AggregateRating` **only** when
  approved genuine reviews exist. Nothing is fabricated.
- Per-entity metadata: products/categories expose `seo_title`, `seo_description`,
  `seo_keywords`, `canonical_url`, `og_image` with sensible auto-defaults; staff
  override via `/api/seo/products/{slug}/`, `/api/seo/categories/{slug}/`, global
  defaults at `/api/seo/settings/`, snippet preview at `/api/seo/preview-snippet/`.

## Dashboard & reports

- `GET /api/dashboard/overview/?range=today|yesterday|week|month|last_month|custom&date_from=&date_to=`
  → realized revenue (verified payments only), orders by state, pending payments,
  customers, catalogue & inventory health (low/out-of-stock lists), recent orders,
  best sellers, daily sales trend.
- Reports: sales (summary + trend), sales by category, best-selling products,
  payment ledger, refund ledger, orders. Each supports `format=json|csv|xlsx|pdf`
  with permission enforcement (`reports.view` / `finance.view`) and date ranges.
  Unpaid orders never count as revenue; each successful payment contributes once.

## Testing

```bash
python manage.py test tests            # 112 tests (SQLite test DB by default)
python manage.py test tests -v 2       # verbose
DB_ENGINE=mysql DB_HOST=... python manage.py test tests   # full MySQL run incl. concurrency test
```

Coverage: auth flows, categories (depth/cycles/safe-delete), products (SKU, sale
rules, cost-price privacy, images incl. malicious upload rejection), search, cart
(guest/merge/limits), Buy Now (cart untouched, reservations), checkout (guest,
validation, idempotency, shipping authority), promotions (caps/windows/limits),
Paystack (initialize/verify/webhook: signatures, duplicates, amount & currency
mismatch, expiry, replay), order lifecycle (invalid transitions, protected financial
statuses, receipts), refunds (partial/full, provider-confirmed, restock), inventory
(constraint-level negative prevention, release/restore, expiry task), security (RBAC,
cross-customer access, price/quantity manipulation), SEO (sitemap, robots, JSON-LD,
pre-render), reports (revenue integrity, CSV/XLSX/PDF export), and measured
performance bounds (query-count limits catch N+1 regressions).

## Production deployment

Recommended topology (frontend and backend deploy independently):

```
FRONTEND (static hosting/CDN)  →  DJANGO REST API (gunicorn in Docker)
                                   ├── MANAGED MYSQL 8+
                                   ├── REDIS / CELERY worker + beat
                                   ├── BACKBLAZE B2 (+ CDN) for media
                                   ├── PAYSTACK
                                   └── TRANSACTIONAL EMAIL PROVIDER
```

```bash
# on the server
cp .env.example .env   # production values: DEBUG=false, real keys, DB_ENGINE=mysql
docker compose -f docker-compose.production.yml up -d --build
```

Checklist:

1. TLS terminated at reverse proxy (nginx/Caddy/Traefik) → forwards to api:8000.
   `SECURE_SSL_REDIRECT=true`, HSTS on (defaults in production settings).
2. `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` must list
   your exact frontend/API origins.
3. Paystack webhook URL configured + secret in env; test with a live test-mode key.
4. B2 buckets created (public + private), keys scoped to those buckets,
   `B2_PUBLIC_BASE_URL` pointing at CDN/friendly domain.
5. Real `EMAIL_BACKEND` configured (production settings refuse console backend).
6. Static files: `collectstatic` runs in the production compose command; serve
   `staticfiles/` from the proxy or whitenoise-equivalent. Django admin is available
   at `/django-admin/` (consider IP allow-listing at the proxy).
7. MySQL backups enabled (see below); volumes persisted outside containers.
8. Containers run as non-root `django` user; secrets only via env; healthchecks on.
9. Create the owner: `docker compose exec api python manage.py createsuperuser`.
10. Rollback: redeploy the previous image tag and restore the latest DB snapshot
    (migrations are additive; never edit historical financial rows).

## Database backups

```bash
# MySQL dump (daily via cron; keep offsite)
mysqldump --single-transaction --routines --triggers -h DB_HOST -u DB_USER -p starmond \
  | gzip > starmond-$(date +%F).sql.gz
# restore
gunzip < starmond-YYYY-MM-DD.sql.gz | mysql -h DB_HOST -u DB_USER -p starmond
```
Backblaze B2: enable versioning + a lifecycle rule on the media buckets. Test restores
periodically. Media and DB are separable: the DB stores object keys only.

## Monitoring guidance

- Liveness/readiness: `GET /api/health/` (checks DB) — wire into uptime monitoring;
  Docker healthchecks already use it.
- Every response has `X-Request-ID` + `X-Response-Time-Ms` for tracing/latency SLOs.
- Watch: `EmailLog.status=failed` count, `PaymentWebhookEvent.processed=false`,
  pending orders older than expiry, low-stock list from the dashboard, Celery queue
  depth (`celery -A config inspect active`), MySQL connections/slow query log.
- Logs are structured to stdout (12-factor) — aggregate with your log stack.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImproperlyConfigured` on boot (production) | A required env var is missing — the message names it |
| Paystack initialize returns 502 | Check `PAYSTACK_SECRET_KEY` (test vs live) and outbound network |
| Webhook 400 invalid signature | Dashboard webhook secret ≠ `PAYSTACK_WEBHOOK_SECRET`; re-copy |
| Orders expiring too fast | Raise `PENDING_ORDER_EXPIRY_MINUTES`; beat releases reservations |
| Images 403/404 in production | `B2_PUBLIC_BASE_URL` wrong or bucket not public; verify key scope |
| CORS errors in browser console | Add the exact frontend origin to `CORS_ALLOWED_ORIGINS` (scheme included) |
| CSRF failures with cookie auth | Frontend must read `csrftoken` cookie and send `X-CSRFToken` header; origin must be in `CSRF_TRUSTED_ORIGINS` |
| Emails not sending | Check `EmailLog` rows via `/api/emails/logs/` for provider errors; verify SMTP creds |
| `mysqlclient` build fails | Install `default-libmysqlclient-dev` + `build-essential` (already in Dockerfile) |
| Tests slow / lock errors on SQLite | Expected for concurrency test — it auto-skips unless `DB_ENGINE=mysql` |

---

*Version 1.0.0 · Currency NGN (architecture supports adding currencies) · Timezone
Africa/Lagos (configurable) · All financial figures in this system derive from
verified payment records.*
