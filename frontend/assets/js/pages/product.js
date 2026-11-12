/**
 * Product details page.
 * Renders only backend data: price, stock, variants, reviews. It never computes
 * prices, and Buy Now always uses the backend's buy-now session so the existing
 * cart is untouched.
 */
import { ready } from '../app.js';
import { catalog, checkout } from '../api.js';
import { CONFIG } from '../env.js';
import { cart as cartStore, session, wishlist } from '../store.js';
import { toast, notifyError } from '../ui/toast.js';
import { renderProducts, productUrl, productImage } from '../ui/cards.js';
import { breadcrumbJsonLd, productJsonLd, setJsonLd, setMeta } from '../seo.js';
import {
  clearErrors, esc, fieldError, formatDate, money, qs, qsa, sessionStore, setBusy, sitePath, starRow, validate
} from '../utils.js';

const el = {
  pdp: qs('[data-pdp]'),
  crumbs: qs('[data-product-crumbs] ol'),
  brand: qs('[data-pdp-brand]'),
  title: qs('[data-pdp-title]'),
  rating: qs('[data-pdp-rating]'),
  sku: qs('[data-pdp-sku]'),
  price: qs('[data-pdp-price]'),
  stock: qs('[data-pdp-stock]'),
  form: qs('[data-buy-form]'),
  variations: qs('[data-variations]'),
  qty: qs('[data-qty-input]'),
  qtyHint: qs('[data-qty-hint]'),
  addBtn: qs('[data-add-to-cart]'),
  buyBtn: qs('[data-buy-now]'),
  wishBtn: qs('[data-wishlist-toggle]'),
  error: qs('[data-buy-error]'),
  gallery: qs('[data-gallery-main]'),
  thumbs: qs('[data-gallery-thumbs]'),
  description: qs('[data-pdp-description]'),
  specs: qs('[data-pdp-specs]'),
  reviews: qs('[data-reviews]'),
  reviewForm: qs('[data-review-form]'),
  reviewWrap: qs('[data-review-form-wrap]'),
  reviewSignin: qs('[data-review-signin]'),
  related: qs('[data-related-grid]'),
  sticky: qs('[data-sticky-buy]'),
  stickyPrice: qs('[data-sticky-price]'),
  stickyName: qs('[data-sticky-name]')
};

/* Product URLs come in two shapes:
     1. /product/<slug>/          → server-rendered route, indexable, canonical
     2. /product.html?slug=<slug> → static shell used until (1) is deployed,
                                    deliberately noindex to avoid a thin duplicate
   See reports/SEO_STRATEGY.md for the backend contract. */
const pathSegments = window.location.pathname.split('/').filter(Boolean);
const prettyIndex = pathSegments.indexOf('product');
const prettySlug = prettyIndex >= 0 && pathSegments[prettyIndex + 1] && !pathSegments[prettyIndex + 1].includes('.html')
  ? decodeURIComponent(pathSegments[prettyIndex + 1])
  : null;
const IS_PRETTY_URL = Boolean(prettySlug);
const slug = prettySlug || new URLSearchParams(location.search).get('slug');
let product = null;
let variants = [];
let options = [];
const selection = {};
let quantity = 1;

/* ------------------------------------------------------------------ render */
function gallery(images) {
  const list = (images || []).map((img) => (typeof img === 'string' ? img : (img.url || img.image))).filter(Boolean);
  if (!list.length) {
    el.gallery.innerHTML = `<div class="media-placeholder"><span>No image provided</span></div>`;
    el.thumbs.innerHTML = '';
    return;
  }
  el.gallery.innerHTML = `<img src="${esc(list[0])}" alt="${esc(product.name)}" width="720" height="720" fetchpriority="high" decoding="async">`;
  el.thumbs.innerHTML = list.map((src, i) => `<li><button class="gallery__thumb" type="button"
      data-thumb="${i}" aria-current="${i === 0 ? 'true' : 'false'}" aria-label="Show image ${i + 1} of ${list.length}">
      <img src="${esc(src)}" alt="" width="66" height="66" loading="lazy"></button></li>`).join('');
  qsa('[data-thumb]', el.thumbs).forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.thumb);
      el.gallery.querySelector('img').src = list[idx];
      qsa('[data-thumb]', el.thumbs).forEach((b) => b.setAttribute('aria-current', String(b === btn)));
    });
  });
}

