/**
 * product.js — product detail page.
 *
 * Resolves the product from the SEO path (/products/<slug>/) or ?slug=,
 * renders the gallery, variations, quantity control, purchase actions, tabs,
 * reviews, related and recently-viewed products.
 *
 * Quantity limits and variation availability come from the backend. The final
 * validation always happens server-side when the line is added to the cart.
 */

import boot from '../boot.js';
import api, { normalizeList } from '../api.js';
import {
  getProduct, getRelatedProducts, getProductReviews, submitReview,
  productPrice, productStock, productImage, productRating, brandName,
  renderProductGrid, renderStars, productJsonLd, PRODUCT_URL, variationLabel,
} from '../products.js';
import { getCategories, categoryUrl, categoryTrail, renderCategoryBreadcrumbs, breadcrumbJsonLd } from '../categories.js';
import { addItem, startBuyNow } from '../cart.js';
import { isAuthenticated, getUser } from '../auth.js';
import { getSettings } from '../site.js';
import {
  skeletons, resolveRegion, renderRegionError, emptyState, toast, announce,
  openDialog, confirmDialog, withSubmit, formData, applyFormErrors,
} from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, $$, formatMoney, formatNumber, formatDate, sanitizeHtml, truncate, stripTags, createStorage } from '../utils.js';
import { toggleWishlist, isWishlisted, primeWishlist } from '../wishlist.js';
import { syncWishlistButtons } from '../shop-actions.js';

await boot();

const origin = (window.STARMOND_CONFIG?.SITE_URL || location.origin).replace(/\/$/, '');
const localStore = createStorage('local');
const RECENT_KEY = 'recently_viewed';

let product = null;
let selectedVariation = null;
let selectedOptions = {};
let quantity = 1;

/* ============================================================================
   Slug resolution
   ========================================================================== */

function slugFromLocation() {
  const match = location.pathname.match(/^\/products\/([^/]+)\/?$/);
  if (match) return decodeURIComponent(match[1]);
  return new URLSearchParams(location.search).get('slug') || '';
}

/* ============================================================================
   Load
   ========================================================================== */

async function load() {
  const slug = slugFromLocation();
  const region = $('[data-product-region]');
  if (!slug) {
    resolveRegion(region, emptyState({
      title: 'Product not specified', text: 'Open a product from the shop to see its details.',
      iconName: 'package', actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse the shop</a>',
    }));
    return;
  }
  region.setAttribute('aria-busy', 'true');
  region.innerHTML = skeletons.productDetail();
  try {
    product = await getProduct(slug);
    renderProduct();
    rememberRecent(product);
    loadRelated();
    loadReviews();
    loadRecentlyViewed();
  } catch (error) {
    if (error.isNotFound) {
      document.title = 'Product not found — Starmond Technology Limited';
      document.querySelector('meta[name="robots"]')?.setAttribute('content', 'noindex, follow');
      resolveRegion(region, emptyState({
        title: 'This product is no longer available',
        text: 'It may have been removed or renamed. Browse the catalogue to find something similar.',
        iconName: 'package',
        actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse the shop</a>',
      }));
      return;
    }
    renderRegionError(region, error, load, { title: 'This product could not be loaded' });
  }
}

/* ============================================================================
   Render
   ========================================================================== */

