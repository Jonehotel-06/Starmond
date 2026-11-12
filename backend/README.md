# STARMOND TECHNOLOGY LIMITED — E-Commerce Backend

Production-ready backend for a **single-owner, multi-category** Nigerian e-commerce
business. The backend is the single source of truth for catalogue data, pricing,
stock, orders, payments (Paystack), refunds, delivery, reporting and SEO.

- **Stack:** Python 3.11+ · Django 5 · Django REST Framework · PostgreSQL 8+/MySQL 8+ (SQLite for local dev)
- **Currency:** Nigerian Naira (₦ / NGN), with a `currency` column on every monetary record
- **Frontend:** consumed by an independent HTML/CSS/vanilla-JS client over the REST API
- **No Docker, no CSS/JS frameworks, no mock data**

---

## 1. What this backend does

| Area | Delivered |
|---|---|
| Catalogue | Unlimited dynamic categories & subcategories, products, galleries, attributes, variations with per-variant price and stock, custom/made-to-order products |
| Cart | Guest and customer carts, persistence, merge on login, duplicate prevention, live re-pricing |
| Checkout | Server-authoritative totals, backend delivery fees, discounts, **Buy Now** that never touches the cart, idempotency keys |
| Inventory | Variation-level stock, the `AVAILABLE = ON-HAND − RESERVED` formula, reservation ledger, movement ledger, no negative stock, row locks |
| Orders | Human-readable references, full lifecycle state machine, activity trail, expiry, cancellation |
| Payments | Paystack initialise + **independent server-side verification**, HMAC-verified idempotent webhooks, duplicate-payment prevention |
| Refunds | Customer requests, staff review, Paystack refund API, provider-confirmed completion only, optional restocking |
| Delivery | Zones/states/cities, priced methods, pickup, tracking references, pluggable provider abstraction |
| Customers | Registration, JWT auth, email verification, password reset/change, addresses, order history, receipts, wishlist, notification preferences |
| Reviews | Verified-purchase badges from real orders, moderation, duplicate prevention, rate limiting |
| Promotions | Percentage/fixed/free-shipping, windows, caps, per-customer limits, stacking rules, redemption records |
| Admin | Dashboard stats, role-based permissions, order processing, refund queue, inventory control, CMS, reports |
| Reports | Gross/net sales, payments by state, refunds, discounts, shipping revenue, product & category sales, AOV, CSV/Excel/PDF exports |
| SEO | Server-side metadata, canonical URLs, JSON-LD, `sitemap.xml`, `robots.txt` |
| Security | Backend-authoritative everything, RBAC, throttling, idempotency, audit log, no secrets in responses |

---

## 2. Quick start (development)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit the values
python manage.py migrate
python manage.py bootstrap_starmond \
    --email owner@starmond.com --password "ChooseAStrongPassword!2026"
python manage.py runserver
```

`bootstrap_starmond` is idempotent. It seeds business settings, six staff roles
with real permission sets, seven delivery zones covering all 36 states + FCT, and
the first administrator.

Verify:

```bash
curl http://127.0.0.1:8000/health/
curl http://127.0.0.1:8000/api/v1/products/
curl http://127.0.0.1:8000/robots.txt
```

Interactive API docs: `http://127.0.0.1:8000/api/docs/`
(OpenAPI schema at `/api/schema/`.)

---

## 3. First administrator

```bash
python manage.py createsuperuser --email owner@starmond.com
# or, to get the full bootstrap (roles + zones + settings):
python manage.py bootstrap_starmond --email owner@starmond.com --password "..."
```

