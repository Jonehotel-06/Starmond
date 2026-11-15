#!/usr/bin/env node
/**
 * prerender.mjs — build-time SEO rendering for catalogue pages.
 *
 * This is the answer to "SEO must not depend on client-side JavaScript" while
 * staying on pure HTML/CSS/Vanilla JS. At build time we read the public API and
 * emit a real static HTML file for every active category and product:
 *
 *   /shop/<slug>/index.html          (and nested subcategory paths)
 *   /products/<slug>/index.html
 *   /sitemap.xml
 *
 * Each file contains the real title, meta description, canonical, Open Graph,
 * JSON-LD (Product/Offer/BreadcrumbList), an H1, the description, crawlable
 * internal links and the server-rendered price/availability. The same Vanilla
 * JS module then hydrates the interactive parts in the browser.
 *
 * Run AFTER the backend is reachable:
 *   SITE_URL=https://store.example API_BASE_URL=https://api.example/api \
 *     node tools/prerender.mjs
 *
 * If the API is unreachable this exits non-zero WITHOUT writing fake pages.
 * The runtime fallback pages (category.html / product.html) plus the host
 * rewrite rules in deploy/ still serve correct URLs in that case.
 */
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { storefrontPage, baseJsonLd, escapeHtml } from './lib/shell.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

const SITE_URL = (process.env.SITE_URL || '').replace(/\/$/, '');
const API_BASE_URL = process.env.API_BASE_URL || '/api';
const LIMIT = Number(process.env.PRERENDER_LIMIT || 5000);

if (!SITE_URL) {
  console.error('SITE_URL is required for pre-rendering (canonical URLs must be absolute).');
  process.exit(1);
}
if (!/^https?:\/\//i.test(API_BASE_URL)) {
  console.error('API_BASE_URL must be an absolute URL at build time (the build has no reverse proxy).');
  process.exit(1);
}

const origin = SITE_URL;
const strip = (html = '') => String(html).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
const truncate = (text, max = 158) => (text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`);
const money = (value, currency = 'NGN') => {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return new Intl.NumberFormat('en-NG', { style: 'currency', currency, currencyDisplay: 'narrowSymbol', maximumFractionDigits: n % 1 ? 2 : 0 }).format(n);
};

async function apiGet(path, params = {}) {
  const url = new URL(`${API_BASE_URL}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null) url.searchParams.set(k, String(v)); });
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);
  return response.json();
}

async function fetchAll(path, params = {}) {
  const out = [];
  let page = 1;
  while (out.length < LIMIT) {
    const data = await apiGet(path, { ...params, page, page_size: 100 });
    const results = Array.isArray(data) ? data : data.results || [];
    out.push(...results);
    if (!data.next || results.length === 0) break;
    page += 1;
  }
  return out;
}

function categoryPath(category, byId) {
  if (category.path) return `/shop/${String(category.path).replace(/^\/+|\/+$/g, '')}/`;
  const segments = [];
  let node = category;
  const seen = new Set();
  while (node && !seen.has(node.id)) {
    seen.add(node.id);
    segments.unshift(node.slug);
    node = typeof node.parent === 'object' ? node.parent : byId.get(String(node.parent));
  }
  return `/shop/${segments.join('/')}/`;
}

