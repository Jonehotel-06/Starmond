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

const PAYSTACK_HOSTS = ['checkout.paystack.com', 'paystack.com', 'standard.paystack.co'];

/** Only redirect to a URL the backend gave us on a genuine Paystack host. */
export function isTrustedPaystackUrl(url) {
  try {
    const parsed = new URL(url);
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
 * Ask the backend to independently verify a transaction.
 * @param {string} reference
 * @returns {Promise<{status:string, order:object|null, payment:object|null, message:string}>}
 */
export async function verifyPayment(reference) {
  const data = await api.privateGet('/payments/verify/', { params: { reference } });
  return normalizeVerification(data);
}

/**
 * Poll verification while a transaction is pending, with capped backoff.
 * Never runs forever: after `maxAttempts` the UI shows the pending state.
 */
export async function pollVerification(reference, { maxAttempts = 5, onUpdate } = {}) {
  let attempt = 0;
  let result = null;
  while (attempt < maxAttempts) {
    result = await verifyPayment(reference);
    onUpdate?.(result, attempt + 1);
    if (result.status !== 'pending') return result;
    attempt += 1;
    if (attempt < maxAttempts) await new Promise((resolve) => setTimeout(resolve, Math.min(2000 * attempt, 8000)));
  }
  return result;
}

/**
 * Normalize the backend's payment status vocabulary into the seven states the
 * UI must present. Unknown values are treated as pending, never as success.
 */
export function normalizeVerification(data) {
  const payment = data?.payment || data || {};
  const raw = String(payment.status || data?.status || '').toLowerCase();
  const map = {
    success: 'success', successful: 'success', paid: 'success', completed: 'success',
    pending: 'pending', processing: 'pending', queued: 'pending', ongoing: 'pending', initiated: 'pending',
    failed: 'failed', failure: 'failed', declined: 'failed', error: 'failed',
    abandoned: 'abandoned', cancelled: 'abandoned', canceled: 'abandoned',
    reversed: 'reversed',
    refunded: 'refunded',
    partially_refunded: 'partially_refunded', 'partially-refunded': 'partially_refunded',
  };
  const status = map[raw] || 'pending';
  return {
    status,
    rawStatus: raw,
    order: data?.order || payment.order || null,
    payment,
    reference: payment.reference || data?.reference || null,
    message: data?.message || data?.detail || payment.gateway_response || '',
    amount: payment.amount ?? null,
    currency: payment.currency || 'NGN',
    paidAt: payment.paid_at || payment.paidAt || null,
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

/** Retry payment for an existing pending order. */
export async function retryPayment(orderReference) {
  const data = await api.post(`/orders/${encodeURIComponent(orderReference)}/retry-payment/`, {});
  return {
    authorizationUrl: data.payment?.authorization_url || data.authorization_url || null,
    reference: data.payment?.reference || data.reference || orderReference,
  };
}

export default { verifyPayment, pollVerification, redirectToPaystack, retryPayment };
