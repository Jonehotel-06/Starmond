# Known issues and limitations

Current as of the frontend ↔ backend integration (15 November 2026). The full
list of what was fixed is in `/docs/ISSUE_CHECKLIST.md`; what could not be
verified is in `/docs/TESTING_REPORT.md`.

## Open

1. **Visual redesign not done.** The existing design system was kept and only
   defects were fixed (mobile menu, breadcrumbs, admin tables/forms). A full
   restyle of storefront and admin is still outstanding.
2. **The other reports in this folder are out of date.** `test_report.md`,
   `implementation_report.md`, `frontend_architecture_report.md`,
   `changed_files_manifest.md` and the `*_test_results.md` files describe the
   frontend before it was connected to the real API (they mention `/api/v1` and
   JWT). Treat them as history.
3. **`backend/docs/openapi-schema.yml` was not regenerated** and lacks the
   endpoints added during integration (CSRF, delivery states, checkout preview,
   facets, related products, recent reviews, media).
4. **No product brands endpoint, search suggestions, or FAQ API.** The related
   UI was removed or falls back (FAQ is a CMS page).
5. **Promotions limited to specific products take product IDs typed by hand**
   (comma-separated) — there is no product picker yet.
6. **Admin → Customers is read-only** and lists customer profiles, which
   includes staff who have shopped; the dashboard "Customers" figure counts
   non-staff accounts, so the two numbers can differ.
7. **Registration stays on the form** after success rather than moving to the
   account page; the email-verification step was not tested with a real mailbox.
8. **Seed catalogue has no images**, so a fresh install shows placeholders until
   images are uploaded in Admin → Products.
9. Anonymous visits to account, orders and wishlist log one expected
   `403 /api/auth/me/` in the browser console before redirecting to sign-in.

## Local-development notes

- Use `http://localhost:5173`. `127.0.0.1` is a different origin and is rejected
  by CSRF checks unless added to `CSRF_TRUSTED_ORIGINS`.
- Do not run `node tools/build-pages.mjs` with `SITE_URL` set unless building for
  that domain — it rewrites canonical links in every page.
- The payment redirect accepts a `localhost` gateway only when the page itself
  is served from `localhost` (for the mock gateway in `tests/e2e/`).