function productCardHtml(product) {
  const price = money(product.price ?? product.current_price, product.currency);
  const compare = money(product.compare_at_price, product.currency);
  const image = product.images?.[0]?.url || product.image_url || product.image;
  const url = `/products/${product.slug}/`;
  return `<article class="product-card">
    <a class="product-card__media" href="${escapeHtml(url)}" tabindex="-1" aria-hidden="true">
      ${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(product.images?.[0]?.alt || product.name)}" width="600" height="600" loading="lazy" decoding="async">` : ''}
    </a>
    <div class="product-card__body">
      <h3 class="product-card__name t-clamp-2"><a href="${escapeHtml(url)}">${escapeHtml(product.name)}</a></h3>
      <span class="price-row">${price ? `<span class="price">${escapeHtml(price)}</span>` : '<span class="t-meta">Price unavailable</span>'}
      ${compare && product.compare_at_price > product.price ? `<span class="price price--original">${escapeHtml(compare)}</span>` : ''}</span>
      ${product.stock_status ? `<span class="product-card__stock">${escapeHtml(String(product.stock_status).replace(/_/g, ' '))}</span>` : ''}
    </div>
  </article>`;
}

function breadcrumbHtml(items) {
  return `<nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list">${
    items.map((item, i) => `<li class="breadcrumbs__item">${
      i < items.length - 1 && item.url ? `<a href="${escapeHtml(item.url)}">${escapeHtml(item.name)}</a>` : `<span aria-current="page">${escapeHtml(item.name)}</span>`
    }</li>`).join('')}</ol></nav>`;
}

function breadcrumbLd(items) {
  return {
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: items.map((item, i) => ({
      '@type': 'ListItem', position: i + 1, name: item.name,
      ...(item.url ? { item: `${origin}${item.url}` } : {}),
    })),
  };
}

async function writePage(relative, html) {
  const target = join(root, relative);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html, 'utf8');
}

/* ------------------------------------------------------------------ main -- */

console.log(`Pre-rendering from ${API_BASE_URL} …`);

let categories;
let products;
try {
  categories = await fetchAll('/categories/', { active: 1 });
  products = await fetchAll('/products/', { active: 1 });
} catch (error) {
  console.error(`\nPre-render aborted: the API is not reachable.\n  ${error.message}`);
  console.error('No pages were written. Deploy the runtime fallbacks, or re-run once the API is live.');
  process.exit(2);
}

const byId = new Map(categories.map((c) => [String(c.id), c]));
const sitemap = [
  { loc: '/', priority: '1.0', changefreq: 'daily' },
  { loc: '/shop.html', priority: '0.9', changefreq: 'daily' },
  { loc: '/about.html', priority: '0.5', changefreq: 'monthly' },
  { loc: '/contact.html', priority: '0.5', changefreq: 'monthly' },
  { loc: '/faq.html', priority: '0.5', changefreq: 'monthly' },
  { loc: '/policies/privacy.html', priority: '0.3', changefreq: 'yearly' },
  { loc: '/policies/terms.html', priority: '0.3', changefreq: 'yearly' },
  { loc: '/policies/shipping.html', priority: '0.4', changefreq: 'yearly' },
  { loc: '/policies/returns.html', priority: '0.4', changefreq: 'yearly' },
];

let written = 0;

for (const category of categories) {
  const path = categoryPath(category, byId);
  const trail = [];
  let node = category;
  const seen = new Set();
  while (node && !seen.has(node.id)) { seen.add(node.id); trail.unshift(node); node = typeof node.parent === 'object' ? node.parent : byId.get(String(node.parent)); }

  const crumbs = [{ name: 'Home', url: '/' }, { name: 'Shop', url: '/shop.html' }, ...trail.map((c) => ({ name: c.name, url: categoryPath(c, byId) }))];
  const categoryProducts = products.filter((p) => String(p.category?.id ?? p.category) === String(category.id)).slice(0, 24);
  const description = truncate(strip(category.seo?.description || category.description || `Shop ${category.name} at Starmond Technology Limited.`));

  const body = `<div class="container">
  <div class="page-head">
    ${breadcrumbHtml(crumbs)}
    <h1 class="page-head__title" data-listing-title>${escapeHtml(category.name)}</h1>
    <p class="page-head__sub" data-listing-description>${escapeHtml(strip(category.description || ''))}</p>
  </div>
  ${category.banner_url ? `<div class="category-banner"><img src="${escapeHtml(category.banner_url)}" alt="${escapeHtml(category.banner_alt || category.name)}" width="1600" height="320" decoding="async"></div>` : ''}
  ${category.children?.length ? `<div class="subcategory-tiles">${category.children.map((child) => `<a class="category-tile" href="${escapeHtml(categoryPath(child, byId))}">${escapeHtml(child.name)}</a>`).join('')}</div>` : ''}
  <div class="listing">
    <aside class="listing__sidebar" id="filters" data-filters aria-label="Product filters">
      <div class="cluster cluster--between"><h2 class="t-md t-semibold">Filters</h2><button type="button" class="link-btn" data-filters-clear>Clear all</button></div>
      <div data-filters-body></div>
    </aside>
    <div class="listing__main">
      <div class="listing-toolbar">
        <p class="listing-toolbar__count" data-listing-count aria-live="polite">${categoryProducts.length} product${categoryProducts.length === 1 ? '' : 's'}</p>
        <div class="listing-toolbar__controls">
          <button type="button" class="btn btn--secondary btn--sm mobile-filter-trigger" data-filters-toggle aria-expanded="false" aria-controls="filters">Filters</button>
          <label class="sr-only" for="listing-sort">Sort products</label>
          <select class="select" id="listing-sort" data-listing-sort>
            <option value="featured">Featured</option><option value="newest">Newest</option>
            <option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option>
            <option value="best_selling">Best selling</option><option value="rating">Highest rated</option>
          </select>
        </div>
      </div>
      <div class="active-filters" data-active-filters></div>
      <div data-listing-results data-loading-region aria-busy="false">
        <div class="product-grid">${categoryProducts.map(productCardHtml).join('')}</div>
      </div>
      <nav class="pagination" data-listing-pagination aria-label="Product pagination"></nav>
    </div>
  </div>
