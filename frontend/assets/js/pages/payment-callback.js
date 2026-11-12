/**
 * Paystack return page.
 *
 * The frontend NEVER decides that a payment succeeded. It sends the reference to
 * the backend, which verifies it with Paystack, and renders whatever status the
 * backend reports.
 */
import { ready } from '../app.js';
import { payments } from '../api.js';
import { qs, sitePath, money, formatDateTime } from '../utils.js';
import { toast } from '../ui/toast.js';

const title = qs('[data-callback-title]');
const message = qs('[data-callback-message]');
const refEl = qs('[data-callback-reference]');
const spinner = qs('[data-callback-spinner]');
const actions = qs('[data-callback-actions]');
const note = qs('[data-callback-note]');
const primary = qs('[data-callback-primary]');

function show({ heading, text, reference, ok, extra }) {
  if (spinner) spinner.hidden = true;
  if (title) title.textContent = heading;
  if (message) message.textContent = text;
  if (refEl) refEl.textContent = reference ? `Payment reference: ${reference}` : '';
  if (actions) actions.hidden = false;
  if (note && extra) { note.hidden = false; note.textContent = extra; }
  if (primary) {
    primary.href = ok !== false ? sitePath('account.html') : sitePath('cart.html');
    primary.textContent = ok !== false ? 'View your orders' : 'Return to your cart';
  }
}

async function verify(reference) {
  let attempts = 0;
  const maxAttempts = 3;
  while (attempts < maxAttempts) {
    attempts += 1;
    try {
      const data = await payments.verify(reference);
      const status = String(data?.status || data?.payment_status || '').toLowerCase();
      const paid = ['paid', 'success', 'successful', 'completed', 'verified', 'charge.success'].includes(status);
      const pending = ['pending', 'processing', 'initialized', 'ongoing', ''].includes(status);
      const orderNumber = data?.order_number || data?.order?.order_number || '';
      const amount = data?.amount ?? data?.order?.total;
      const orderLink = data?.order_id || orderNumber
        ? `${sitePath('order.html')}?order=${encodeURIComponent(orderNumber || data?.order_id)}`
        : sitePath('account.html');

      if (paid) {
        if (primary) primary.href = orderLink;
        show({
          heading: 'Payment confirmed',
          text: `We verified your payment${amount !== undefined ? ` of ${money(amount)}` : ''}. Your order is confirmed and will move to processing${orderNumber ? ` — order ${orderNumber}` : ''}.`,
          reference,
          ok: true,
          extra: data?.paid_at ? `Verified ${formatDateTime(data.paid_at)}.` : ''
        });
        if (orderNumber) sessionStorage.removeItem('starmond_last_payment');
        return;
      }
      if (pending && attempts < maxAttempts) {
        if (message) message.textContent = `Still confirming with the payment provider… (attempt ${attempts} of ${maxAttempts})`;
        await new Promise((r) => setTimeout(r, 2500));
        continue;
      }
      show({
        heading: 'Payment not confirmed',
        text: data?.gateway_response || data?.detail || 'The payment provider has not confirmed this payment. If you were debited, contact us with the reference below and your order number — no payment is ever marked as successful by this page.',
        reference,
        ok: false
      });
      return;
    } catch (err) {
      if (attempts >= maxAttempts) {
        show({
          heading: 'We could not confirm the payment',
          text: `${err.message} If you were debited, contact support with the reference below so we can check it against our payment records.`,
          reference,
          ok: false
        });
        toast('Payment verification failed. Please contact support if you were debited.', { type: 'error', timeout: 9000 });
        return;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

async function init() {
  await ready;
  const params = new URLSearchParams(location.search);
  const reference = params.get('reference') || params.get('trxref') || '';
  if (!reference) {
    show({
      heading: 'No payment reference found',
      text: 'This page is shown after a Paystack payment and needs the payment reference. Open your order to see its status.',
      ok: false
    });
    return;
  }
  if (refEl) refEl.textContent = `Payment reference: ${reference}`;
  verify(reference);
}

init();
