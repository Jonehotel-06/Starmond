/**
 * STARMOND — Checkout data layer
 * ----------------------------------------------------------------------------
 * Backend contract (apps/orders, apps/shipping, apps/payments):
 *   GET  /shipping/states/                          → ["Lagos", …] states the store delivers to
 *   GET  /shipping/options/?state=&subtotal=        → delivery methods + fee for that state
 *   POST /checkout/preview/                         → authoritative totals (creates nothing)
 *   POST /checkout/   (+ Idempotency-Key header)    → creates the pending order, reserves stock
 *   POST /payments/paystack/initialize/             → Paystack authorization_url
 *
 * Every amount shown at checkout comes from the backend. The browser never
 * calculates prices, discounts or delivery fees.
 */

import api from './api.js';
import { getBuyNowIntent, isBuyNowMode } from './cart.js';
import { createStorage, randomToken } from './utils.js';

const session = createStorage('session');
const ACCESS_KEY = 'order_access';

/* ---------------------------------------------------------------- access -- */

/** Remember the guest access token the backend issued for an order (tab only). */
export function rememberOrderAccess(reference, token) {
  if (!reference || !token) return;
  const map = session.get(ACCESS_KEY, {}) || {};
  map[reference] = token;
  session.set(ACCESS_KEY, map);
}
export function getOrderAccess(reference) {
  return (session.get(ACCESS_KEY, {}) || {})[reference] || null;
}

/* -------------------------------------------------------------- delivery -- */

/** States with at least one active delivery method. Empty list = none configured. */
export async function getDeliverableStates() {
  const data = await api.publicGet('/shipping/states/');
  return (Array.isArray(data) ? data : []).filter(Boolean);
}

/** Delivery methods for a state. `code` is the ShippingMethod id the backend expects. */
export async function getDeliveryOptions({ state, subtotal = null } = {}) {
  const params = { state };
  if (subtotal !== null && subtotal !== undefined) params.subtotal = subtotal;
  const data = await api.publicGet('/shipping/options/', { params, cache: false });
  return (Array.isArray(data) ? data : []).map((method) => ({
    id: method.id,
    code: String(method.id),
    name: method.name,
    kind: method.kind,
    description: method.kind === 'pickup'
      ? (method.pickup_address ? `Collect from: ${method.pickup_address}` : 'Collect in store')
      : (method.estimated_delivery ? `Estimated ${method.estimated_delivery}` : ''),
    fee: method.fee,
    base_fee: method.base_fee,
    free_above: method.free_above_amount,
    currency: 'NGN',
    is_pickup: method.kind === 'pickup',
    pickup_address: method.pickup_address || '',
    eta: method.estimated_delivery || null,
    available: true,
  }));
}

/* ------------------------------------------------------------------ mode -- */

export function currentMode(search) {
  return isBuyNowMode(search) ? 'buy_now' : 'cart';
}

/** Buy Now line held in sessionStorage; null when it has expired. Cart mode → null. */
export function checkoutLines(mode) {
  if (mode !== 'buy_now') return null;
  const intent = getBuyNowIntent();
  if (!intent) return null;
  return [{ product: intent.product, variation: intent.variation, quantity: intent.quantity }];
}

function sourceFor(mode, lines) {
  if (mode === 'buy_now' && lines?.length) {
    const [line] = lines;
    return {
      type: 'buy_now',
      product_id: Number(line.product),
      variation_id: line.variation ? Number(line.variation) : null,
      quantity: Number(line.quantity) || 1,
    };
  }
  return { type: 'cart' };
}

/* --------------------------------------------------------------- preview -- */

/**
 * @param {{mode:string, lines?:Array, state?:string, deliveryMethod?:string, couponCode?:string}} input
 */
export async function previewCheckout({ mode, lines = null, state = '', deliveryMethod = null, couponCode = '' }) {
  const body = {
    source: sourceFor(mode, lines),
    promotion_code: couponCode || '',
    cart_token: api.getCartToken() || undefined,
  };
  if (state && deliveryMethod) body.delivery = { state, shipping_method_id: Number(deliveryMethod) };
  const data = await api.post('/checkout/preview/', body);
  const totals = data.totals || {};
  return {
    items: (data.items || []).map((item) => ({
      id: item.id,
      quantity: item.quantity,
      unit_price: item.unit_price,
      line_total: item.line_total,
      product: {
        id: item.product, name: item.product_name, slug: item.product_slug,
        images: item.image_url ? [{ url: item.image_url, alt: item.product_name }] : [],
      },
      variation: item.variation ? { id: item.variation, label: item.variation_label || '' } : null,
    })),
    totals: {
      subtotal: totals.subtotal ?? null,
      discount_total: totals.discount ?? null,
      shipping_total: totals.shipping_fee ?? null,
      total: totals.total ?? null,
      currency: totals.currency || 'NGN',
    },
    currency: totals.currency || 'NGN',
    coupon: data.promotion || null,
    couponError: data.promotion_error || null,
    shippingMethod: data.shipping_method || null,
    changes: [],
  };
}