</div>`;

  const html = storefrontPage({
    title: category.seo?.title || `${category.name} — Starmond Technology Limited`,
    description,
    path: `${origin}${path}`,
    canonical: `${origin}${category.seo?.canonical || path}`,
    ogImage: category.image_url || `${origin}/assets/images/og-default.png`,
    module: '/assets/js/pages/listing.js',
    jsonLd: [...baseJsonLd(origin), breadcrumbLd(crumbs), {
      '@context': 'https://schema.org', '@type': 'CollectionPage',
      name: category.name, url: `${origin}${path}`, isPartOf: { '@id': `${origin}/#website` },
    }],
  }, body);

  await writePage(`${path.replace(/^\//, '')}index.html`, html);
  sitemap.push({ loc: path, priority: '0.8', changefreq: 'daily', lastmod: category.updated_at });
  written += 1;
}

for (const product of products) {
  const path = `/products/${product.slug}/`;
  const price = product.price ?? product.current_price;
  const currency = product.currency || 'NGN';
  const images = (product.images || []).map((i) => i.url || i).filter(Boolean);
  const category = typeof product.category === 'object' ? product.category : byId.get(String(product.category));
  const crumbs = [{ name: 'Home', url: '/' }, { name: 'Shop', url: '/shop.html' }];
  if (category) crumbs.push({ name: category.name, url: categoryPath(category, byId) });
  crumbs.push({ name: product.name, url: path });

  const availability = product.stock_status === 'out_of_stock' ? 'https://schema.org/OutOfStock' : 'https://schema.org/InStock';
  const jsonLd = [...baseJsonLd(origin), breadcrumbLd(crumbs), {
    '@context': 'https://schema.org', '@type': 'Product',
    name: product.name, url: `${origin}${path}`,
    ...(product.description ? { description: truncate(strip(product.description), 5000) } : {}),
    ...(images.length ? { image: images } : {}),
    ...(product.sku ? { sku: product.sku } : {}),
    ...(product.brand ? { brand: { '@type': 'Brand', name: typeof product.brand === 'string' ? product.brand : product.brand.name } } : {}),
    ...(price != null ? {
      offers: { '@type': 'Offer', url: `${origin}${path}`, price: Number(price), priceCurrency: currency, availability, itemCondition: 'https://schema.org/NewCondition' },
    } : {}),
    ...(product.rating_count > 0 && product.rating_average != null ? {
      aggregateRating: { '@type': 'AggregateRating', ratingValue: product.rating_average, reviewCount: product.rating_count, bestRating: 5, worstRating: 1 },
    } : {}),
  }];

  const specs = Array.isArray(product.specifications) ? product.specifications : Object.entries(product.specifications || {}).map(([name, value]) => ({ name, value }));

  const body = `<div class="container">
  <div class="page-head" data-product-breadcrumbs>${breadcrumbHtml(crumbs)}</div>
  <div data-product-region data-loading-region aria-busy="false">
    <div class="pdp">
      <div class="pdp__gallery">
        <div class="pdp__main">${images[0] ? `<img src="${escapeHtml(images[0])}" alt="${escapeHtml(product.images?.[0]?.alt || product.name)}" width="800" height="800" fetchpriority="high" decoding="async" data-gallery-image>` : ''}</div>
        ${images.length > 1 ? `<div class="pdp__thumbs">${images.map((image, i) => `<button type="button" class="pdp__thumb" data-gallery-thumb="${i}" aria-current="${i === 0}"><img src="${escapeHtml(image)}" alt="" width="120" height="120" loading="lazy"></button>`).join('')}</div>` : ''}
      </div>
      <div class="pdp__info">
        <div class="pdp__head">
          ${product.brand ? `<span class="pdp__brand">${escapeHtml(typeof product.brand === 'string' ? product.brand : product.brand.name)}</span>` : ''}
          <h1 class="pdp__title">${escapeHtml(product.name)}</h1>
          <div class="pdp__meta">${product.sku ? `<span>SKU: <strong>${escapeHtml(product.sku)}</strong></span>` : ''}</div>
        </div>
        <div class="pdp__price-block">
          <div class="price-row">${money(price, currency) ? `<span class="price pdp__price">${escapeHtml(money(price, currency))}</span>` : '<span class="t-muted">Price unavailable</span>'}
          ${product.compare_at_price > price ? `<span class="price price--original">${escapeHtml(money(product.compare_at_price, currency))}</span>` : ''}</div>
          ${product.stock_status ? `<span class="product-card__stock">${escapeHtml(String(product.stock_status).replace(/_/g, ' '))}</span>` : ''}
        </div>
        ${product.short_description ? `<p class="pdp__short">${escapeHtml(product.short_description)}</p>` : ''}
        <div data-variant-groups></div>
        <div class="pdp__buy"><div data-pdp-hydration-note class="t-sm t-muted">Loading purchase options…</div></div>
      </div>
    </div>
  </div>
  <section class="pdp-section">
    <h2 class="t-xl t-semibold">Product description</h2>
    <div class="prose" style="margin-top:1rem">${product.description || `<p>${escapeHtml(product.short_description || '')}</p>`}</div>
    ${specs.length ? `<h2 class="t-xl t-semibold" style="margin-top:2rem">Specifications</h2>
      <table class="spec-table" style="margin-top:1rem"><tbody>${specs.map((s) => `<tr><th scope="row">${escapeHtml(s.name || s.label)}</th><td>${escapeHtml(s.value)}</td></tr>`).join('')}</tbody></table>` : ''}
  </section>
</div>`;

  const html = storefrontPage({
    title: product.seo?.title || `${product.name} — Starmond Technology Limited`,
    description: truncate(strip(product.seo?.description || product.short_description || product.description || `Buy ${product.name} from Starmond Technology Limited.`)),
    path: `${origin}${path}`,
    canonical: `${origin}${product.seo?.canonical || path}`,
    ogType: 'product',
    ogImage: images[0] || `${origin}/assets/images/og-default.png`,
    preloadImage: images[0],
    module: '/assets/js/pages/product.js',
    jsonLd,
  }, body);

  await writePage(`products/${product.slug}/index.html`, html);
  sitemap.push({ loc: path, priority: '0.7', changefreq: 'weekly', lastmod: product.updated_at, images });
  written += 1;
}

const sitemapXml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
${sitemap.map((entry) => `  <url>
    <loc>${origin}${entry.loc}</loc>
${entry.lastmod ? `    <lastmod>${new Date(entry.lastmod).toISOString().slice(0, 10)}</lastmod>\n` : ''}    <changefreq>${entry.changefreq}</changefreq>
    <priority>${entry.priority}</priority>
${(entry.images || []).slice(0, 5).map((image) => `    <image:image><image:loc>${image.startsWith('http') ? image : origin + image}</image:loc></image:image>`).join('\n')}
  </url>`).join('\n')}
</urlset>
`;
await writeFile(join(root, 'sitemap.xml'), sitemapXml, 'utf8');

console.log(`Pre-rendered ${written} catalogue pages (${categories.length} categories, ${products.length} products).`);
console.log('Wrote sitemap.xml.');
