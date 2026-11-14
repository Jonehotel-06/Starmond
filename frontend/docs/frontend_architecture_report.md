# Frontend architecture report

## Runtime model

The application is static HTML with CSS and native browser ES modules. `tools/build-pages.mjs` creates each route from shared `tools/lib/shell.mjs` and page definitions in `tools/pages/`. The shared shell provides metadata, navigation, footer, drawers/dialogs, theme/config hooks and page module loading. Browser code is divided into common services (`utils`, `config`, `api`, `auth`, `cart`, `products`, `categories`, `navigation`, `search`, `site`, `ui`) and page-specific storefront/admin modules.

## Data and trust boundaries

The same-origin API base defaults to `/api/v1`; deployment may reverse-proxy it or inject a public HTTPS API root. `assets/js/api.js` centralizes credentialed requests, CSRF, cart token, safe retries, list normalization, request errors, public caching/deduplication and private uncached reads. The backend remains authoritative for price, stock, totals, discounts, orders and payment status. No Paystack secret is present in browser code.

Session authentication uses cookies and CSRF; the local session hint is only a request optimization. Private page and admin entry points force session probes and share in-flight checks. Authorization is still enforced by backend permissions. Cart isolation is keyed by a browser-held cart token; local storage is not a trusted order source.

## Storefront flow

Product/category/search modules render API results and support URL routes. Product variation selection updates price/stock/availability and quantity limits. Add-to-cart changes backend state. Buy Now stores a short-lived session intent and submits its explicit product line independently of the cart. Cart checkout lets the API own cart items/totals; checkout preview and coupon checks are backend calls. Payment result pages verify references against the API; URL state alone cannot declare a payment successful.

## Admin flow

Admin page definitions share a sidebar/topbar shell. `AdminTable` supplies table/list rendering, selection, filters, pagination and module-specific operations; module access defaults to permission keys and backend authorization remains mandatory. Dashboard data is fetched from dedicated report/inventory endpoints.

## Styling and accessibility

Eight layered stylesheets separate design tokens, typography, reusable components, shell, storefront/admin page styles, skeletons and responsive behavior. Mobile/tablet breakpoints cover widths from 320 px through desktop. Off-canvas drawers/sidebars are closed by default on small screens; tables become responsive cards. Focus, labels, dialog semantics, target sizes and text-link cues are included. Twelve representative pages passed automated axe WCAG 2.1 A/AA checks after contrast corrections.

## PWA/deployment

The manifest/icons and optional service worker provide install/offline shell behavior. Private/admin/API content is excluded from service-worker caching. Hosting examples route clean category/product paths to generated output or runtime fallback pages and proxy API/media/sitemap paths. Build-time prerender requires a reachable public API plus a real absolute `SITE_URL`.