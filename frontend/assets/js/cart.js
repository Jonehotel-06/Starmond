/**
 * cart.js — cart state facade over the backend cart service.
 *
 * IMPORTANT
 *   • The backend owns the cart. This module never computes a payable total,
 *     never decides stock, and never authorizes a discount.
 *   • Guests are identified by an opaque, rotating `X-Cart-Token` header that
 *     api.js attaches. No price or personal data is stored in the browser.
 *   • "Buy Now" uses a SEPARATE sessionStorage intent. It never reads from or
 *     writes to the cart, so an existing cart is always preserved.
 */

import api from './api.js';
import { createStorage } from './utils.js';

const session = createStorage('session');
const BUY_NOW_KEY = 'buy_now_intent';
const BUY_NOW_TTL_MS = 30 * 60 * 1000;

let cachedCart = null;
let pending = null;
const listeners = new Set();

/* ============================================================================
   Events
   ========================================================================== */

function emit(reason, cart = cachedCart) {
  listeners.forEach((fn) => { try { fn(cart, reason); } catch (err) { console.error(err); } });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('starmond:cart-changed', { detail: { reason, cart } }));
  }
}

export function onCartChange(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

/* ============================================================================
   Read
   ========================================================================== */

/** The discount code the shopper entered. The backend has no "cart coupon"
 *  resource: a code is validated by POST /checkout/preview/ and finally
 *  applied (and usage-counted) by POST /checkout/. We only remember the text. */
const COUPON_KEY = 'cart_coupon';
export function getCouponCode() { return session.get(COUPON_KEY) || ''; }
function setCouponCode(code) { if (code) session.set(COUPON_KEY, code); else session.remove(COUPON_KEY); }

export async function getCart({ force = false } = {}) {
  if (cachedCart && !force) return cachedCart;
  if (pending && !force) return pending;
  pending = api.privateGet('/cart/')
    .then((data) => adopt(data, 'fetch'))
    .finally(() => { pending = null; });
  return pending;
}

export function getCachedCart() { return cachedCart; }

/** Map one backend cart line (apps/cart/serializers.py) to the UI shape. */
function normalizeItem(item) {
  if (!item || typeof item !== 'object') return item;
  if (item.product && typeof item.product === 'object') return item;
  return {
    id: item.id,
    quantity: Number(item.quantity) || 0,
    unit_price: item.unit_price,
    line_total: item.line_total,
    product: {
      id: item.product,
      name: item.product_name,
      slug: item.product_slug,
      url: item.product_slug ? `/products/${item.product_slug}/` : null,
      images: item.image_url ? [{ url: item.image_url, alt: item.product_name }] : [],
    },
    variation: item.variation ? {
      id: item.variation,
      label: item.variation_label || '',
      options: item.variation_options || {},
    } : null,
  };
}

/** Normalise the cart payload so pages can rely on a stable shape. */
export function normalizeCart(data) {
  if (!data || typeof data !== 'object') {
    return { items: [], item_count: 0, quantity_total: 0, currency: 'NGN', totals: null, warnings: [], changes: [], coupon: null };
  }
  const items = (Array.isArray(data.items) ? data.items : []).map(normalizeItem);
  const quantity = items.reduce((sum, i) => sum + (Number(i.quantity) || 0), 0);
  const currency = data.currency || data.totals?.currency || 'NGN';
  return {
    ...data,
    items,
    item_count: items.length,
    quantity_total: quantity,
    currency,
    totals: {
      subtotal: data.totals?.subtotal ?? data.subtotal ?? null,
      discount_total: data.totals?.discount ?? null,
      shipping_estimate: null, // delivery is quoted at checkout once a state is chosen
      total: data.totals?.total ?? data.subtotal ?? null,
      currency,
    },
    coupon: data.coupon || null,
    discount_code: data.coupon?.code || null,
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    changes: Array.isArray(data.changes) ? data.changes : [],
  };
}

/** Line count shown on the header badge = total units. */
export function getCartCount(cart = cachedCart) {
  return Number(cart?.quantity_total ?? cart?.item_count ?? 0) || 0;
}

/** Store the authoritative cart, remember the server-issued guest token. */
function adopt(data, reason) {
  if (data?.token) api.setCartToken(data.token);
  const previous = cachedCart;
  cachedCart = normalizeCart(data);
  // Keep the last verified discount until it is re-priced.
  if (previous?.coupon && getCouponCode() && cachedCart.items.length) {
    cachedCart.coupon = previous.coupon;
    cachedCart.discount_code = previous.coupon.code;
  }
  emit(reason, cachedCart);
  return cachedCart;
}

/**
 * Ask the backend to price the cart (POST /checkout/preview/). Used to show a
 * verified discount on the cart page. Never computes money in the browser.
 */
export async function priceCart({ code = getCouponCode() } = {}) {
  const cart = await getCart();
  if (!cart.items.length) { setCouponCode(''); return { cart, error: null }; }
  const preview = await api.post('/checkout/preview/', {
    source: { type: 'cart' },
    promotion_code: code || '',
    cart_token: api.getCartToken() || undefined,
  });
  const error = preview.promotion_error || null;
  if (error) setCouponCode('');
  cachedCart = {
    ...cart,
    totals: {
      subtotal: preview.totals.subtotal,
      discount_total: Number(preview.totals.discount) > 0 ? preview.totals.discount : null,
      shipping_estimate: null,
      total: preview.totals.total,
      currency: preview.totals.currency,
    },
    coupon: preview.promotion || null,
    discount_code: preview.promotion?.code || null,
  };
  emit('price', cachedCart);
  return { cart: cachedCart, error };
}

/* ============================================================================
   Mutations — every one returns the backend's authoritative cart
   ========================================================================== */

async function afterMutation(data, reason) {
  adopt(data, reason);
  if (getCouponCode() && cachedCart.items.length) {
    try { await priceCart(); } catch { /* totals fall back to the subtotal */ }
  } else if (!cachedCart.items.length) {
    setCouponCode('');
  }
  return cachedCart;
}

/** POST /cart/ {product, variation, quantity} */
export async function addItem({ product, variation = null, quantity = 1 }) {
  const payload = { product: Number(product), quantity: Number(quantity) || 1 };
  if (variation !== null && variation !== undefined && variation !== '') payload.variation = Number(variation);
  const data = await api.post('/cart/', payload);
  return afterMutation(data, 'add');
}

/** PATCH /cart/items/<id>/ {quantity} */
export async function updateItem(itemId, quantity) {
  const data = await api.patch(`/cart/items/${encodeURIComponent(itemId)}/`, { quantity: Number(quantity) });
  return afterMutation(data, 'update');
}

/** DELETE /cart/items/<id>/ */
export async function removeItem(itemId) {
  const data = await api.delete(`/cart/items/${encodeURIComponent(itemId)}/`);
  return afterMutation(data, 'remove');
}

/** DELETE /cart/ */
export async function clearCart() {
  await api.delete('/cart/');
  setCouponCode('');
  cachedCart = null;
  return getCart({ force: true });
}

/** Validate a discount code against the current cart (server-side). */
export async function applyCoupon(code) {
  const clean = String(code || '').trim();
  const { cart, error } = await priceCart({ code: clean });
  if (error || !cart.coupon) {
    const failure = new Error(error || 'This discount code cannot be used.');
    failure.userMessage = error || 'This discount code cannot be used.';
    failure.fieldErrors = { code: [failure.userMessage] };
    throw failure;
  }
  setCouponCode(cart.coupon.code);
  return { cart, message: `Code ${cart.coupon.code} applied.` };
}

export async function removeCoupon() {
  setCouponCode('');
  if (cachedCart) {
    cachedCart = normalizeCart({ ...cachedCart, totals: null, coupon: null, subtotal: cachedCart.totals?.subtotal });
    emit('coupon', cachedCart);
  }
  return getCart({ force: true });
}

/**
 * Re-read the cart before checkout. The backend silently drops delisted
 * products and re-checks prices, so a fresh read is the validation; lines that
 * disappeared or changed price are reported as `changes`.
 */
export async function validateCart() {
  const before = cachedCart;
  const cart = await getCart({ force: true });
  const changes = [];
  if (before) {
    before.items.forEach((old) => {
      const now = cart.items.find((i) => String(i.id) === String(old.id));
      if (!now) changes.push({ type: 'removed', message: `${old.product?.name || 'An item'} is no longer available and was removed.` });
      else if (Number(now.unit_price) !== Number(old.unit_price)) changes.push({ type: 'price', message: `The price of ${now.product?.name || 'an item'} has changed.` });
    });
  }
  cart.changes = changes;
  if (getCouponCode() && cart.items.length) {
    try { await priceCart(); } catch { /* handled by the page */ }
  }
  return { cart: cachedCart, changes };
}

/** POST /cart/merge/ {token} — after sign-in, fold the guest cart into the account cart. */
export async function mergeGuestCart() {
  const token = api.getCartToken();
  if (!token) return getCart({ force: true });
  try {
    const data = await api.post('/cart/merge/', { token });
    api.clearCartToken();
    return adopt(data, 'merge');
  } catch {
    api.clearCartToken();
    return getCart({ force: true }).catch(() => null);
  }
}

/** POST /customers/wishlist/move-to-cart/ {product} */
export async function moveWishlistItemToCart({ product }) {
  await api.post('/customers/wishlist/move-to-cart/', { product: Number(product) });
  return getCart({ force: true });
}

/* ============================================================================
   Buy Now — isolated direct-checkout intent
   ========================================================================== */

/**
 * Store a direct-purchase intent. Does NOT touch the cart.
 * @param {{product:string|number, variation?:string|number|null, quantity?:number}} line
 */
export function setBuyNowIntent({ product, variation = null, quantity = 1 }) {
  const intent = {
    product: String(product),
    variation: variation === '' || variation === undefined ? null : String(variation),
    quantity: Math.max(1, Number(quantity) || 1),
    created_at: Date.now(),
  };
  session.set(BUY_NOW_KEY, intent);
  return intent;
}

export function getBuyNowIntent() {
  const intent = session.get(BUY_NOW_KEY);
  if (!intent) return null;
  if (!intent.created_at || Date.now() - intent.created_at > BUY_NOW_TTL_MS) {
    clearBuyNowIntent();
    return null;
  }
  return intent;
}

export function clearBuyNowIntent() { session.remove(BUY_NOW_KEY); }

/** Navigate to the isolated direct checkout. */
export function startBuyNow({ product, variation = null, quantity = 1 }) {
  setBuyNowIntent({ product, variation, quantity });
  window.location.assign('/checkout.html?mode=buy');
}

/** True when the checkout page should use the Buy Now intent, not the cart. */
export function isBuyNowMode(search = (typeof location !== 'undefined' ? location.search : '')) {
  return new URLSearchParams(search).get('mode') === 'buy';
}

/* ============================================================================
   Header badge
   ========================================================================== */

/** Keep every [data-cart-count] badge in sync. */
export function initCartBadge() {
  const render = (cart) => {
    const count = getCartCount(cart);
    document.querySelectorAll('[data-cart-count]').forEach((node) => {
      node.textContent = count > 99 ? '99+' : String(count);
      node.hidden = count === 0;
    });
    document.querySelectorAll('[data-cart-link]').forEach((node) => {
      const label = count === 1 ? 'Cart, 1 item' : `Cart, ${count} items`;
      node.setAttribute('aria-label', label);
    });
  };
  onCartChange((cart) => render(cart));
  // Render an unknown badge as hidden until the backend answers — never guess.
  render(cachedCart);
  getCart().catch(() => { /* badge simply stays hidden if the cart is unreachable */ });
}

/** Drop the in-memory cart, e.g. after sign-out. */
export function resetCartCache() {
  cachedCart = null;
  setCouponCode('');
  emit('reset', null);
}

if (typeof window !== 'undefined') {
  window.addEventListener('starmond:auth-changed', (event) => {
    if (event.detail?.status === 'guest') { resetCartCache(); getCart({ force: true }).catch(() => {}); }
    else if (event.detail?.reason === 'login') return; // auth.login() awaits mergeGuestCart()
    else getCart({ force: true }).catch(() => {});
  });
}

export default { getCart, addItem, updateItem, removeItem, clearCart, applyCoupon, startBuyNow, onCartChange };