function renderProduct() {
  const region = $('[data-product-region]');
  const price = productPrice(product);
  const stock = productStock(product);
  const rating = productRating(product);
  const images = (product.images?.length ? product.images : [productImage(product)].filter(Boolean)) || [];
  const brand = brandName(product);

  updateMeta();
  renderBreadcrumbs();

  const html = `<div class="pdp">
    <div class="pdp__gallery">
      <div class="pdp__main" data-gallery-main>
        ${images.length
          ? `<img src="${esc(images[0].url || images[0])}" alt="${esc(images[0].alt || product.name)}" width="800" height="800" fetchpriority="high" decoding="async" data-gallery-image>`
          : `<span class="product-card__noimage">${icon('image', { size: 'xl' })}</span>`}
        ${images.length ? `<button type="button" class="pdp__zoom" data-gallery-zoom aria-label="View larger image">${icon('search', { size: 'sm' })}</button>` : ''}
      </div>
      ${images.length > 1 ? `<div class="pdp__thumbs" role="list" aria-label="Product images">
        ${images.map((image, index) => `<button type="button" class="pdp__thumb" role="listitem" data-gallery-thumb="${index}"
            aria-current="${index === 0}" aria-label="View image ${index + 1} of ${images.length}: ${esc(image.alt || product.name)}">
            <img src="${esc(image.url || image)}" alt="" width="120" height="120" loading="lazy" decoding="async">
          </button>`).join('')}
      </div>` : ''}
    </div>

    <div class="pdp__info">
      <div class="pdp__head">
        ${brand ? `<span class="pdp__brand">${esc(brand)}</span>` : ''}
        <h1 class="pdp__title">${esc(product.name)}</h1>
        <div class="pdp__meta">
          ${product.sku ? `<span>SKU: <strong data-variant-sku>${esc(product.sku)}</strong></span>` : ''}
          ${rating ? `<span class="cluster cluster--sm">${renderStars(rating.average)}<span>${rating.average.toFixed(1)} (${formatNumber(rating.count)} review${rating.count === 1 ? '' : 's'})</span></span>` : ''}
        </div>
      </div>

      <div class="pdp__price-block">
        <div class="price-row">
          ${price.formatted
            ? `<span class="price pdp__price ${price.onSale ? 'price--sale' : ''}" data-variant-price>${esc(price.formatted)}</span>
               ${price.formattedOriginal ? `<span class="price price--original" data-variant-compare>${esc(price.formattedOriginal)}</span>` : ''}
               ${price.discountPercent ? `<span class="badge badge--danger">Save ${esc(price.discountPercent)}%</span>` : ''}`
            : '<span class="t-muted">Price unavailable — please contact us</span>'}
        </div>
        ${stock.label ? `<span class="product-card__stock ${stock.className}" data-variant-stock>${icon(stock.iconName, { size: 'sm' })}${esc(stock.label)}</span>` : ''}
        <p class="t-xs t-muted">All prices are in Nigerian Naira (NGN) and include applicable taxes as configured by the store.</p>
      </div>

      ${product.short_description ? `<p class="pdp__short">${esc(product.short_description)}</p>` : ''}

      <div data-variant-groups></div>

      <div class="pdp__buy">
        <div class="pdp__qty-row">
          <div class="field" style="gap:var(--space-2)">
            <label class="field__label" for="pdp-quantity">Quantity</label>
            <div class="qty">
              <button type="button" class="qty__btn" data-qty-decrease aria-label="Decrease quantity">${icon('minus', { size: 'sm' })}</button>
              <input class="qty__input" id="pdp-quantity" type="number" min="1" value="1" inputmode="numeric" data-qty-input aria-describedby="qty-feedback">
              <button type="button" class="qty__btn" data-qty-increase aria-label="Increase quantity">${icon('plus', { size: 'sm' })}</button>
            </div>
          </div>
          <p class="t-xs t-muted" id="qty-feedback" data-qty-feedback role="status"></p>
        </div>
        <p class="field__error" data-selection-error role="alert"></p>
        <div class="pdp__actions">
          <button type="button" class="btn btn--primary btn--lg" data-pdp-add ${!stock.purchasable ? 'disabled aria-disabled="true"' : ''}>
            ${icon('cart', { size: 'sm' })} Add to cart
          </button>
          <button type="button" class="btn btn--secondary btn--lg" data-pdp-buy ${!stock.purchasable ? 'disabled aria-disabled="true"' : ''}>
            Buy now
          </button>
        </div>
        <button type="button" class="btn btn--ghost btn--sm pdp__wishlist" data-wishlist-toggle data-product-id="${esc(product.id)}" aria-pressed="false">
          ${icon('heart', { size: 'sm' })} Save to wishlist
        </button>
      </div>

      <div class="pdp__assurances" data-pdp-assurances>
        <div class="pdp__assurance">${icon('truck')}<span><span class="pdp__assurance-title">Delivery</span><span class="pdp__assurance-text" data-delivery-note>Delivery options and fees are calculated at checkout based on your address.</span></span></div>
        <div class="pdp__assurance">${icon('undo')}<span><span class="pdp__assurance-title">Returns</span><span class="pdp__assurance-text" data-returns-note>See our returns and refund policy for eligibility and timelines.</span></span></div>
        <div class="pdp__assurance">${icon('shield')}<span><span class="pdp__assurance-title">Secure payment</span><span class="pdp__assurance-text">Payments are processed by Paystack. Your card details never reach this store.</span></span></div>
      </div>
    </div>
  </div>`;

  resolveRegion(region, html);
  renderVariations();
  initGallery(images);
  initQuantity();
  // Apply the backend stock ceiling to the quantity input on first paint.
  // Previously max was only written after a variation change, so a simple
  // product shipped an unbounded number input.
  resolveVariation();
  initPurchaseActions();
  renderTabs();
  syncWishlistButtons();

  if (new URLSearchParams(location.search).get('select') === '1') {
    $('[data-variant-groups]')?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

function updateMeta() {
  const seo = product.seo || {};
  const description = seo.description || truncate(stripTags(product.short_description || product.description || ''), 158);
  document.title = seo.title || `${product.name} — Starmond Technology Limited`;
  setMeta('description', description || `Buy ${product.name} from Starmond Technology Limited.`);
  setCanonical(`${origin}${seo.canonical || PRODUCT_URL(product)}`);
  const image = productImage(product);
  if (image) {
    setProperty('og:image', image.url);
    setProperty('og:type', 'product');
    document.querySelector('meta[name="twitter:card"]')?.setAttribute('content', 'summary_large_image');
    setMeta('twitter:image', image.url);
  }
  setProperty('og:title', seo.title || product.name);
  setProperty('og:description', description);
  setProperty('og:url', `${origin}${PRODUCT_URL(product)}`);

  document.querySelectorAll('script[data-product-jsonld]').forEach((n) => n.remove());
  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.dataset.productJsonld = 'true';
  script.textContent = JSON.stringify(productJsonLd(product, origin));
  document.head.appendChild(script);
}

function renderBreadcrumbs() {
  const holder = $('[data-product-breadcrumbs]');
  const category = typeof product.category === 'object' ? product.category : null;
  const items = [{ name: 'Home', url: '/' }, { name: 'Shop', url: '/shop.html' }];
  if (category) {
    const trail = categoryTrail(category);
    trail.forEach((c) => items.push({ name: c.name, url: categoryUrl(c) }));
    holder.innerHTML = renderCategoryBreadcrumbs(trail, product.name);
  } else {
    holder.innerHTML = `<nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list">
      <li class="breadcrumbs__item"><a href="/">Home</a></li>
      <li class="breadcrumbs__item"><a href="/shop.html">Shop</a></li>
      <li class="breadcrumbs__item"><span aria-current="page">${esc(product.name)}</span></li>
    </ol></nav>`;
  }
  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.dataset.productJsonld = 'true';
  script.textContent = JSON.stringify(breadcrumbJsonLd([...items, { name: product.name, url: PRODUCT_URL(product) }], origin));
  document.head.appendChild(script);
}

/* ============================================================================
   Variations
   ========================================================================== */

function variationOptions() {
  // Two accepted shapes: option_types + variations, or a flat variation list.
  if (Array.isArray(product.option_types) && product.option_types.length) {
    return product.option_types.map((type) => ({
      key: type.slug || type.name,
      name: type.name,
      type: type.type || 'text',
      values: type.values || [],
    }));
  }
  const variations = product.variations || [];
  const map = new Map();
  variations.forEach((variation) => {
    const options = variation.options || variation.attributes || {};
    const entries = Array.isArray(options)
      ? options.map((o) => [o.name || o.type, o.value])
      : Object.entries(options);
    entries.forEach(([name, value]) => {
      if (!map.has(name)) map.set(name, new Set());
      map.get(name).add(String(value));
    });
  });
  return [...map.entries()].map(([name, values]) => ({
    key: name, name, type: /colou?r/i.test(name) ? 'color' : 'text', values: [...values],
  }));
}

function renderVariations() {
  const holder = $('[data-variant-groups]');
  const groups = variationOptions();
  if (!groups.length) { holder.innerHTML = ''; return; }

  holder.innerHTML = `<div class="stack stack--lg">${groups.map((group) => `
    <fieldset class="variant-group">
      <legend class="variant-group__label">${esc(group.name)} <span data-selected-label="${esc(group.key)}"></span></legend>
      <div class="variant-options" role="group" aria-label="${esc(group.name)}">
        ${group.values.map((value) => {
          const val = typeof value === 'object' ? (value.value ?? value.label) : value;
          const label = typeof value === 'object' ? (value.label ?? value.value) : value;
          const hex = typeof value === 'object' ? value.hex : null;
          const available = isOptionAvailable(group.key, String(val));
          return `<button type="button" class="variant-option ${group.type === 'color' && hex ? 'variant-option--swatch' : ''}"
            data-option-key="${esc(group.key)}" data-option-value="${esc(val)}"
            aria-pressed="false" ${!available ? 'disabled aria-disabled="true"' : ''}
            aria-label="${esc(group.name)}: ${esc(label)}${!available ? ' (unavailable)' : ''}">
            ${group.type === 'color' && hex ? `<span style="background:${esc(hex)}"></span>` : esc(label)}
          </button>`;
        }).join('')}
      </div>
    </fieldset>`).join('')}</div>`;

  holder.addEventListener('click', (event) => {
    const button = event.target.closest('[data-option-key]');
    if (!button || button.disabled) return;
    const { optionKey, optionValue } = button.dataset;
    if (selectedOptions[optionKey] === optionValue) delete selectedOptions[optionKey];
    else selectedOptions[optionKey] = optionValue;
    holder.querySelectorAll(`[data-option-key="${CSS.escape(optionKey)}"]`).forEach((node) => {
      node.setAttribute('aria-pressed', String(node.dataset.optionValue === selectedOptions[optionKey]));
    });
    const label = holder.querySelector(`[data-selected-label="${CSS.escape(optionKey)}"]`);
    if (label) label.textContent = selectedOptions[optionKey] ? `— ${selectedOptions[optionKey]}` : '';
    resolveVariation();
  });
}

function isOptionAvailable(key, value) {
  const variations = product.variations || [];
  if (!variations.length) return true;
  return variations.some((variation) => {
    const options = normalizeOptions(variation);
    if (String(options[key]) !== String(value)) return false;
    return Object.entries(selectedOptions).every(([k, v]) => k === key || String(options[k]) === String(v));
  });
}

function normalizeOptions(variation) {
  const options = variation.options || variation.attributes || variation.option_values || {};
  if (Array.isArray(options)) return Object.fromEntries(options.map((o) => [o.name || o.type, o.value]));
  return options;
}

function resolveVariation() {
  const groups = variationOptions();
  const errorNode = $('[data-selection-error]');
  const complete = groups.every((group) => selectedOptions[group.key]);
  selectedVariation = null;

  if (complete && product.variations?.length) {
    selectedVariation = product.variations.find((variation) => {
      const options = normalizeOptions(variation);
      return groups.every((group) => String(options[group.key]) === String(selectedOptions[group.key]));
    }) || null;
  }

  if (errorNode) errorNode.textContent = '';

  const source = selectedVariation || product;
  const price = productPrice(source);
  const stock = productStock(source);

  const priceNode = $('[data-variant-price]');
  if (priceNode && price.formatted) {
    priceNode.textContent = price.formatted;
    priceNode.classList.toggle('price--sale', price.onSale);
  }
  const compareNode = $('[data-variant-compare]');
  if (compareNode) compareNode.textContent = price.formattedOriginal || '';
  const skuNode = $('[data-variant-sku]');
  if (skuNode && source.sku) skuNode.textContent = source.sku;
  const stockNode = $('[data-variant-stock]');
  if (stockNode && stock.label) {
    stockNode.className = `product-card__stock ${stock.className}`;
    stockNode.innerHTML = `${icon(stock.iconName, { size: 'sm' })}${esc(stock.label)}`;
  }

  const max = maxQuantity();
  const input = $('[data-qty-input]');
  if (input) {
    if (max) input.max = String(max);
    if (quantity > (max || Infinity)) { quantity = max; input.value = String(max); }
  }
  updateQuantityFeedback();

  const disabled = !stock.purchasable || (groups.length > 0 && !selectedVariation);
  $('[data-pdp-add]')?.toggleAttribute('disabled', disabled);
  $('[data-pdp-buy]')?.toggleAttribute('disabled', disabled);

  if (selectedVariation) announce(`${variationLabel(selectedVariation)} selected. ${price.formatted || ''} ${stock.label || ''}`);
}

function maxQuantity() {
  const source = selectedVariation || product;
  const candidates = [
    source?.available_quantity,
    source?.max_quantity_per_order,
    product?.max_quantity_per_order,
  ].map(Number).filter((n) => Number.isFinite(n) && n > 0);
  return candidates.length ? Math.min(...candidates) : null;
}

/* ============================================================================
   Gallery / quantity / purchase
   ========================================================================== */

function initGallery(images) {
  if (!images.length) return;
  const main = $('[data-gallery-image]');
  $$('[data-gallery-thumb]').forEach((thumb) => {
    thumb.addEventListener('click', () => {
      const index = Number(thumb.dataset.galleryThumb);
      const image = images[index];
      main.src = image.url || image;
      main.alt = image.alt || product.name;
      $$('[data-gallery-thumb]').forEach((node) => node.setAttribute('aria-current', String(node === thumb)));
    });
  });
  $('[data-gallery-zoom]')?.addEventListener('click', () => {
    const current = main?.src;
    openDialog({
      title: product.name,
      size: 'wide',
      body: `<img src="${esc(current)}" alt="${esc(main?.alt || product.name)}" style="width:100%;height:auto;border-radius:var(--radius-md)">`,
    });
  });
}

function updateQuantityFeedback() {
  const feedback = $('[data-qty-feedback]');
  if (!feedback) return;
  const max = maxQuantity();
  const stock = productStock(selectedVariation || product);
  if (stock.status === 'out_of_stock') feedback.textContent = 'This item is currently out of stock.';
  else if (max) feedback.textContent = `Up to ${max} available for this selection.`;
  else feedback.textContent = '';
}

function initQuantity() {
  const input = $('[data-qty-input]');
  if (!input) return;
  const setQuantity = (next) => {
    const max = maxQuantity();
    let value = Math.max(1, Math.floor(Number(next) || 1));
    if (max && value > max) {
      value = max;
      toast(`Only ${max} available for this selection.`, { type: 'warning' });
    }
    quantity = value;
    input.value = String(value);
    $('[data-qty-decrease]').disabled = value <= 1;
    $('[data-qty-increase]').disabled = !!max && value >= max;
    updateQuantityFeedback();
  };
  $('[data-qty-decrease]').addEventListener('click', () => setQuantity(quantity - 1));
  $('[data-qty-increase]').addEventListener('click', () => setQuantity(quantity + 1));
  input.addEventListener('change', () => setQuantity(input.value));
  input.addEventListener('input', () => { quantity = Math.max(1, Math.floor(Number(input.value) || 1)); });
  setQuantity(1);
}

function requireSelection() {
  const groups = variationOptions();
  if (!groups.length) return true;
  const missing = groups.filter((group) => !selectedOptions[group.key]);
  if (missing.length) {
    const node = $('[data-selection-error]');
    node.textContent = `Please choose ${missing.map((g) => g.name.toLowerCase()).join(' and ')}.`;
    $('[data-variant-groups]')?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    announce(node.textContent, { assertive: true });
    return false;
  }
  if (!selectedVariation) {
    $('[data-selection-error]').textContent = 'That combination is not available. Please choose a different option.';
    return false;
  }
  return true;
}

function initPurchaseActions() {
  const addButton = $('[data-pdp-add]');
  const buyButton = $('[data-pdp-buy]');

  addButton?.addEventListener('click', async () => {
    if (!requireSelection()) return;
    const original = addButton.innerHTML;
    addButton.disabled = true;
    addButton.innerHTML = '<span class="btn__pending">Adding</span>';
    try {
      await addItem({ product: product.id, variation: selectedVariation?.id ?? null, quantity });
      toast(`${product.name} added to your cart.`, {
        type: 'success', title: 'Added to cart', action: { label: 'View cart', href: '/cart.html' },
      });
    } catch (error) {
      const message = error?.fieldErrors?.quantity?.[0] || error?.userMessage || 'Could not add this product.';
      $('[data-selection-error]').textContent = message;
      toast(message, { type: 'danger', title: 'Not added' });
    } finally {
      addButton.disabled = false;
      addButton.innerHTML = original;
      hydrateIcons(addButton);
    }
  });

  buyButton?.addEventListener('click', () => {
    if (!requireSelection()) return;
    // Isolated direct checkout — the existing cart is untouched.
    startBuyNow({ product: product.id, variation: selectedVariation?.id ?? null, quantity });
  });
}

/* ============================================================================
   Tabs
   ========================================================================== */

function renderTabs() {
  const section = $('[data-product-tabs]');
  section.hidden = false;

  const descHolder = $('[data-product-description]');
  descHolder.innerHTML = product.description
    ? sanitizeHtml(product.description)
    : '<p class="t-muted">No detailed description has been published for this product yet.</p>';

  const specs = product.specifications || product.attributes || [];
  const specsHolder = $('[data-product-specs]');
  const entries = Array.isArray(specs)
    ? specs.map((s) => [s.name || s.label || s.key, s.value])
    : Object.entries(specs);
  const extra = [
    product.sku ? ['SKU', product.sku] : null,
    brandName(product) ? ['Brand', brandName(product)] : null,
    product.weight ? ['Weight', product.weight] : null,
    product.warranty ? ['Warranty', product.warranty] : null,
  ].filter(Boolean);
  const allSpecs = [...extra, ...entries].filter(([, value]) => value !== null && value !== undefined && value !== '');
  specsHolder.innerHTML = allSpecs.length
    ? `<table class="spec-table"><caption class="sr-only">Product specifications</caption><tbody>${
        allSpecs.map(([name, value]) => `<tr><th scope="row">${esc(name)}</th><td>${esc(value)}</td></tr>`).join('')
      }</tbody></table>`
    : emptyState({ title: 'No specifications published', text: 'Technical details for this product have not been added yet.', iconName: 'clipboard', inline: true });

  const deliveryHolder = $('[data-product-delivery]');
  getSettings().then((settings) => {
    const shipping = settings?.policies?.shipping?.summary;
    const returns = settings?.policies?.returns?.summary;
    deliveryHolder.innerHTML = `
      <h3>Delivery</h3>
      <p>${esc(shipping || 'Delivery options, coverage and fees are shown at checkout once you enter your address. The fee is calculated by the store before payment.')}</p>
      <h3>Returns</h3>
      <p>${esc(returns || 'Return eligibility and timelines are described in our returns and refund policy.')}</p>
      <p><a href="/policies/shipping.html">Read the shipping policy</a> · <a href="/policies/returns.html">Read the returns policy</a></p>`;
    if (shipping) $('[data-delivery-note]').textContent = truncate(shipping, 120);
    if (returns) $('[data-returns-note]').textContent = truncate(returns, 120);
  });

  // Accessible tab pattern with arrow-key navigation.
  const tabs = $$('.tabs__btn');
  const activate = (tab) => {
    tabs.forEach((node) => {
      const selected = node === tab;
      node.setAttribute('aria-selected', String(selected));
      node.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(node.getAttribute('aria-controls'));
      if (panel) panel.hidden = !selected;
    });
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', (event) => {
      const keys = { ArrowRight: 1, ArrowLeft: -1, Home: -index, End: tabs.length - 1 - index };
      if (!(event.key in keys)) return;
      event.preventDefault();
      const next = tabs[(index + keys[event.key] + tabs.length) % tabs.length];
      activate(next);
      next.focus();
    });
  });
}

