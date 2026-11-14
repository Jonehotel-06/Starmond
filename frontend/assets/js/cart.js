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

/**
 * Fetch the authoritative cart.
 * @param {{force?:boolean}} [opts]
 */
export async function getCart({ force = false } = {}) {
  if (cachedCart && !force) return cachedCart;
  if (pending && !force) return pending;
  pending = api.privateGet('/cart/')
    .then((data) => {
      cachedCart = normalizeCart(data);
      emit('fetch', cachedCart);
      return cachedCart;
    })
    .finally(() => { pending = null; });
  return pending;
}

export function getCachedCart() { return cachedCart; }

/** Defensive normalization — tolerates a leaner backend payload. */
export function normalizeCart(data) {
  if (!data || typeof data !== 'object') {
    return { items: [], item_count: 0, quantity_total: 0, currency: 'NGN', totals: null, warnings: [] };
  }
  const items = Array.isArray(data.items) ? data.items : [];
  return {
    ...data,
    items,
    item_count: data.item_count ?? items.length,
    quantity_total: data.quantity_total ?? items.reduce((sum, i) => sum + (Number(i.quantity) || 0), 0),
    currency: data.currency || data.totals?.currency || 'NGN',
    totals: data.totals || {
      subtotal: data.subtotal ?? null,
      discount_total: data.discount_total ?? null,
      shipping_estimate: data.shipping_estimate ?? null,
      total: data.total ?? null,
      currency: data.currency || 'NGN',
    },
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    changes: Array.isArray(data.changes) ? data.changes : [],
  };
}

export function getCartCount(cart = cachedCart) {
  return Number(cart?.quantity_total ?? cart?.item_count ?? 0) || 0;
}

/* ============================================================================
   Mutations — every one returns the backend's authoritative cart
   ========================================================================== */

/**
 * @param {{product:string|number, variation?:string|number|null, quantity?:number}} line
 */
export async function addItem({ product, variation = null, quantity = 1 }) {
  const payload = { product, quantity: Number(quantity) || 1 };
  if (variation !== null && variation !== undefined && variation !== '') payload.variation = variation;
  const data = await api.post('/cart/items/', payload);
  cachedCart = normalizeCart(data.cart || data);
  emit('add', cachedCart);
  return cachedCart;
}

export async function updateItem(itemId, quantity) {
  const data = await api.patch(`/cart/items/${encodeURIComponent(itemId)}/`, { quantity: Number(quantity) });
  cachedCart = normalizeCart(data.cart || data);
  emit('update', cachedCart);
  return cachedCart;
}

export async function removeItem(itemId) {
  const data = await api.delete(`/cart/items/${encodeURIComponent(itemId)}/`);
  cachedCart = normalizeCart(data.cart || data);
  emit('remove', cachedCart);
  return cachedCart;
}

export async function clearCart() {
  const data = await api.delete('/cart/');
  cachedCart = normalizeCart(data?.cart || data || null);
  emit('clear', cachedCart);
  return cachedCart;
}

export async function applyCoupon(code) {
  const data = await api.post('/cart/coupon/', { code: String(code).trim() });
  cachedCart = normalizeCart(data.cart || data);
  emit('coupon', cachedCart);
  return { cart: cachedCart, message: data.message || data.detail || null };
}

export async function removeCoupon() {
  const data = await api.delete('/cart/coupon/');
  cachedCart = normalizeCart(data.cart || data);
  emit('coupon', cachedCart);
  return cachedCart;
}

/**
 * Ask the backend to re-price and re-check stock before checkout.
 * Returns {cart, changes[]} where changes describe price/stock movements the
 * shopper MUST be told about. We never silently accept a new payable amount.
 */
export async function validateCart() {
  const data = await api.post('/cart/validate/', {});
  cachedCart = normalizeCart(data.cart || data);
  emit('validate', cachedCart);
  return { cart: cachedCart, changes: cachedCart.changes || data.changes || [] };
}

/** Move a wishlist entry into the cart. */
export async function moveWishlistItemToCart({ product, variation = null, quantity = 1, wishlistItemId = null }) {
  const cart = await addItem({ product, variation, quantity });
  if (wishlistItemId) {
    try { await api.delete(`/wishlist/items/${encodeURIComponent(wishlistItemId)}/`); } catch { /* non-fatal */ }
  }
  return cart;
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
  emit('reset', null);
}

if (typeof window !== 'undefined') {
  window.addEventListener('starmond:auth-changed', (event) => {
    if (event.detail?.status === 'guest') resetCartCache();
    else getCart({ force: true }).catch(() => {});
  });
}

export default { getCart, addItem, updateItem, removeItem, clearCart, applyCoupon, startBuyNow, onCartChange };
