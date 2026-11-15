# Starmond

Online store for STARMOND TECHNOLOGY LIMITED: a Django REST backend and a static
(no-build-step) storefront + admin console.

```
backend/    Django 5.2 + DRF API (MySQL in production, SQLite for local work)
frontend/   Static HTML/CSS/ES-module site: storefront, customer account, admin console
tests/e2e/  Browser tests that drive the real UI against a running stack
docs/       Integration issue checklist and testing report
```

## Run it locally

Needs Python 3.11+ and Node 20+.

```bash
# 1. Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # skip mysqlclient if you only use SQLite
cp .env.example .env                       # then set DB_ENGINE=sqlite, DEBUG=True and
                                           # CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS=http://localhost:5173
python manage.py migrate
python manage.py seed_roles
python manage.py seed_demo_catalog         # optional demo products
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000

# 2. Frontend (second terminal)
cd frontend
node tools/build-pages.mjs                 # regenerates every HTML page from tools/
API_PROXY_TARGET=http://127.0.0.1:8000 python3 tools/serve.py --port 5173
```

Open <http://localhost:5173> (storefront) and <http://localhost:5173/admin/> (console).
Use `localhost`, not `127.0.0.1`, unless you add that origin to `CSRF_TRUSTED_ORIGINS`.

## How the two halves connect

- The browser only ever talks to **its own origin**. `/api/*` and `/media/*` are
  reverse-proxied to Django (`tools/serve.py` locally; `frontend/deploy/` has
  nginx, Netlify and Vercel examples). To use a separate API domain instead, run
  `API_BASE_URL=https://api.example.com/api node tools/write-config.mjs` and set
  the cross-site cookie variables described in `backend/.env.example`.
- Sign-in uses Django's session cookie plus CSRF token (`GET /api/auth/csrf/`).
- Prices, stock, delivery fees, discounts and payment status are always computed
  by the backend. The frontend displays them; it never calculates money.
- Admin screens are shown or hidden from the permission list returned by
  `GET /api/auth/me/`, and every admin route enforces the same permission server-side.

## Tests

```bash
cd backend && DB_ENGINE=sqlite python manage.py test tests      # 127 API tests
```

Browser tests (need `pip install playwright && playwright install chromium`, a
running stack, and the mock payment gateway — see `tests/e2e/README.md`).

## Before going live

Read `docs/TESTING_REPORT.md` → "Not verified here". In short: real Paystack keys
and webhook, MySQL, Redis, object storage and outgoing email were not available
in the environment this was integrated in and must be checked on staging.