Then sign in at `/admin/` (Django admin, for raw data) or use the API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"owner@starmond.com","password":"..."}'
```

---

## 4. Day-to-day operations

### Manage categories
```
POST   /api/v1/catalogue/admin/            create (optionally nested via parent_id)
PATCH  /api/v1/catalogue/admin/{id}/       rename, re-parent, publish
DELETE /api/v1/catalogue/admin/{id}/       only when empty
```
Categories nest to 10 levels. Publishing a subcategory requires a published parent.

### Manage products
```
POST   /api/v1/products/admin/                       create (SKU must be unique)
PATCH  /api/v1/products/admin/{id}/                  update; price changes are audited
POST   /api/v1/products/admin/{id}/publish/          go live
POST   /api/v1/products/admin/{id}/unpublish/        back to draft
POST   /api/v1/products/admin/{id}/variations/       add a variant (own SKU/price/stock)
POST   /api/v1/products/admin/{id}/images/           multipart upload
```

### Manage stock
```
GET  /api/v1/inventory/                 all stock rows (5 = low filter)
POST /api/v1/inventory/receive/         stock in
POST /api/v1/inventory/adjust/          stock take to an absolute value
POST /api/v1/inventory/write-off/       damage / loss
GET  /api/v1/inventory/movements/       append-only ledger
```
`available_quantity` is always `quantity_on_hand − quantity_reserved`, and it can
never be driven negative or sold below zero.

### Process orders
```
GET  /api/v1/orders/admin/                                  queue with filters
GET  /api/v1/orders/admin/{order_number}/                   detail + allowed transitions
POST /api/v1/orders/admin/{order_number}/transition/        move status
POST /api/v1/shipping/admin/shipments/{order_number}/       create shipment → tracking ref
POST /api/v1/shipping/admin/shipments/{ref}/events/         record a real tracking event
```
Valid transitions only: `pending_payment → paid → processing → packing →
dispatched → out_for_delivery → delivered → completed`, plus `cancelled`/`expired`
before dispatch. Anything else returns `409 invalid_state_transition`.

### Process refunds
```
GET  /api/v1/refunds/admin/                      queue
POST /api/v1/refunds/admin/{id}/approve/         approve (optionally restock)
POST /api/v1/refunds/admin/{id}/reject/          reject with a reason
POST /api/v1/refunds/admin/{id}/submit/          submit to Paystack  → status: processing
POST /api/v1/refunds/admin/{id}/check/           poll provider      → status: completed | failed
```
A refund is **never** completed because it was submitted — only when Paystack
confirms the money actually moved.

### Reports
```
GET /api/v1/reports/summary/?start=2026-01-01&end=2026-01-31
GET /api/v1/reports/full/
GET /api/v1/reports/export/csv|xlsx|pdf/
```

### SEO
```
GET /                                           server-rendered home page
GET /shop?q=&page=2                             server-rendered catalogue with search
GET /category/electronics/phones                server-rendered category page
GET /product/galaxy-a15                         server-rendered product page
GET /page/delivery-policy                       server-rendered CMS page
GET /sitemap.xml                                crawlable XML sitemap
GET /robots.txt                                 private paths disallowed + sitemap link
GET /api/v1/seo/metadata/?path=/product/slug    metadata for any public path
GET /api/v1/products/{slug}/                    includes a complete `seo` block
```

The rendered pages are plain Django templates in `templates/seo/` — inline CSS, no
external assets, no build step — so search engines index the catalogue without
executing JavaScript. Each page carries its own `<title>`, meta description,
canonical link, Open Graph tags and JSON-LD (`Organization`, `WebSite`, `Product`
with live `availability`, `CollectionPage`, `BreadcrumbList`).

Editing metadata (admin → SEO → settings, or the `meta_*` fields on a product or
category) changes both the rendered page and the JSON API, because both read the
same `SEOService`. A trailing-slash or non-canonical variant returns **301** to the
canonical URL. Add 301/302 rules under SEO → redirects; the fallback route honours
them and counts hits.

The JS storefront, if you run one, should use the same canonical URLs or consume
`/api/v1/seo/metadata/` so the two surfaces never disagree.

---

## 5. Scheduled jobs (cron)

```cron
*/5  * * * *  cd /srv/starmond/backend && .venv/bin/python manage.py expire_stale_orders
*/10 * * * *  cd /srv/starmond/backend && .venv/bin/python manage.py expire_stock_reservations
*/15 * * * *  cd /srv/starmond/backend && .venv/bin/python manage.py reconcile_payments
*/30 * * * *  cd /srv/starmond/backend && .venv/bin/python manage.py reconcile_refunds
0    3 * * *  cd /srv/starmond/backend && .venv/bin/python manage.py check_inventory
0    4 * * *  cd /srv/starmond/backend && .venv/bin/python manage.py purge_idempotency_keys
```

`reconcile_payments` is the safety net for a missed webhook: it re-verifies every
pending payment with Paystack and settles the ones that were genuinely paid.

---

## 6. Paystack setup

1. Create a Paystack account and copy the **test** keys into `.env`.
2. Set `PAYSTACK_MODE=test` while developing. The app **refuses** to run live keys
   unless `PAYSTACK_MODE=live` and `DEBUG=False`.
3. Add the webhook URL in the Paystack dashboard:
   `https://api.starmond.com/api/v1/payments/webhook/paystack/`
4. Point `PAYSTACK_CALLBACK_URL` at the frontend return page.

Security properties:

- the secret key never leaves the server and never appears in a response or log;
- a payment is only recognised after `GET /transaction/verify/{reference}` returns
  success **with a matching amount and currency**;
- the browser redirect is treated as a hint only;
- webhooks are HMAC-SHA512 verified, stored once per unique event key, and then
  re-verified with Paystack before any money is recognised;
- duplicate deliveries, replays and double payments cannot double-count revenue.

### Testing a webhook locally
```bash
python - <<'PY'
import hashlib, hmac, json, os, requests
secret = os.environ["PAYSTACK_WEBHOOK_SECRET"]
body = json.dumps({"event":"charge.success","data":{"reference":"STM-...", "id":123}}).encode()
sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
print(requests.post("http://127.0.0.1:8000/api/v1/payments/webhook/paystack/",
                    data=body, headers={"x-paystack-signature": sig,
                                        "Content-Type":"application/json"}).text)
PY
```