/* ============================================================================
   Reviews
   ========================================================================== */

async function loadReviews() {
  const holder = $('[data-product-reviews]');
  holder.innerHTML = skeletons.review(2);
  try {
    const list = await getProductReviews(product.slug, { approved: 1, page_size: 10 });
    const rating = productRating(product);
    const reviews = list.results;

    holder.innerHTML = `
      <div class="stack stack--lg">
        <div class="cluster cluster--between">
          ${rating ? `<div class="rating-summary">
            <span class="rating-summary__value">${rating.average.toFixed(1)}</span>
            <span class="stack stack--xs">${renderStars(rating.average)}<span class="t-meta">${formatNumber(rating.count)} approved review${rating.count === 1 ? '' : 's'}</span></span>
          </div>` : '<p class="t-sm t-muted">No approved reviews yet.</p>'}
          <button type="button" class="btn btn--secondary btn--sm" data-write-review>${icon('edit', { size: 'sm' })} Write a review</button>
        </div>
        <div data-review-list>
          ${reviews.length ? reviews.map(renderReview).join('') : emptyState({
            title: 'No reviews yet', text: 'Be the first to share your experience with this product.', iconName: 'star', inline: true,
          })}
        </div>
      </div>`;
    hydrateIcons(holder);
    holder.querySelector('[data-write-review]')?.addEventListener('click', openReviewDialog);
  } catch (error) {
    renderRegionError(holder, error, loadReviews, { title: 'Reviews could not be loaded' });
  }
}

