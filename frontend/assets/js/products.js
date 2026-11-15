/**
 * products.js — catalogue reads and product presentation.
 *
 * Every price, discount, stock state and rating rendered here was computed by
 * the backend. If a field is absent we show "unavailable" or omit the element —
 * we never substitute an invented value.
 */

import api, { normalizeList } from './api.js';
import { esc, formatMoney, formatNumber } from './utils.js';
import { icon } from './icons.js';
import { categoryUrl } from './categories.js';

/** Storefront product URL. The static site serves product.html for
 *  /products/<slug>/ (see tools/serve.py and deploy/*). */
export const PRODUCT_URL = (product) => product?.url || `/products/${product?.slug ?? product?.id}/`;

/* ============================================================================
   Normalisation — one place that maps the backend product contract
   (apps/products/serializers.py) onto the shape the UI renders.
   ========================================================================== */

const num = (value) => (value === null || value === undefined || value === '' ? null : Number(value));

export function normalizeVariation(variation) {
  if (!variation || typeof variation !== 'object') return variation;
  const available = variation.is_available !== false && variation.in_stock !== false;
  return {
    ...variation,
    label: variation.display_name || variation.label || variation.sku || '',
    price: variation.effective_price ?? variation.price ?? null,
    stock_status: available ? 'in_stock' : 'out_of_stock',
    options: variation.options && typeof variation.options === 'object' ? variation.options : {},
  };
}

export function normalizeProduct(raw) {
  if (!raw || typeof raw !== 'object' || raw._normalized) return raw;
  const regular = num(raw.regular_price);
  const effective = num(raw.effective_price ?? raw.sale_price ?? raw.regular_price ?? raw.price);
  const onSale = raw.on_sale ?? (regular !== null && effective !== null && regular > effective);
  const inStock = raw.stock?.in_stock ?? raw.in_stock;
  const gallery = Array.isArray(raw.images) && raw.images.length
    ? [...raw.images]
      .sort((x, y) => Number(!!y.is_main) - Number(!!x.is_main) || (x.sort_order ?? 0) - (y.sort_order ?? 0))
      .map((image) => ({ url: image.url, alt: image.alt_text || raw.name, width: image.width || 600, height: image.height || 600 }))
      .filter((image) => image.url)
    : (raw.main_image_url || raw.main_image ? [{ url: raw.main_image_url || raw.main_image, alt: raw.name, width: 600, height: 600 }] : []);
  const breadcrumb = Array.isArray(raw.breadcrumb) ? raw.breadcrumb : [];
  const variations = Array.isArray(raw.variations) ? raw.variations.map(normalizeVariation) : [];
  return {
    ...raw,
    _normalized: true,
    url: `/products/${raw.slug}/`,
    price: effective,
    compare_at_price: onSale ? regular : null,
    currency: raw.currency || 'NGN',
    images: gallery,
    rating_average: raw.rating_summary?.average ?? null,
    rating_count: raw.rating_summary?.count ?? 0,
    stock_status: inStock === true ? (raw.stock?.low_stock ? 'low_stock' : 'in_stock')
      : inStock === false ? 'out_of_stock' : null,
    has_variations: raw.has_variations ?? variations.length > 0,
    variations,
    category: (raw.category && typeof raw.category === 'object') ? raw.category : {
      id: raw.category ?? null,
      name: raw.category_name || '',
      slug: raw.category_slug || '',
      // Detail responses carry the full trail; the last crumb is the product itself.
      url: breadcrumb.length > 1 ? breadcrumb[breadcrumb.length - 2].url_path : null,
    },
    category_trail: breadcrumb.slice(0, -1).map((c) => ({ name: c.name, slug: c.slug, url: c.url_path })),
    weight: raw.weight_kg ? `${raw.weight_kg} kg` : null,
    seo: raw.seo || null,
  };
}

function normalizeProductList(data) {
  const list = normalizeList(data);
  return { ...list, results: list.results.map(normalizeProduct) };
}

/** UI sort keys → backend `ordering` values (ProductPublicViewSet.ordering_fields). */
export const SORT_OPTIONS = Object.freeze([
  { value: '', label: 'Newest first', ordering: '-created_at' },
  { value: 'price_asc', label: 'Price: low to high', ordering: 'price' },
  { value: 'price_desc', label: 'Price: high to low', ordering: '-price' },
  { value: 'name', label: 'Name: A to Z', ordering: 'name' },
  { value: 'rating', label: 'Top rated', ordering: '-avg_rating' },
]);