---

## 7. Email setup

Development uses the console backend (emails print to the terminal). For
production set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` plus
host/port/credentials. All transactional emails are logged in `EmailLog`, are
de-duplicated per business event, and **never** roll back a payment if delivery
fails. Templates live in `templates/emails/` (HTML + plain text).

---

## 8. Media storage

Local `MEDIA_ROOT` by default. To use S3 or similar, set
`DEFAULT_FILE_STORAGE` to your storage backend class and `PIPELINE` variables.
Uploads are validated for type and size (`MAX_UPLOAD_SIZE_BYTES`), and every
asset is registered in the media library with a checksum.

---

## 9. Production deployment

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
export DJANGO_DEBUG=False
export DJANGO_SECRET_KEY="<50+ random chars>"
export DJANGO_ALLOWED_HOSTS="api.starmond.com"
export DB_ENGINE=postgres
export CORS_ALLOWED_ORIGINS="https://starmond.com,https://www.starmond.com"
export CSRF_TRUSTED_ORIGINS="https://starmond.com"
export PAYSTACK_MODE=live
export PAYSTACK_SECRET_KEY="sk_live_..."
export PAYSTACK_PUBLIC_KEY="pk_live_..."
export EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
export REDIS_URL="redis://127.0.0.1:6379/1"   # shared cache: makes throttling global
export SITE_URL="https://starmond.com"        # canonical URLs, sitemap, OG tags

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py bootstrap_starmond --email owner@starmond.com --password "..."
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 60
```

`config/settings/production.py` fails closed: it raises at boot if the secret key
is default, `ALLOWED_HOSTS` is empty, Paystack is unconfigured, CORS is empty, or
a console email backend is configured. It also enables HSTS, secure cookies, the
HTTPS redirect and hashed static file names (`ManifestStaticFilesStorage`).

**Cache and throttling.** Without `REDIS_URL` Django uses `LocMemCache`, which is
per-process — with four Gunicorn workers each worker counts throttles separately.
Set `REDIS_URL` so rate limits and cached settings are shared across all workers.

**Category depth.** The taxonomy is unlimited; `MAX_CATEGORY_DEPTH` (default 25,
env-tunable) only prevents absurdly deep URLs.

Nginx (sketch):

```nginx
server {
    listen 443 ssl http2;
    server_name api.starmond.com;
    location /static/ { alias /var/www/starmond/staticfiles/; }
    location /media/  { alias /var/www/starmond/media/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 10m;
    }
}
```

---

## 10. Testing

```bash
python manage.py test tests --settings=config.settings.development
```

222 tests cover catalogue, cart, checkout, Buy Now isolation, inventory
concurrency, the order state machine, payment verification, webhook signatures
and replays, refunds, authentication, RBAC, reporting integrity, SEO, the
rendered public pages and API security — plus a full end-to-end acceptance flow.

The suite runs in about 45 seconds against an in-memory SQLite database and never
contacts Paystack (the provider is stubbed at the `requests` boundary). Run it
against your production database engine before launch:

```bash
DB_ENGINE=postgresql DB_NAME=starmond_test … python manage.py test tests
```

---

## 11. Project layout

```
backend/
├── config/            settings (base/development/production), urls, wsgi, asgi
├── apps/              21 domain apps (accounts … seo)
│   └── <app>/         models · services · serializers · views · urls · admin · migrations
├── services/          stable re-export surface for every service
├── templates/emails/  branded transactional email templates
├── templates/seo/     server-rendered storefront pages
├── tests/             222 automated tests
├── manage.py · requirements.txt · .env.example · README.md
```

Business logic lives in `services.py` (or `checkout.py` / `pricing.py` / `paystack.py`),
never in views. The request lifecycle is uniform:

```
REQUEST → VALIDATION → AUTHORIZATION → SERVICE → TRANSACTION → AUDIT → NOTIFY → RESPONSE
```

---

## 12. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `payment_not_configured` | `PAYSTACK_SECRET_KEY` missing |
| `paystack_mode_mismatch` | Live key with `PAYSTACK_MODE=test` — use test keys |
| `paystack_live_blocked_in_debug` | Live mode with `DEBUG=True` — intended guard |
| Order stuck in `pending_payment` | Customer did not pay, or a webhook was missed → run `reconcile_payments` |
| `insufficient_stock` at checkout | Another customer holds the last units; the hold expires with `expire_stock_reservations` |
| Refund stuck in `processing` | Awaiting Paystack → run `reconcile_refunds` or POST `/check/` |
| `invalid_state_transition` | The lifecycle order was skipped — see §4 |
| Emails not arriving | Inspect `EmailLog`; a failure never blocks a payment |
| `discrepancy_count > 0` in reports | Payment/order totals disagree — inspect the flagged orders immediately |

---

© STARMOND TECHNOLOGY LIMITED. Single-owner multi-category retail platform.