function renderReview(review) {
  const name = review.display_name || review.customer_name || 'Customer';
  return `<article class="review">
    <div class="review__head">
      <span class="review__author">
        <span class="review__avatar" aria-hidden="true">${esc(name.slice(0, 2).toUpperCase())}</span>
        ${esc(name)}
        ${review.verified_purchase ? '<span class="badge badge--success badge--dot">Verified purchase</span>' : ''}
      </span>
      <span class="t-meta">${esc(formatDate(review.created_at))}</span>
    </div>
    ${typeof review.rating === 'number' ? renderStars(review.rating) : ''}
    ${review.title ? `<h3 class="review__title">${esc(review.title)}</h3>` : ''}
    <p class="review__body">${esc(review.body || review.comment || '')}</p>
  </article>`;
}

async function openReviewDialog() {
  if (!isAuthenticated()) {
    const proceed = await confirmDialog({
      title: 'Sign in to review', message: 'Reviews are linked to your account so we can verify purchases.', confirmLabel: 'Sign in',
    });
    if (proceed) window.location.assign(`/login.html?next=${encodeURIComponent(location.pathname)}`);
    return;
  }
  openDialog({
    title: 'Write a review',
    sub: product.name,
    body: `<form class="stack" id="review-form" novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="field">
        <label class="field__label" for="rv-rating">Overall rating <span class="field__req">*</span></label>
        <select class="select" id="rv-rating" name="rating" required>
          <option value="">Choose a rating</option>
          <option value="5">5 — Excellent</option><option value="4">4 — Good</option>
          <option value="3">3 — Average</option><option value="2">2 — Poor</option><option value="1">1 — Very poor</option>
        </select>
        <p class="field__error" data-error-for="rating"></p>
      </div>
      <div class="field">
        <label class="field__label" for="rv-title">Review title</label>
        <input class="input" id="rv-title" name="title" maxlength="120">
        <p class="field__error" data-error-for="title"></p>
      </div>
      <div class="field">
        <label class="field__label" for="rv-body">Your review <span class="field__req">*</span></label>
        <textarea class="textarea" id="rv-body" name="body" rows="5" required maxlength="2000"></textarea>
        <p class="field__hint">Reviews are published after moderation.</p>
        <p class="field__error" data-error-for="body"></p>
      </div>
    </form>`,
    footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-submit-review data-pending-label="Submitting">Submit review</button>',
    onMount({ element, close }) {
      const form = element.querySelector('#review-form');
      element.querySelector('[data-submit-review]').addEventListener('click', async (event) => {
        const button = event.currentTarget;
        try {
          await withSubmit(form, button, () => submitReview(product.slug, { ...formData(form), rating: Number(formData(form).rating) }));
          close();
          toast('Thank you. Your review will appear once it has been approved.', { type: 'success' });
        } catch { /* errors rendered on the form */ }
      });
    },
  });
}