/* ============================================================================
   Reads
   ========================================================================== */

/**
 * GET /products/ — filters: category (slug), q, brand, min_price, max_price,
 * in_stock, featured, new_arrivals, best_sellers, ordering, page, page_size.
 */
export function listProducts(params = {}, { signal } = {}) {
  return api.publicGet('/products/', { params, signal }).then(normalizeProductList);
}

/** GET /products/search/?q= — relevance-ranked search. */
export function searchProducts(params = {}, { signal } = {}) {
  return api.publicGet('/products/search/', { params, signal }).then(normalizeProductList);
}

export function getProduct(slug, { signal } = {}) {
  return api.publicGet(`/products/${encodeURIComponent(slug)}/`, { signal }).then(normalizeProduct);
}

export function getRelatedProducts(slug, { signal, limit = 4 } = {}) {
  return api.publicGet(`/products/${encodeURIComponent(slug)}/related/`, { params: { limit }, signal })
    .then(normalizeProductList)
    .catch(() => ({ results: [], count: 0 }));
}

/** GET /reviews/product/<slug>/ — approved reviews (paginated) + rating summary. */
export function getProductReviews(slug, params = {}, { signal } = {}) {
  return api.publicGet(`/reviews/product/${encodeURIComponent(slug)}/`, { params, signal }).then((data) => {
    const list = normalizeList(data);
    return {
      ...list,
      summary: data?.summary || null,
      results: list.results.map((review) => ({
        ...review,
        display_name: review.customer_name || 'Customer',
        verified_purchase: !!review.is_verified_purchase,
      })),
    };
  });
}

/** POST /reviews/ — signed-in customers only; the review is moderated before it appears. */
export function submitReview(productId, { rating, title = '', body = '' }) {
  return api.post('/reviews/', { product: productId, rating: Number(rating), title, body });
}

/** GET /products/facets/ — brands (with counts) and price bounds for a scope. */
export function getFacets(params = {}, { signal } = {}) {
  return api.publicGet('/products/facets/', { params, signal }).then((data) => ({
    brands: Array.isArray(data?.brands) ? data.brands : [],
    price_range: { min: num(data?.price?.min), max: num(data?.price?.max) },
    count: data?.count ?? null,
  }));
}

export async function getBrands(params = {}, opts = {}) {
  const facets = await getFacets(params, opts);
  return { results: facets.brands, count: facets.brands.length };
}

/* ============================================================================
   Field readers — tolerant of reasonable backend naming, never inventive
   ========================================================================== */

export function productPrice(product) {
  const currency = product?.currency || 'NGN';
  const current = product?.price ?? product?.current_price ?? product?.sale_price ?? null;
  const original = product?.compare_at_price ?? product?.original_price ?? null;
  const hasCurrent = current !== null && current !== undefined && current !== '';
  const numericCurrent = hasCurrent ? Number(current) : null;
  const numericOriginal = original !== null && original !== undefined && original !== '' ? Number(original) : null;
  const onSale = numericOriginal !== null && numericCurrent !== null && numericOriginal > numericCurrent;
  return {
    currency,
    current: numericCurrent,
    original: numericOriginal,
    onSale,
    formatted: hasCurrent ? formatMoney(numericCurrent, currency) : null,
    formattedOriginal: onSale ? formatMoney(numericOriginal, currency) : null,
    discountPercent: onSale
      ? (product?.discount_percent ?? Math.round(((numericOriginal - numericCurrent) / numericOriginal) * 100))
      : null,
  };
}

/**
 * Stock presentation. `stock_status` from the API wins. We never infer
 * availability from a quantity the backend did not send.
 */
export function productStock(product) {
  const status = product?.stock_status
    || (product?.in_stock === true ? 'in_stock' : product?.in_stock === false ? 'out_of_stock' : null);
  const quantity = Number.isFinite(Number(product?.available_quantity)) ? Number(product.available_quantity) : null;
  switch (status) {
    case 'in_stock':
      return { status, label: 'In stock', className: 'stock-in', iconName: 'check-circle', purchasable: true, quantity };
    case 'low_stock':
      return {
        status,
        label: product?.low_stock_label || (quantity !== null ? `Only ${quantity} left` : 'Low stock'),
        className: 'stock-low', iconName: 'alert-triangle', purchasable: true, quantity,
      };
    case 'out_of_stock':
      return { status, label: 'Out of stock', className: 'stock-out', iconName: 'alert-circle', purchasable: false, quantity };
    case 'backorder':
      return { status, label: product?.backorder_label || 'Available on backorder', className: 'stock-low', iconName: 'clock', purchasable: true, quantity };
    case 'preorder':
      return { status, label: 'Pre-order', className: 'stock-low', iconName: 'clock', purchasable: true, quantity };
    default:
      return { status: null, label: null, className: '', iconName: null, purchasable: product?.purchasable !== false, quantity };
  }
}

