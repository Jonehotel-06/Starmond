# Regression test results

Final regression run after production-safe config restoration and QA `.env` removal:

- Static: PASS, 45 JS modules / 58 HTML pages / 8 stylesheets.
- Browser smoke: PASS, 56/56 routes; no console errors, failed requests or stuck skeletons.
- Critical commerce/admin workflows: PASS, 28/28 assertions.
- Responsive suite: PASS, 168/168 page/viewport combinations (layout-affecting CSS changes included; later accessibility fixes changed colors/text decoration only).
- Accessibility: PASS, 12 pages / 0 axe violation nodes.
- SEO: PASS, 58 documents / 0 issues.

Regression coverage is local mock-backed. Live backend, payment provider and deployment-host regressions remain production integration gates. See JSON artifacts in `../../../reports/` and scripts in `../../../tests/`.