/* ============================================================================
   Related + recently viewed
   ========================================================================== */

async function loadRelated() {
  const section = $('[data-related-section]');
  const region = $('[data-related-products]');
  region.innerHTML = skeletons.productGrid(4);
  try {
    const list = await getRelatedProducts(product.slug, { limit: 4 });
    if (!list.results.length) { section.hidden = true; return; }
    section.hidden = false;
    resolveRegion(region, `<div class="product-grid">${renderProductGrid(list.results.slice(0, 4))}</div>`);
    syncWishlistButtons();
  } catch { section.hidden = true; }
}

function rememberRecent(item) {
  const list = localStore.get(RECENT_KEY, []).filter((entry) => entry.slug !== item.slug);
  list.unshift({
    slug: item.slug, name: item.name, id: item.id,
    image: productImage(item)?.url || null,
    price: productPrice(item).current, currency: productPrice(item).currency,
  });
  localStore.set(RECENT_KEY, list.slice(0, 8));
}

function loadRecentlyViewed() {
  const section = $('[data-recent-section]');
  const region = $('[data-recent-products]');
  const list = localStore.get(RECENT_KEY, []).filter((entry) => entry.slug !== product.slug).slice(0, 4);
  if (!list.length) { section.hidden = true; return; }
  section.hidden = false;
  region.innerHTML = `<div class="product-grid">${list.map((entry) => `
    <article class="product-card">
      <a class="product-card__media" href="/products/${esc(entry.slug)}/" tabindex="-1" aria-hidden="true">
        ${entry.image ? `<img src="${esc(entry.image)}" alt="" width="300" height="300" loading="lazy" decoding="async">` : `<span class="product-card__noimage">${icon('image')}</span>`}
      </a>
      <div class="product-card__body">
        <h3 class="product-card__name t-clamp-2"><a href="/products/${esc(entry.slug)}/">${esc(entry.name)}</a></h3>
        <span class="price">${entry.price != null ? esc(formatMoney(entry.price, entry.currency || 'NGN')) : '—'}</span>
      </div>
    </article>`).join('')}</div>`;
  hydrateIcons(region);
}

/* ---------------------------------------------------------------- helpers -- */

function setMeta(name, content) {
  let tag = document.querySelector(`meta[name="${name}"]`);
  if (!tag) { tag = document.createElement('meta'); tag.name = name; document.head.appendChild(tag); }
  tag.content = content;
}
function setProperty(property, content) {
  let tag = document.querySelector(`meta[property="${property}"]`);
  if (!tag) { tag = document.createElement('meta'); tag.setAttribute('property', property); document.head.appendChild(tag); }
  tag.content = content;
}
function setCanonical(href) {
  let tag = document.querySelector('link[rel="canonical"]');
  if (!tag) { tag = document.createElement('link'); tag.rel = 'canonical'; document.head.appendChild(tag); }
  tag.href = href;
}

load();