function renderVariations() {
  if (!options.length) { el.variations.innerHTML = ''; return; }
  el.variations.innerHTML = options.map((option, oi) => {
    const name = option.name || option.label || `Option ${oi + 1}`;
    const values = option.values || option.options || [];
    return `<div class="variation-set" data-option="${esc(name)}">
      <span class="variation-set__label" id="opt-${oi}">${esc(name)}</span>
      <div class="variation-set__options" role="group" aria-labelledby="opt-${oi}">
        ${values.map((v) => {
          const value = typeof v === 'string' ? v : (v.value || v.name);
          const disabled = !variantAvailable(name, value);
          return `<button class="variation-opt" type="button" data-option-name="${esc(name)}"
            data-option-value="${esc(value)}" aria-pressed="false" ${disabled ? 'disabled' : ''}>${esc(value)}</button>`;
        }).join('')}
      </div>
    </div>`;
  }).join('');

  qsa('.variation-opt', el.variations).forEach((btn) => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.optionName;
      const value = btn.dataset.optionValue;
      selection[name] = value;
      qsa(`[data-option-name="${CSS.escape(name)}"]`, el.variations)
        .forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
      onSelectionChange();
    });
  });
}

function variantAvailable(optionName, value) {
  if (!variants.length) return true;
  return variants.some((v) => {
    const attrs = v.attributes || v.options || {};
    const matchesCurrent = Object.entries(selection).every(([k, val]) => !attrs[k] || attrs[k] === val);
    return attrs[optionName] === value && matchesCurrent && v.in_stock !== false;
  });
}

function currentVariant() {
  if (!variants.length) return null;
  return variants.find((v) => {
    const attrs = v.attributes || v.options || {};
    return options.every((opt) => {
      const key = opt.name || opt.label;
      return attrs[key] === selection[key];
    });
  }) || null;
}

function onSelectionChange() {
  const variant = currentVariant();
  const price = variant?.price ?? product.price;
  const stockQty = variant?.stock_quantity ?? product.stock_quantity;
  const inStock = variant ? variant.in_stock !== false : product.in_stock !== false;

  if (price !== undefined) {
    el.price.innerHTML = `<span class="price">${money(price, product.currency)}</span>
      ${product.compare_at_price && Number(product.compare_at_price) > Number(price)
        ? `<span class="price--was">${money(product.compare_at_price, product.currency)}</span>` : ''}`;
    if (el.stickyPrice) el.stickyPrice.textContent = money(price, product.currency);
  }
  renderStock({ inStock, stockQty });
  updateQtyBounds(inStock ? stockQty : 0);
}

function renderStock({ inStock, stockQty }) {
  const qty = Number(stockQty);
  let text = 'In stock — ready to ship';
  let cls = 'is-in';
  if (!inStock) { text = 'Out of stock — contact us for an arrival estimate'; cls = 'is-out'; }
  else if (Number.isFinite(qty) && qty > 0 && qty <= 5) { text = `Low stock — only ${qty} left`; cls = 'is-low'; }
  el.stock.textContent = text;
  el.stock.className = `pdp__stock ${cls}`;
  const disabled = !inStock;
  [el.addBtn, el.buyBtn].forEach((btn) => { if (btn) btn.disabled = disabled; });
  qsa('[data-sticky-cart], [data-sticky-buy-now]').forEach((btn) => { btn.disabled = disabled; });
}

function updateQtyBounds(max) {
  const limit = Number.isFinite(Number(max)) && Number(max) > 0 ? Math.min(Number(max), 99) : 99;
  el.qty.max = String(limit);
  if (quantity > limit) quantity = limit;
  el.qty.value = String(quantity);
  if (el.qtyHint) {
    el.qtyHint.textContent = max === 0 ? 'Out of stock'
      : (limit < 99 ? `Maximum ${limit} per order` : '');
  }
  if (el.sticky) el.sticky.dataset.max = String(limit);
}

/* --------------------------------------------------------------- buy actions */
function readQuantity() {
  const max = Number(el.qty.max) || 99;
  let value = parseInt(el.qty.value, 10);
  if (!Number.isFinite(value) || value < 1) value = 1;
  if (value > max) value = max;
  quantity = value;
  el.qty.value = String(value);
  return value;
}

