/**
 * payment-result.js — Paystack return handling.
 *
 * The redirect back from Paystack carries a reference. That reference proves
 * nothing on its own: this page always asks the backend to verify the
 * transaction and renders only the backend's verdict.
 *
 * Duplicate returns are safe: verification is idempotent and the page guards
 * against re-entrancy.
 */

import boot from '../boot.js';
import { pollVerification, PAYMENT_COPY, retryPayment, redirectToPaystack } from '../payments.js';
import { clearBuyNowIntent } from '../cart.js';
import { resolveRegion, emptyState, toast, announce, openDialog } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, formatDateTime, createStorage } from '../utils.js';
import { verifyPayment } from '../payments.js';

await boot();

const processed = createStorage('session');
let inFlight = false;

function referenceFromUrl() {
  const params = new URLSearchParams(location.search);
  return params.get('reference') || params.get('trxref') || params.get('order') || '';
}

function renderMissingReference() {
  resolveRegion($('[data-payment-region]'), emptyState({
    title: 'No payment reference found',
    text: 'This page needs the payment reference from Paystack. If you completed a payment, check your email for the order reference, or contact customer support.',
    iconName: 'alert-circle',
    actionHtml: '<a class="btn btn--primary btn--sm" href="/orders.html">View my orders</a><a class="btn btn--secondary btn--sm" href="/contact.html">Contact support</a>',
  }));
  document.title = 'Payment reference missing — Starmond Technology Limited';
}

function renderResult(result, { polling = false } = {}) {
  const copy = PAYMENT_COPY[result.status] || PAYMENT_COPY.pending;
  const order = result.order || {};
  const reference = result.reference || order.reference || referenceFromUrl();
  const amount = result.amount ?? order.total ?? null;

  document.title = `${copy.title} — Starmond Technology Limited`;

  const details = `
    <div class="panel result-card__details">
      <div class="summary-row"><span class="summary-row__label">Order reference</span>
        <span class="result-ref">${esc(reference)}
          <button type="button" class="row-action" data-copy-ref aria-label="Copy order reference">${icon('copy', { size: 'sm' })}</button>
        </span>
      </div>
      ${order.order_number ? `<div class="summary-row"><span class="summary-row__label">Order number</span><span class="summary-row__value">${esc(order.order_number)}</span></div>` : ''}
      ${amount != null ? `<div class="summary-row"><span class="summary-row__label">Amount</span><span class="summary-row__value">${esc(formatMoney(amount, result.currency))}</span></div>` : ''}
      ${result.paidAt ? `<div class="summary-row"><span class="summary-row__label">Paid at</span><span class="summary-row__value">${esc(formatDateTime(result.paidAt))}</span></div>` : ''}
      ${order.fulfilment_status || order.status ? `<div class="summary-row"><span class="summary-row__label">Order status</span><span class="summary-row__value"><span class="badge badge--primary">${esc(String(order.fulfilment_status || order.status).replace(/_/g, ' '))}</span></span></div>` : ''}
      ${order.email ? `<div class="summary-row"><span class="summary-row__label">Receipt sent to</span><span class="summary-row__value">${esc(order.email)}</span></div>` : ''}
    </div>`;

  const actions = [];
  if (result.status === 'success') {
    if (order.access_url) actions.push(`<a class="btn btn--primary" href="${esc(order.access_url)}">View order details</a>`);
    else actions.push('<a class="btn btn--primary" href="/orders.html">View my orders</a>');
    actions.push('<a class="btn btn--secondary" href="/shop.html">Continue shopping</a>');
  } else if (['failed', 'abandoned'].includes(result.status)) {
    actions.push(`<button type="button" class="btn btn--primary" data-retry-payment="${esc(reference)}">Try payment again</button>`);
    actions.push('<a class="btn btn--secondary" href="/cart.html">Return to cart</a>');
    actions.push('<a class="btn btn--ghost" href="/contact.html">Contact support</a>');
  } else {
    actions.push(`<button type="button" class="btn btn--primary" data-recheck="${esc(reference)}">${icon('refresh', { size: 'sm' })} Check again</button>`);
    actions.push('<a class="btn btn--secondary" href="/orders.html">View my orders</a>');
    actions.push('<a class="btn btn--ghost" href="/contact.html">Contact support</a>');
  }

  const guestNote = order.access_url
    ? ''
    : `<p class="summary-note">Checked out as a guest? Keep this reference. You can also use <a href="/track-order.html">Track an order</a> to receive a secure access link by email.</p>`;

  const createAccount = result.status === 'success' && !order.customer_has_account
    ? `<div class="panel stack stack--sm" style="text-align:left">
        <p class="t-sm t-semibold">Want to track this order more easily?</p>
        <p class="t-sm t-muted">Create an account with ${esc(order.email || 'the email you used')} to see all your orders, receipts and delivery updates in one place.</p>
        <div><a class="btn btn--secondary btn--sm" href="/register.html${order.email ? `?email=${encodeURIComponent(order.email)}` : ''}">Create an account</a></div>
      </div>`
    : '';

  resolveRegion($('[data-payment-region]'), `
    <div class="stack stack--lg">
      <span class="result-card__icon result-card__icon--${copy.tone}">${icon(copy.icon, { size: 'xl' })}</span>
      <div class="stack stack--sm">
        <h1 class="result-card__title">${esc(copy.title)}</h1>
        <p class="result-card__text">${esc(copy.text)}</p>
        ${result.message && result.status !== 'success' ? `<p class="t-sm t-muted">${esc(result.message)}</p>` : ''}
        ${polling ? '<p class="t-xs t-muted" role="status">Still checking with the payment provider…</p>' : ''}
      </div>
      ${details}
      <div class="result-card__actions">${actions.join('')}</div>
      ${guestNote}
      ${createAccount}
    </div>
  `);

  announce(`${copy.title}. ${copy.text}`, { assertive: result.status !== 'success' });

  $('[data-copy-ref]')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(reference); toast('Reference copied.', { type: 'success' }); }
    catch { toast('Copy the reference manually.', { type: 'info' }); }
  });

  $('[data-recheck]')?.addEventListener('click', () => run({ manual: true }));

  $('[data-retry-payment]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    const original = button.innerHTML;
    button.innerHTML = '<span class="btn__pending">Preparing</span>';
    try {
      const retry = await retryPayment(button.dataset.retryPayment);
      redirectToPaystack(retry.authorizationUrl);
    } catch (error) {
      toast(error?.userMessage || 'Could not restart payment. Please contact support.', { type: 'danger' });
      button.disabled = false;
      button.innerHTML = original;
    }
  });
}

