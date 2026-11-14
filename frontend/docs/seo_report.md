# SEO implementation report

## Implemented

- Page-specific title, meta description, canonical URL, robots directive, Open Graph/Twitter metadata and base Organization/WebSite/SearchAction JSON-LD are generated in the HTML shell.
- Product/category/search query fallbacks are marked noindex where they would duplicate clean URLs; admin, account, cart, checkout, payment, auth and other private/transactional routes are noindex/nofollow and disallowed in `robots.txt` as appropriate.
- `tools/prerender.mjs` fetches the active catalogue at build time and emits `/shop/<path>/index.html`, `/products/<slug>/index.html`, Product/Offer and BreadcrumbList JSON-LD, crawlable links, canonical metadata and `sitemap.xml`.
- `robots.txt` intentionally has no fake absolute sitemap host in this delivery. `tools/write-config.mjs` injects the sitemap host only after a real `SITE_URL` is supplied.

## QA results

`tests/seo.mjs`: PASS for 58 HTML documents, with 9 indexable and 49 private/noindex documents; no duplicate indexable titles, missing descriptions/canonicals/robots directives/H1s, malformed JSON-LD, or robots exclusions. The static-check suite also passed its SEO and structured-data invariants.

The prerenderer was run in an isolated QA copy using the deterministic local API and a reserved `.invalid` host: 9 categories and 14 products generated 23 catalogue pages and a sitemap. This QA output was deliberately not copied into the deliverable, so no placeholder canonical URL ships.

## Production requirement

Configure the actual canonical origin and a public API endpoint at build time, run `node tools/write-config.mjs`, then run `node tools/prerender.mjs` with API access. Publish the resulting catalogue routes and sitemap, and confirm canonical URLs, product availability/pricing, image URLs, robots behavior and sitemap reachability against the deployed domain. `robots.txt` is guidance, not access control.