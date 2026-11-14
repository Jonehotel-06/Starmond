# Automated test results

## Final run summary

- `node tests/static-checks.mjs` — PASS; 45 modules, 58 pages, 8 CSS files; 0 failures.
- `node tests/smoke.mjs` — PASS; 56/56; 0 console errors and 0 failed requests.
- `node tests/workflows.mjs` — PASS; 28/28 assertions across 12 journeys.
- `node tests/responsive.mjs` — PASS; 168/168 combinations, 14 viewport widths × 12 pages.
- `node tests/accessibility.mjs` — PASS; 12 routes, 0 WCAG 2.1 A/AA axe violation nodes.
- `node tests/seo.mjs` — PASS; 58 HTML docs, 9 indexable, 49 noindex, 0 issues.
- `node --check` for responsive/workflow scripts — PASS. All application JS modules passed static syntax/import validation.

## Notable journey assertions

Backend cart persistence and count; Buy Now leaves cart unchanged and sends direct items; cart checkout omits frontend-authoritative line items; payment failure overrides a success URL after backend verification; stock maximum and out-of-stock disablement; variation selection; search debounce; guest cart reload; admin table/create dialog/Escape close; guest admin redirect; backend coupon validation and discounted total.

Raw test output and detailed per-case data are in `../../../reports/`. The test API is a local deterministic fixture, not a production service.