function validateSelection() {
  clearErrors(el.form);
  if (el.error) el.error.hidden = true;
  if (options.length) {
    const missing = options.filter((opt) => !selection[opt.name || opt.label]);
    if (missing.length) {
      const message = `Choose a ${missing.map((o) => o.name || o.label).join(' and ')} first.`;
      if (el.error) { el.error.textContent = message; el.error.hidden = false; }
      el.variations.querySelector('.variation-opt')?.focus();
      return false;
    }
    if (variants.length && !currentVariant()) {
      if (el.error) { el.error.textContent = 'That combination is not available. Try another option.'; el.error.hidden = false; }
      return false;
    }
  }
  return true;
}

async function handleAddToCart(event) {
  event?.preventDefault();
  if (!validateSelection()) return;
  const variant = currentVariant();
  setBusy(el.addBtn, true);
  try {
    await cartStore.add({ product_id: product.id, variant_id: variant?.id ?? null, quantity: readQuantity() });
    toast(`${product.name} added to your cart.`, { type: 'success' });
  } catch (err) {
    notifyError(err);
  } finally {
    setBusy(el.addBtn, false);
  }
}

async function handleBuyNow() {
  if (!validateSelection()) return;
  setBusy(el.buyBtn, true);
  try {
    const variant = currentVariant();
    const data = await checkout.buyNow({
      product_id: product.id,
      variant_id: variant?.id ?? null,
      quantity: readQuantity()
    });
    sessionStore(CONFIG.BUY_NOW_KEY, {
      token: data?.buy_now_token || data?.token || null,
      subtotal: data?.subtotal ?? null,
      line_items: data?.line_items || data?.items || [],
      created: Date.now(),
      product_slug: product.slug,
      /* Display snapshot only — the backend recalculates everything at checkout. */
      display_only: true
    });
    window.location.href = `${sitePath('checkout.html')}?mode=buy_now`;
  } catch (err) {
    notifyError(err);
    setBusy(el.buyBtn, false);
  }
}

/* ----------------------------------------------------------------- reviews */
async function loadReviews() {
  if (!el.reviews) return;
  try {
    const data = await catalog.reviews(product.slug);
    const items = data.items;
    if (!items.length) {
      el.reviews.innerHTML = `<p class="muted">No reviews yet${product.review_count === 0 ? '' : ''}. Ordered this product before? Sign in to write the first review.</p>`;
    } else {
      el.reviews.innerHTML = `${product.rating_average ? `<p class="pdp__meta"><span class="review__stars" aria-hidden="true">${starRow(product.rating_average)}</span>
          <strong>${Number(product.rating_average).toFixed(1)}</strong> out of 5 · ${product.review_count ?? items.length} review(s)</p>` : ''}
        <ul class="review-list">${items.map((review) => `
          <li class="review">
            <div class="review__head">
              <span class="review__stars" aria-hidden="true">${starRow(review.rating)}</span>
              <span class="sr-only">Rated ${review.rating} out of 5</span>
              <span class="review__author">${esc(review.author_name || review.customer_name || 'Verified customer')}</span>
              ${review.is_verified_purchase ? '<span class="review__verified">Verified purchase</span>' : ''}
              <span class="review__date">${formatDate(review.created_at)}</span>
            </div>
            ${review.title ? `<p class="review__title">${esc(review.title)}</p>` : ''}
            <p class="review__body">${esc(review.body || review.comment || '')}</p>
          </li>`).join('')}</ul>`;
    }
  } catch (err) {
    el.reviews.innerHTML = `<p class="muted">Reviews could not be loaded right now.</p>`;
  }

  const signedIn = session.isAuthenticated;
  if (el.reviewWrap) el.reviewWrap.hidden = !signedIn;
  if (el.reviewSignin) {
    el.reviewSignin.hidden = signedIn;
    const link = el.reviewSignin.querySelector('a');
    if (link) link.href = `${sitePath('login.html')}?next=${encodeURIComponent(location.pathname + location.search)}`;
  }
}

