/**
 * Client-side metadata hydration.
 *
 * IMPORTANT — SEO contract: the public pages are generated as static HTML with
 * unique titles, descriptions, canonicals and JSON-LD already in the document
 * (see source/build.py and reports/SEO_STRATEGY.md). Product and category data
 * that only exists at runtime is *hydrated* here, never left to JavaScript
 * alone: production must serve /product/<slug>/ through the server-side render
 * described in the SEO strategy document. This module keeps the runtime view
 * consistent (share links, structured data, history entry titles).
 */
import { CONFIG } from './env.js';

function upsertMeta(selector, attrs) {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement('meta');
    Object.entries(attrs.name ? { name: attrs.name } : { property: attrs.property }).forEach(([k, v]) => el.setAttribute(k, v));
    document.head.appendChild(el);
  }
  if (attrs.content !== undefined) el.setAttribute('content', attrs.content);
  return el;
}

function absolute(path) {
  if (!path) return CONFIG.SITE_URL || window.location.origin;
  if (/^https?:/i.test(path)) return path;
  return `${(CONFIG.SITE_URL || window.location.origin).replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

export function setMeta({ title, description, canonicalPath, image, type = 'website', robots } = {}) {
  if (title) {
    document.title = title;
    upsertMeta('meta[property="og:title"]', { property: 'og:title', content: title });
    upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: title });
  }
  if (description) {
    upsertMeta('meta[name="description"]', { name: 'description', content: description });
    upsertMeta('meta[property="og:description"]', { property: 'og:description', content: description });
    upsertMeta('meta[name="twitter:description"]', { name: 'twitter:description', content: description });
  }
  if (canonicalPath) {
    const href = absolute(canonicalPath);
    let link = document.head.querySelector('link[rel="canonical"]');
    if (!link) { link = document.createElement('link'); link.rel = 'canonical'; document.head.appendChild(link); }
    link.href = href;
    upsertMeta('meta[property="og:url"]', { property: 'og:url', content: href });
  }
  if (image) {
    const href = absolute(image);
    upsertMeta('meta[property="og:image"]', { property: 'og:image', content: href });
    upsertMeta('meta[name="twitter:image"]', { name: 'twitter:image', content: href });
  }
  upsertMeta('meta[property="og:type"]', { property: 'og:type', content: type });
  if (robots) upsertMeta('meta[name="robots"]', { name: 'robots', content: robots });
}

export function setJsonLd(id, payload) {
  let script = document.head.querySelector(`script[data-ld="${id}"]`);
  if (!payload) { script?.remove(); return; }
  if (!script) {
    script = document.createElement('script');
    script.type = 'application/ld+json';
    script.dataset.ld = id;
    document.head.appendChild(script);
  }
  script.textContent = JSON.stringify(payload);
}

export function productJsonLd(product, { url, categoryName } = {}) {
  if (!product) return null;
  const price = product.price ?? product.unit_price;
  const inStock = product.in_stock !== false && Number(product.stock_quantity ?? 1) > 0;
  return {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    sku: product.sku || undefined,
    description: (product.meta_description || product.short_description || product.description || '')
      .replace(/<[^>]+>/g, ' ').trim().slice(0, 320),
    image: [product.primary_image].filter(Boolean).map((i) => absolute(typeof i === 'string' ? i : i.url)),
    brand: product.brand ? { '@type': 'Brand', name: product.brand } : undefined,
    category: categoryName || product.category?.name || undefined,
    offers: {
      '@type': 'Offer',
      url: url ? absolute(url) : location.href,
      priceCurrency: product.currency || 'NGN',
      price: price === undefined || price === null ? undefined : String(price),
      availability: inStock ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
      itemCondition: 'https://schema.org/NewCondition',
      seller: { '@type': 'Organization', name: 'STARMOND TECHNOLOGY LIMITED' }
    },
    aggregateRating: product.review_count > 0 && product.rating_average
      ? { '@type': 'AggregateRating', ratingValue: String(product.rating_average), reviewCount: String(product.review_count) }
      : undefined
  };
}

export function breadcrumbJsonLd(trail = []) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.filter(Boolean).map((crumb, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: crumb.name,
      item: crumb.path ? absolute(crumb.path) : undefined
    }))
  };
}