export function productImage(product, index = 0) {
  const images = product?.images || product?.gallery || [];
  const candidate = Array.isArray(images) ? images[index] || images[0] : null;
  const url = candidate?.url || candidate?.image || (typeof candidate === 'string' ? candidate : null)
    || product?.image_url || product?.image || product?.thumbnail || null;
  if (!url) return null;
  return {
    url,
    alt: candidate?.alt || product?.image_alt || product?.name || 'Product image',
    width: candidate?.width || 600,
    height: candidate?.height || 600,
    srcset: candidate?.srcset || null,
  };
}

export function productRating(product) {
  const average = Number(product?.rating_average ?? product?.rating_summary?.average ?? NaN);
  const count = Number(product?.rating_count ?? product?.rating_summary?.count ?? NaN);
  if (!Number.isFinite(average) || !Number.isFinite(count) || count <= 0) return null;
  return { average, count };
}

export function brandName(product) {
  if (!product?.brand) return null;
  return typeof product.brand === 'string' ? product.brand : product.brand.name || null;
}

/* ============================================================================
   Renderers
   ========================================================================== */

export function renderStars(average) {
  const rounded = Math.round(average * 2) / 2;
  return `<span class="stars" aria-hidden="true">${
    Array.from({ length: 5 }, (_, i) => icon('star', { class: i + 1 <= rounded ? '' : 'icon--empty' })).join('')
  }</span>`;
}

/**
 * Product card. `lazy` should be false for above-the-fold cards on listing
 * pages so the LCP image is not deferred.
 */
export function renderProductCard(product, { lazy = true, showWishlist = true, eager = false } = {}) {
  const price = productPrice(product);
  const stock = productStock(product);
  const image = productImage(product);
  const rating = productRating(product);
  const url = PRODUCT_URL(product);
  const name = product?.name || 'Product';
  const category = product?.category;
  const categoryName = typeof category === 'string' ? category : (category?.name || product?.category_name);
  const hasVariations = !!(product?.has_variations || product?.variations?.length);
  const canBuyDirectly = stock.purchasable && !hasVariations;

  const flags = [];
  if (price.onSale && price.discountPercent) flags.push(`<span class="badge badge--danger">−${esc(price.discountPercent)}%</span>`);
  if (product?.is_featured) flags.push('<span class="badge badge--primary">Featured</span>');

  return `<article class="product-card" data-product-card data-product-id="${esc(product.id)}" data-product-slug="${esc(product.slug || '')}">
    <a class="product-card__media" href="${esc(url)}" tabindex="-1" aria-hidden="true">
      ${image
        ? `<img src="${esc(image.url)}" alt="${esc(image.alt)}" width="${esc(image.width)}" height="${esc(image.height)}"
             ${image.srcset ? `srcset="${esc(image.srcset)}" sizes="(max-width:600px) 50vw, (max-width:1024px) 33vw, 25vw"` : ''}
             loading="${eager ? 'eager' : lazy ? 'lazy' : 'eager'}" decoding="async" ${eager ? 'fetchpriority="high"' : ''}>`
        : `<span class="product-card__noimage" aria-hidden="true">${icon('image', { size: 'xl' })}</span>`}
    </a>
    ${flags.length ? `<span class="product-card__flags">${flags.join('')}</span>` : ''}
    ${showWishlist ? `<button type="button" class="product-card__wish" data-wishlist-toggle data-product-id="${esc(product.id)}"
        aria-pressed="false" aria-label="Save ${esc(name)} to wishlist">${icon('heart', { size: 'sm' })}</button>` : ''}
    <div class="product-card__body">
      ${categoryName ? `<span class="product-card__cat">${esc(categoryName)}</span>` : ''}
      <h3 class="product-card__name t-clamp-2"><a href="${esc(url)}">${esc(name)}</a></h3>
      ${rating ? `<span class="product-card__rating">${renderStars(rating.average)}<span>${rating.average.toFixed(1)}</span><span class="t-meta">(${formatNumber(rating.count)})</span></span>` : ''}
      <span class="price-row">
        ${price.formatted
          ? `<span class="price">${esc(price.formatted)}</span>${price.formattedOriginal ? `<span class="price price--original">${esc(price.formattedOriginal)}</span>` : ''}`
          : '<span class="t-meta">Price unavailable</span>'}
      </span>
      ${stock.label ? `<span class="product-card__stock ${stock.className}">${icon(stock.iconName, { size: 'sm' })}${esc(stock.label)}</span>` : ''}
    </div>
    <div class="product-card__actions">
      ${canBuyDirectly
        ? `<button type="button" class="btn btn--primary" data-add-to-cart data-product-id="${esc(product.id)}" data-quantity="1">
             ${icon('cart', { size: 'sm' })}Add to cart</button>`
        : `<a class="btn btn--primary" href="${esc(url)}">${hasVariations ? 'Choose options' : 'View product'}</a>`}
      <button type="button" class="btn btn--secondary" data-buy-now data-product-id="${esc(product.id)}"
        ${hasVariations ? `data-requires-variation="true"` : ''} ${!stock.purchasable ? 'disabled aria-disabled="true"' : ''}>Buy now</button>
    </div>
  </article>`;
}

