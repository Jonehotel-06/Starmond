/**
 * payments.js — Paystack redirect flow and backend verification.
 *
 * HARD RULES
 *   1. The frontend never holds a Paystack secret key.
 *   2. The frontend never verifies a payment itself.
 *   3. A browser redirect back from Paystack is NOT proof of payment.
 *   4. Success is displayed only when the backend says the payment succeeded.
 */

import api from './api.js';
import { createStorage } from './utils.js';
import { getOrderAccess, initializePayment } from './checkout.js';

const session = createStorage('session');

const PAYSTACK_HOSTS = ['checkout.paystack.com', 'paystack.com', 'standard.paystack.co'];

/** Only redirect to a URL the backend gave us on a genuine Paystack host. */
export function isTrustedPaystackUrl(url) {
  try {
    const parsed = new URL(url);
    // Local development only: a mock gateway on this machine (see docs). Never
    // reachable in production because the page itself is not served from localhost.
    const local = ['localhost', '127.0.0.1'];
    if (local.includes(window.location.hostname) && local.includes(parsed.hostname)) return true;
    if (parsed.protocol !== 'https:') return false;
    return PAYSTACK_HOSTS.some((host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`));
  } catch {
    return false;
  }
}

export function redirectToPaystack(authorizationUrl) {
  if (!authorizationUrl || !isTrustedPaystackUrl(authorizationUrl)) {
    throw new Error('The store returned an invalid payment URL. Please contact support with your order reference.');
  }
  window.location.assign(authorizationUrl);
}

/**
 * Ask the backend to verify a transaction with Paystack (server-to-server).
 * POST /payments/paystack/verify/ {reference, guest_token?}
 *
 * The browser being redirected back from Paystack proves nothing: only this
 * verified response (or the signed webhook) marks an order as paid.
 *
 * @param {string} reference Paystack transaction reference (?reference= / ?trxref=)
 * @param {string} [orderReference] order reference from ?order=, used to find the guest token
 */
export async function verifyPayment(reference, orderReference = null) {
  const orderRef = orderReference || session.get(`payment_for:${reference}`) || null;
  const body = { reference };
  const token = orderRef ? getOrderAccess(orderRef) : null;
  if (token) body.guest_token = token;
  const data = await api.post('/payments/paystack/verify/', body);
  return normalizeVerification(data, { reference, guest: !!token });
}

/** Poll a pending transaction with backoff. Never loops forever. */
export async function pollVerification(reference, { maxAttempts = 5, onUpdate, orderReference = null } = {}) {
  let attempt = 0;
  let result = null;
  while (attempt < maxAttempts) {
    result = await verifyPayment(reference, orderReference);
    onUpdate?.(result, attempt + 1);
    if (result.status !== 'pending') return result;
    attempt += 1;
    if (attempt < maxAttempts) await new Promise((resolve) => setTimeout(resolve, Math.min(2000 * attempt, 8000)));
  }
  return result;
}

/** Backend Payment.Status → the five states the result pages render. */
export function normalizeVerification(data, { reference = null, guest = false } = {}) {
  const raw = String(data?.payment_status || '').toLowerCase();
  const map = {
    successful: 'success', success: 'success',
    pending: 'pending', initialized: 'pending', processing: 'pending',
    failed: 'failed',
    abandoned: 'abandoned', cancelled: 'abandoned',
    reversed: 'reversed',
    refunded: 'refunded', partially_refunded: 'partially_refunded',
  };
  const status = map[raw] || 'pending';
  const orderReference = data?.order_reference || null;
  return {
    status,
    rawStatus: raw,
    reference: orderReference || reference,
    paymentReference: reference,
    order: orderReference ? {
      reference: orderReference,
      status: data.order_status || null,
      payment_status: data.order_payment_status || null,
      access_url: `/order-detail.html?reference=${encodeURIComponent(orderReference)}`,
      is_guest: guest,
    } : null,
    message: data?.failure_reason || '',
    amount: data?.amount ?? null,
    currency: 'NGN',
    paidAt: data?.verified_at || null,
  };
}

export const PAYMENT_COPY = {
  success: {
    tone: 'success', icon: 'check-circle', title: 'Payment confirmed',
    text: 'Your payment has been verified by our system and your order is confirmed. A receipt has been sent to your email address.',
  },
  pending: {
    tone: 'pending', icon: 'clock', title: 'Payment is still being verified',
    text: 'We have not yet received final confirmation for this transaction. Your order is held as pending. This page will keep checking, or you can return later with your reference.',
  },
  failed: {
    tone: 'danger', icon: 'alert-circle', title: 'Payment was not completed',
    text: 'This transaction was not successful. You have not been charged for a completed order. You can try again or choose a different payment method on Paystack.',
  },
  abandoned: {
    tone: 'danger', icon: 'alert-circle', title: 'Payment was cancelled',
    text: 'The payment window was closed before the transaction completed. Your order is still pending and your cart has not been charged.',
  },
  reversed: {
    tone: 'pending', icon: 'undo', title: 'Payment was reversed',
    text: 'This transaction was reversed. If you believe this is an error, contact customer support with your order reference.',
  },
  refunded: {
    tone: 'pending', icon: 'undo', title: 'Payment refunded',
    text: 'This transaction has been refunded. Refunds are returned to the original payment method by your bank.',
  },
  partially_refunded: {
    tone: 'pending', icon: 'undo', title: 'Payment partially refunded',
    text: 'Part of this transaction has been refunded. See your order details for the refunded amount.',
  },
};

/**
 * Start a fresh Paystack transaction for an order that is still awaiting
 * payment (POST /payments/paystack/initialize/). The backend refuses if the
 * order is already paid, cancelled or expired.
 */
export async function retryPayment(orderReference) {
  const payment = await initializePayment(orderReference);
  return { authorizationUrl: payment.authorizationUrl, reference: payment.reference };
}

export default { verifyPayment, pollVerification, redirectToPaystack, retryPayment };
