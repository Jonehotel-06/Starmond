# Known issues and production handoff

## Environment-specific items to configure

1. Supply the real storefront `SITE_URL`; the delivery has no assumed production domain. Generate config and prerendered category/product routes only after this is set.
2. Connect the real backend and confirm endpoint shapes, cookie/session settings, CSRF, allowed origins, permissions, shipping/tax rules, catalogue content and error semantics. Local QA used a deterministic mock, not a live backend.
3. Configure the real Paystack/backend payment integration, webhook/signature handling, redirect origins and reconciliation. The frontend verifies payment references through the API; no live payment transaction was run.
4. Confirm business contact details, policies, delivery options, product images, SEO copy and admin permissions with the business. API-backed settings may replace shell defaults.
5. Review CSP, HSTS, cookie `Secure`/`HttpOnly`/`SameSite`, cache headers, rate limits, backup/monitoring and deployment access controls with the backend/hosting team.

## Explicit boundaries

- `robots.txt` does not secure pages; server/API authorization must do so.
- Mock login and seed data are for QA only. The mock API is under `tests/fixtures/` and must not be deployed as a backend.
- `.env` QA overrides were removed; `config.js` was restored to production-safe defaults. The provided `SITE_URL` example is documentation only.
- Prerender requires API access and an absolute site URL; it intentionally aborts without them and does not emit fake catalogue pages.
- Automated accessibility covered 12 representative routes; it is not a manual audit or a full 58-page assistive-technology review.
- No production Web Vitals, load test, live payment test or deployment smoke test is available in this workspace.