/* ----------------------------------------------------------------- order -- */

/** Map the checkout form to the CheckoutSerializer body. */
export function buildOrderPayload({ mode, form, deliveryMethod, couponCode, lines, pickup = null }) {
  const fullName = String(form.full_name || '').trim();
  const phone = String(form.phone || '').trim();
  return {
    contact: {
      full_name: fullName,
      email: String(form.email || '').trim().toLowerCase(),
      phone,
    },
    delivery: {
      full_name: fullName,
      phone,
      state: form.state,
      city: String(form.city || '').trim(),
      // A pickup order has no delivery address; the collection point is recorded instead.
      street: pickup ? (pickup.pickup_address || `Pickup — ${pickup.name}`) : String(form.address_line1 || '').trim(),
      details: pickup ? '' : String(form.address_line2 || '').trim(),
      instructions: String(form.delivery_instructions || '').trim(),
      shipping_method_id: Number(deliveryMethod),
    },
    source: sourceFor(mode, lines),
    promotion_code: couponCode || '',
    cart_token: api.getCartToken() || '',
  };
}

/**
 * One idempotency key per distinct order payload. A double click, a network
 * retry or a page reload re-sends the same key, so the backend returns the
 * same order instead of creating a duplicate.
 */
function idempotencyKeyFor(payload) {
  const fingerprint = JSON.stringify(payload);
  const stored = session.get('checkout_idem');
  if (stored && stored.fingerprint === fingerprint && Date.now() - stored.at < 30 * 60 * 1000) return stored.key;
  const key = `chk-${randomToken(20)}`;
  session.set('checkout_idem', { fingerprint, key, at: Date.now() });
  return key;
}
export function clearCheckoutIdempotency() { session.remove('checkout_idem'); }

/** Create the order, then ask the backend for the Paystack payment link. */
export async function createOrder(payload) {
  const order = await api.post('/checkout/', payload, {
    headers: { 'Idempotency-Key': idempotencyKeyFor(payload) },
  });
  const reference = order.reference;
  const guestToken = order.next_step?.payload?.guest_token || null;
  rememberOrderAccess(reference, guestToken);
  const payment = await initializePayment(reference);
  return { order, reference, payment, authorizationUrl: payment.authorizationUrl };
}

/** POST /payments/paystack/initialize/ {order_reference, guest_token} */
export async function initializePayment(orderReference) {
  const body = { order_reference: orderReference };
  const token = getOrderAccess(orderReference);
  if (token) body.guest_token = token;
  const data = await api.post('/payments/paystack/initialize/', body);
  session.set(`payment_for:${data.provider_reference}`, orderReference);
  return {
    authorizationUrl: data.authorization_url || null,
    reference: data.provider_reference,
    paymentReference: data.payment_reference,
    amount: data.amount ?? null,
  };
}

export function saveAddress(form) {
  return api.post('/customers/addresses/', {
    kind: 'shipping',
    label: 'Delivery address',
    full_name: String(form.full_name || '').trim(),
    phone: String(form.phone || '').trim(),
    state: form.state,
    city: String(form.city || '').trim(),
    street: String(form.address_line1 || '').trim(),
    details: String(form.address_line2 || '').trim(),
    instructions: String(form.delivery_instructions || '').trim(),
  });
}

export function validateCheckoutForm(form, { deliveryMethod, pickup = false }) {
  const errors = {};
  if (!String(form.full_name || '').trim()) errors.full_name = 'Enter the full name for this delivery.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(form.email || '').trim())) errors.email = 'Enter a valid email address.';
  const phone = String(form.phone || '').replace(/[^\d]/g, '');
  if (phone.length < 10) errors.phone = 'Enter a valid phone number we can reach you on.';
  if (!form.state) errors.state = 'Select your state.';
  if (!String(form.city || '').trim()) errors.city = 'Enter your city or town.';
  if (!pickup && !String(form.address_line1 || '').trim()) errors.address_line1 = 'Enter the delivery address.';
  if (!deliveryMethod) errors.delivery_method = 'Choose a delivery method.';
  if (!form.accept_terms) errors.accept_terms = 'Please accept the terms to continue.';
  return errors;
}

export default { previewCheckout, createOrder, initializePayment, getDeliveryOptions, getDeliverableStates };
