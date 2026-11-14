# Changed files manifest

Delivery root: `changed_files/frontend/`.

## Main application

- `*.html`, `admin/*.html`, `policies/*.html` — 58 generated routes and page shells.
- `assets/css/` — 8 stylesheets: tokens, typography, components, main shell, responsive, skeletons, storefront page styles and admin page styles.
- `assets/js/` — 45 ES modules including shared API/auth/cart/checkout/payment/navigation/UI modules, 17 storefront page modules and 9 admin modules.
- `assets/icons/`, `assets/images/` — favicon/app icons and Open Graph/product fallback artwork.
- `manifest.webmanifest`, `sw.js`, `robots.txt` — PWA/offline and crawler configuration.

## Build and hosting

- `tools/build-pages.mjs`, `tools/lib/shell.mjs`, `tools/pages/{storefront,admin}.mjs` — HTML generation and shared shell.
- `tools/write-config.mjs` — public deployment-config injection.
- `tools/prerender.mjs` — API-backed category/product HTML and sitemap generation.
- `tools/serve.py` — local static server, route fallback and optional same-origin API proxy.
- `deploy/{nginx.conf,netlify.toml,_redirects,vercel.json}` — hosting examples.
- `.env.example`, `.gitignore` — configuration template and local-file exclusions. No QA `.env` is included.

## QA assets

- `tests/{static-checks,smoke,workflows,responsive,accessibility,seo}.mjs` — repeatable validation.
- `tests/fixtures/mock-api.mjs` — deterministic API fixture for local QA.
- `reports/` — machine-readable static, browser, workflow, responsive, accessibility and SEO results.
- `docs/` — implementation, architecture, SEO, performance, source-location, test and known-issue reports.

## Important final configuration state

- `assets/js/config.js` restored to production-safe defaults (same-origin `/api/v1`, session/CSRF mode, service worker enabled by default; preview mode off).
- Local `.env` removed. No mock credentials, domain placeholder in the sitemap directive, payment secret, or QA-only configuration should be deployed.
- Set a real `SITE_URL` and production environment before running `tools/write-config.mjs` and `tools/prerender.mjs`.