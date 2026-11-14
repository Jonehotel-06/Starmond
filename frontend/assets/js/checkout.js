/**
 * checkout.js — checkout service layer.
 *
 * Both cart checkout and Buy Now use these SAME endpoints. The only difference
 * is the payload's `mode` and line items. The backend creates the order,
 * reserves stock, computes every amount and initializes the Paystack
 * transaction. The frontend never computes a payable total.
 */

import api from './api.js';
import { getBuyNowIntent, isBuyNowMode } from './cart.js';

/**
 * Geographic reference data for Nigerian states. This is public administrative
 * geography, not business data. The backend's shipping-zone list takes
 * precedence whenever it is available.
 */
export const NIGERIAN_STATES = [
  'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno',
  'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'FCT - Abuja', 'Gombe',
  'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos',
  'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto',
  'Taraba', 'Yobe', 'Zamfara',
];

/** States the store actually delivers to (falls back to all when unknown). */
export async function getDeliverableStates() {
  try {
    const data = await api.publicGet('/shipping/states/');
    const list = Array.isArray(data) ? data : data?.results || data?.states || [];
    const names = list.map((entry) => (typeof entry === 'string' ? entry : entry.name)).filter(Boolean);
    return names.length ? names : NIGERIAN_STATES;
  } catch {
    return NIGERIAN_STATES;
  }
}

/**
 * Backend-configured delivery methods for a destination.
 * Never invents a price: if the API cannot answer, the caller must show an
 * error rather than a guessed fee.
 */
export async function getDeliveryOptions({ state, city, mode = 'cart', items = null } = {}) {
  const params = { state, city };
  if (mode === 'buy_now' && items) params.items = JSON.stringify(items);
  const data = await api.privateGet('/checkout/delivery-options/', { params });
  const list = Array.isArray(data) ? data : data?.results || data?.methods || [];
  return list.map((method) => ({
    id: method.id ?? method.code,
    code: method.code ?? method.id,
    name: method.name,
    description: method.description || method.eta || '',
    fee: method.fee ?? method.price ?? null,
    currency: method.currency || 'NGN',
    is_pickup: !!method.is_pickup,
    eta: method.eta || method.estimated_days || null,
    available: method.available !== false,
    unavailable_reason: method.unavailable_reason || null,
  }));
}

/** Build the line-item payload for the current checkout mode. */
export function checkoutLines(mode) {
  if (mode === 'buy_now') {
    const intent = getBuyNowIntent();
    if (!intent) return null;
    return [{ product: intent.product, variation: intent.variation, quantity: intent.quantity }];
  }
  return null; // cart mode: the backend reads the server-side cart
}

export function currentMode(search) {
  return isBuyNowMode(search) ? 'buy_now' : 'cart';
}

/**
 * Authoritative pricing preview. Called on load and whenever the address,
 * delivery method or coupon changes.
 * @returns {{items:Array, totals:Object, discounts:Array, changes:Array, currency:string}}
 */
export async function previewCheckout(payload) {
  const data = await api.post('/checkout/preview/', payload);
  return {
    items: data.items || data.cart?.items || [],
    totals: data.totals || {
      subtotal: data.subtotal ?? null,
      discount_total: data.discount_total ?? null,
      shipping_total: data.shipping_total ?? data.shipping_fee ?? null,
      tax_total: data.tax_total ?? null,
      fees: data.fees || [],
      total: data.total ?? null,
      currency: data.currency || 'NGN',
    },
    discounts: data.discounts || [],
    changes: data.changes || [],
    currency: data.currency || data.totals?.currency || 'NGN',
    coupon: data.coupon || null,
    raw: data,
  };
}

/** Apply/remove a discount code against the current checkout context. */
export function applyCheckoutCoupon(payload) {
  return api.post('/checkout/coupon/', payload);
}
export function removeCheckoutCoupon(payload) {
  return api.delete('/checkout/coupon/', { body: payload });
}

/**
 * Create the pending order and initialize payment.
 * The backend reserves inventory and returns the Paystack authorization URL.
 * The frontend NEVER marks an order as paid.
 */
export async function createOrder(payload) {
  const data = await api.post('/checkout/orders/', payload);
  return {
    order: data.order || data,
    reference: data.order?.reference || data.reference || data.order_reference,
    payment: data.payment || null,
    authorizationUrl: data.payment?.authorization_url || data.authorization_url || null,
    accessUrl: data.order?.access_url || data.access_url || null,
  };
}

/** Persist non-sensitive checkout form details for convenience. */
export const CHECKOUT_DRAFT_KEY = 'checkout_draft';

export function buildOrderPayload({ mode, form, deliveryMethod, couponCode, lines }) {
  const payload = {
    mode,
    customer: {
      full_name: String(form.full_name || '').trim(),
      email: String(form.email || '').trim().toLowerCase(),
      phone: String(form.phone || '').trim(),
    },
    delivery: {
      state: form.state,
      city: String(form.city || '').trim(),
      address_line1: String(form.address_line1 || '').trim(),
      address_line2: String(form.address_line2 || '').trim(),
      instructions: String(form.delivery_instructions || '').trim(),
      method: deliveryMethod,
    },
    save_address: !!form.save_address,
    accept_terms: !!form.accept_terms,
    currency: 'NGN',
  };
  if (couponCode) payload.coupon_code = couponCode;
  if (mode === 'buy_now') payload.items = lines;
  return payload;
}

/** Client-side convenience validation. The backend re-validates everything. */
export function validateCheckoutForm(form, { deliveryMethod }) {
  const errors = {};
  if (!String(form.full_name || '').trim()) errors.full_name = 'Enter the full name for this delivery.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(form.email || '').trim())) errors.email = 'Enter a valid email address.';
  const phone = String(form.phone || '').replace(/[^\d]/g, '');
  if (phone.length < 10) errors.phone = 'Enter a valid phone number the rider can reach.';
  if (!form.state) errors.state = 'Select your state.';
  if (!String(form.city || '').trim()) errors.city = 'Enter your city or town.';
  if (!String(form.address_line1 || '').trim()) errors.address_line1 = 'Enter the delivery address.';
  if (!deliveryMethod) errors.delivery_method = 'Choose a delivery method.';
  if (!form.accept_terms) errors.accept_terms = 'Please accept the terms to continue.';
  return errors;
}

export default { previewCheckout, createOrder, getDeliveryOptions, getDeliverableStates };