async function run({ manual = false } = {}) {
  if (inFlight) return;
  const reference = referenceFromUrl();
  if (!reference) { renderMissingReference(); return; }

  inFlight = true;
  const region = $('[data-payment-region]');
  if (manual) {
    region.setAttribute('aria-busy', 'true');
    announce('Checking your payment status again.');
  }

  try {
    const result = await pollVerification(reference, {
      maxAttempts: manual ? 1 : 4,
      onUpdate: (partial, attempt) => {
        if (partial.status === 'pending' && attempt > 1) renderResult(partial, { polling: true });
      },
    });
    renderResult(result);
    // A verified successful direct purchase can release its intent safely.
    if (result.status === 'success') {
      clearBuyNowIntent();
      processed.set(`verified:${reference}`, { status: result.status, at: Date.now() });
      window.dispatchEvent(new CustomEvent('starmond:cart-changed', { detail: { reason: 'order-paid' } }));
    }
  } catch (error) {
    if (error.isNotFound) {
      resolveRegion(region, emptyState({
        title: 'We could not find that payment reference',
        text: 'The reference is not recognised by our system. If money left your account, contact customer support with the reference below and we will investigate.',
        iconName: 'alert-circle',
        actionHtml: `<a class="btn btn--primary btn--sm" href="/contact.html">Contact support</a><a class="btn btn--secondary btn--sm" href="/orders.html">My orders</a>`,
      }));
      announce('Payment reference not recognised.', { assertive: true });
      return;
    }
    resolveRegion(region, `<div class="stack stack--lg">
      <span class="result-card__icon result-card__icon--pending">${icon('wifi-off', { size: 'xl' })}</span>
      <div class="stack stack--sm">
        <h1 class="result-card__title">We could not verify your payment yet</h1>
        <p class="result-card__text">${esc(error.userMessage || 'The verification service is unreachable. This does not mean your payment failed — it means we cannot confirm it right now.')}</p>
        <p class="result-ref">${esc(reference)}</p>
      </div>
      <div class="result-card__actions">
        <button type="button" class="btn btn--primary" data-recheck="${esc(reference)}">Try verification again</button>
        <a class="btn btn--secondary" href="/contact.html">Contact support</a>
      </div>
      <p class="summary-note">Never assume a payment succeeded because the browser returned to this page. Only a verified result from our system confirms an order.</p>
    </div>`);
    $('[data-recheck]')?.addEventListener('click', () => run({ manual: true }));
  } finally {
    inFlight = false;
  }
}

run();