function initReviewForm() {
  if (!el.reviewForm) return;
  el.reviewForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors(el.reviewForm);
    const data = new FormData(el.reviewForm);
    const rating = data.get('rating');
    const title = String(data.get('title') || '').trim();
    const body = String(data.get('body') || '').trim();
    let valid = true;
    if (!rating) { fieldError(el.reviewForm, 'rating', 'Choose a star rating.'); valid = false; }
    const titleErr = validate.required(title, 'A review title');
    if (titleErr) { fieldError(el.reviewForm, 'title', titleErr); valid = false; }
    const bodyErr = validate.minLen(body, 10, 'Your review');
    if (bodyErr) { fieldError(el.reviewForm, 'body', bodyErr); valid = false; }
    if (!valid) return;

    const button = el.reviewForm.querySelector('button[type="submit"]');
    setBusy(button, true);
    try {
      const result = await catalog.createReview(product.slug, { rating: Number(rating), title, body });
      el.reviewForm.reset();
      const pending = result?.status === 'pending' || result?.is_approved === false;
      toast(pending ? 'Thanks — your review is awaiting moderation.' : 'Thank you, your review has been published.', { type: 'success' });
      if (!pending) loadReviews();
    } catch (err) {
      if (err.fields) Object.entries(err.fields).forEach(([field, message]) => fieldError(el.reviewForm, field, message));
      notifyError(err);
    } finally {
      setBusy(button, false);
    }
  });
}

/* -------------------------------------------------------------- page wiring */
function renderProduct() {
  el.pdp.removeAttribute('aria-busy');
  const category = product.category;
  const categoryName = category?.name || 'Shop';

  /* Breadcrumbs */
  el.crumbs.innerHTML = `
    <li><a href="${sitePath('index.html')}">Home</a></li>
    <li><a href="${sitePath('shop.html')}">Shop</a></li>
    ${category?.slug ? `<li><a href="${sitePath(`category/${category.slug}/`)}">${esc(categoryName)}</a></li>` : ''}
    <li aria-current="page">${esc(product.name)}</li>`;

  el.brand.textContent = product.brand || categoryName;
  el.title.textContent = product.name;
  el.sku.textContent = product.sku ? `SKU ${product.sku}` : '';
  el.rating.innerHTML = product.rating_average
    ? `<span class="pdp__rating"><svg class="icon" aria-hidden="true"><use href="#i-star"></use></svg>
       ${Number(product.rating_average).toFixed(1)}${product.review_count ? ` · ${product.review_count} review(s)` : ''}</span>`
    : '<span class="muted">No reviews yet</span>';

  gallery(product.images || [product.primary_image].filter(Boolean));

  variants = product.variants || product.variations || [];
  options = product.options || product.variation_options || [];
  if (!options.length && variants.length) {
    const keys = new Set();
    variants.forEach((v) => Object.keys(v.attributes || v.options || {}).forEach((k) => keys.add(k)));
    options = Array.from(keys).map((name) => ({
      name,
      values: Array.from(new Set(variants.map((v) => (v.attributes || v.options || {})[name])).filter(Boolean))
    }));
  }
  if (options.length === 1 && (options[0].values || []).length === 1) {
    selection[options[0].name || options[0].label] = (options[0].values || [])[0];
  }
  renderVariations();
  onSelectionChange();

  el.description.innerHTML = product.description
    ? `<div>${product.description}</div>`
    : `<p class="muted">A full description for this product has not been published yet. Contact us if you need a specific detail confirmed before ordering.</p>`;

  const specs = product.specifications || product.specs || {};
  const rows = Array.isArray(specs)
    ? specs.map((s) => [s.name || s.label, s.value])
    : Object.entries(specs);
  el.specs.innerHTML = rows.length
    ? rows.map(([key, value]) => `<tr><th scope="row">${esc(key)}</th><td>${esc(value)}</td></tr>`).join('')
    : '<tr><td class="muted">No published specification table for this product. Ask us before ordering if a specific detail matters.</td></tr>';

  el.wishBtn.dataset.wishlistProduct = String(product.id);
  const saved = wishlist.has(product.id);
  el.wishBtn.setAttribute('aria-pressed', String(saved));
  el.wishBtn.setAttribute('aria-label', saved ? 'Remove from wishlist' : 'Save to wishlist');

  if (el.sticky) {
    el.stickyName.textContent = product.name;
    el.stickyPrice.textContent = money(product.price, product.currency);
  }

  /* SEO: mirror the server-rendered values for the runtime view. */
  const title = product.meta_title || `${product.name} | STARMOND TECHNOLOGY LIMITED`;
  const description = (product.meta_description || product.short_description
    || (product.description || '').replace(/<[^>]+>/g, ' ').trim().slice(0, 158)
    || `Buy ${product.name} at STARMOND TECHNOLOGY LIMITED with verified stock, current Naira pricing and nationwide delivery.`);
  setMeta({
    title,
    description,
    canonicalPath: `product/${product.slug}/`,
    image: productImage(product),
    type: 'product',
    /* The static shell is a duplicate of the server-rendered route. */
    robots: IS_PRETTY_URL ? 'index, follow, max-image-preview:large' : 'noindex, follow'
  });
  setJsonLd('product', productJsonLd(product, { url: `product/${product.slug}/`, categoryName }));
  setJsonLd('breadcrumbs', breadcrumbJsonLd([
    { name: 'Home', path: '' },
    { name: 'Shop', path: 'shop.html' },
    category ? { name: categoryName, path: `category/${category.slug}/` } : null,
    { name: product.name, path: `product/${product.slug}/` }
  ]));

  loadRelated();
  loadReviews();
}

