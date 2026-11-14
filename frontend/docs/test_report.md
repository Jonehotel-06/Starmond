# Test report

Executed 14 November 2026 against local static preview `http://127.0.0.1:5173` and deterministic contract mock `:8000`.

| Suite | Result | Scope |
|---|---:|---|
| Static checks | PASS | 45 JS modules, 58 HTML pages, 8 stylesheets; imports/links/SEO/JSON-LD checks |
| Browser smoke | PASS, 56/56 | All storefront/admin routes; zero console errors, failed requests or stuck skeletons |
| Commerce/admin workflows | PASS, 28/28 | 12 user journeys; add-to-cart, Buy Now isolation, checkout, payment verification, variation/stock, search, coupon and admin auth/table/dialog |
| Responsive | PASS, 168/168 | 12 pages × 14 widths (320–1920 px); no measured overflow, clipped content or undersized applicable targets |
| Accessibility | PASS | axe-core WCAG 2.1 A/AA, 12 representative pages, 0 violation nodes |
| SEO | PASS | 58 HTML documents; 9 indexable, 49 private/noindex, 0 static invariants |
| Prerender build path | PASS (isolated QA copy) | 9 mock categories + 14 mock products → 23 generated routes and sitemap; QA host artifacts discarded |

Machine-readable evidence is under `../../../reports/`: `static_check_results.json`, `browser_smoke_results.json`, `workflow_results.json`, `responsive_results.json`, `accessibility_results.json`, `seo_results.json`.

These results cover local mock-backed QA, not live production services. Detailed scripts live under `../../../tests/`.