export function renderProductGrid(products, opts = {}) {
  return products.map((product, index) => renderProductCard(product, { ...opts, eager: opts.eagerFirst && index === 0 })).join('');
}

/** Compact horizontal product row, used in carts, order summaries, related. */
export function renderProductLine({ product, variation, quantity, unitPrice, lineTotal, currency = 'NGN' }) {
  const image = productImage(product);
  const name = product?.name || 'Product';
  return `<div class="order-line">
    <span class="order-line__media">
      ${image ? `<img src="${esc(image.url)}" alt="${esc(image.alt)}" width="72" height="72" loading="lazy" decoding="async">`
              : `<span class="order-line__noimage" aria-hidden="true">${icon('image')}</span>`}
    </span>
    <div class="order-line__body">
      <a class="order-line__name" href="${esc(PRODUCT_URL(product))}">${esc(name)}</a>
      ${variation ? `<span class="t-meta">${esc(variationLabel(variation))}</span>` : ''}
      <span class="t-meta">Qty ${esc(quantity)}${unitPrice != null ? ` · ${esc(formatMoney(unitPrice, currency))} each</span>` : ''}
    </div>
    <span class="order-line__total price">${lineTotal != null ? esc(formatMoney(lineTotal, currency)) : '—'}</span>
  </div>`;
}

export function variationLabel(variation) {
  if (!variation) return '';
  if (typeof variation === 'string') return variation;
  if (variation.label) return variation.label;
  if (variation.name) return variation.name;
  const options = variation.options || variation.attributes || variation.option_values;
  if (Array.isArray(options)) return options.map((o) => (typeof o === 'string' ? o : `${o.name || o.type}: ${o.value}`)).join(' · ');
  if (options && typeof options === 'object') return Object.entries(options).map(([k, v]) => `${k}: ${v}`).join(' · ');
  return variation.sku || '';
}

/** Product JSON-LD. Only emits Offer when the backend supplied a real price. */
export function productJsonLd(product, origin) {
  const price = productPrice(product);
  const stock = productStock(product);
  const rating = productRating(product);
  const images = (product?.images || []).map((i) => i.url || i).filter(Boolean);
  const data = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    url: `${origin}${PRODUCT_URL(product)}`,
    ...(product.description ? { description: String(product.description).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 5000) } : {}),
    ...(images.length ? { image: images } : {}),
    ...(product.sku ? { sku: product.sku } : {}),
    ...(brandName(product) ? { brand: { '@type': 'Brand', name: brandName(product) } } : {}),
  };
  if (price.current !== null) {
    data.offers = {
      '@type': 'Offer',
      url: `${origin}${PRODUCT_URL(product)}`,
      price: price.current,
      priceCurrency: price.currency,
      availability: stock.status === 'out_of_stock'
        ? 'https://schema.org/OutOfStock'
        : stock.status === 'preorder'
          ? 'https://schema.org/PreOrder'
          : stock.status === 'backorder'
            ? 'https://schema.org/BackOrder'
            : 'https://schema.org/InStock',
      itemCondition: 'https://schema.org/NewCondition',
    };
  }
  // AggregateRating only when genuine approved reviews exist.
  if (rating) {
    data.aggregateRating = {
      '@type': 'AggregateRating',
      ratingValue: rating.average,
      reviewCount: rating.count,
      bestRating: 5,
      worstRating: 1,
    };
  }
  return data;
}

export { categoryUrl };
export default { listProducts, searchProducts, getProduct, renderProductCard, renderProductGrid, normalizeProduct };