async function loadRelated() {
  if (!el.related) return;
  try {
    const data = await catalog.related(product.slug);
    const items = Array.isArray(data) ? data : (data?.results || data?.items || []);
    if (!items.length) { el.related.closest('section').hidden = true; return; }
    renderProducts(el.related, items.slice(0, 4));
  } catch {
    el.related.closest('section').hidden = true;
  }
}

function initSticky() {
  if (!el.sticky || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver(([entry]) => {
    const show = !entry.isIntersecting && window.innerWidth <= 980;
    el.sticky.hidden = !show;
  }, { rootMargin: '-40px 0px 0px 0px' });
  const actions = qs('.pdp__actions');
  if (actions) observer.observe(actions);
}

function showLoadError(err) {
  el.pdp.removeAttribute('aria-busy');
  el.pdp.innerHTML = `<div class="alert alert--error" role="alert" style="grid-column:1/-1">
      <svg class="icon icon--sm" aria-hidden="true"><use href="#i-close"></use></svg>
      <div>
        <p><strong>${esc(err?.status === 404 ? 'We could not find that product.' : 'This product could not be loaded.')}</strong></p>
        <p>${esc(err?.message || 'Please try again in a moment.')}</p>
        <p><a class="btn btn--outline" href="${sitePath('shop.html')}">Browse all products</a></p>
      </div>
    </div>`;
  setMeta({ title: 'Product unavailable | STARMOND TECHNOLOGY LIMITED', robots: 'noindex, follow' });
}

async function init() {
  await ready;
  if (!slug) { showLoadError({ status: 404, message: 'No product was specified in the link.' }); return; }

  el.form?.addEventListener('submit', handleAddToCart);
  el.buyBtn?.addEventListener('click', handleBuyNow);
  qs('[data-sticky-cart]')?.addEventListener('click', () => { el.form?.requestSubmit ? el.form.requestSubmit() : handleAddToCart(); });
  qs('[data-sticky-buy-now]')?.addEventListener('click', handleBuyNow);
  qs('[data-qty-up]')?.addEventListener('click', () => { el.qty.value = String(Math.min(Number(el.qty.max || 99), readQuantity() + 1)); });
  qs('[data-qty-down]')?.addEventListener('click', () => { el.qty.value = String(Math.max(1, readQuantity() - 1)); });
  el.qty?.addEventListener('change', readQuantity);
  el.wishBtn?.addEventListener('click', async () => {
    if (!product) return;
    try {
      const { added } = await wishlist.toggle(product);
      el.wishBtn.setAttribute('aria-pressed', String(added));
      el.wishBtn.setAttribute('aria-label', added ? 'Remove from wishlist' : 'Save to wishlist');
      toast(added ? 'Saved to your wishlist.' : 'Removed from your wishlist.', { type: added ? 'success' : 'info' });
    } catch (err) { notifyError(err); }
  });
  initReviewForm();
  initSticky();

  try {
    product = await catalog.product(slug);
    if (!product || !product.id) throw new Error('Product data was incomplete.');
    renderProduct();
  } catch (err) {
    showLoadError(err);
  }
}

init();
