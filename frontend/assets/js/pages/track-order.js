/** Public order tracking: order number + email, both verified by the backend. */
import { ready } from '../app.js';
import { orders } from '../api.js';
import { clearErrors, fieldError, formatDate, qs, sitePath, setBusy, validate } from '../utils.js';
import { renderTimeline } from '../ui/timeline.js';

const form = qs('[data-track-form]');
const errorEl = qs('[data-track-error]');
const result = qs('[data-track-result]');
const resultTitle = qs('[data-track-result-title]');
const resultMeta = qs('[data-track-result-meta]');
const timeline = qs('[data-track-timeline]');

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearErrors(form);
  if (errorEl) errorEl.hidden = true;
  result.hidden = true;

  const data = new FormData(form);
  const orderNumber = String(data.get('order_number') || '').trim();
  const email = String(data.get('email') || '').trim();
  let valid = true;
  const numErr = validate.required(orderNumber, 'Order number');
  if (numErr) { fieldError(form, 'order_number', numErr); valid = false; }
  const emailErr = validate.email(email);
  if (emailErr) { fieldError(form, 'email', emailErr); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true);
  try {
    const data2 = await orders.track({ order_number: orderNumber, email });
    const order = data2?.order || data2;
    result.hidden = false;
    resultTitle.textContent = `Order ${order.order_number || orderNumber}`;
    resultMeta.textContent = [
      order.status_display || order.status,
      order.created_at ? `Placed ${formatDate(order.created_at)}` : '',
      order.total !== undefined ? `Total ${order.currency || 'NGN'} ${order.total}` : ''
    ].filter(Boolean).join(' · ');
    renderTimeline(timeline, order.status, order.status_history || order.history || []);
    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    if (errorEl) {
      errorEl.textContent = err.status === 404
        ? 'No order matches that order number and email address. Check both and try again.'
        : err.message;
      errorEl.hidden = false;
    }
  } finally {
    setBusy(button, false);
  }
});

/* Pre-fill the order number when arriving from a link. */
const prefilled = new URLSearchParams(location.search).get('order');
if (prefilled) {
  const input = form?.querySelector('[name="order_number"]');
  if (input) input.value = prefilled;
}

ready.then(() => {
  const signedIn = window.starmond?.session?.isAuthenticated;
  if (signedIn) {
    const note = document.createElement('p');
    note.className = 'small muted';
    note.innerHTML = `Signed in? <a href="${sitePath('account.html')}#orders">See all your orders in your account</a>.`;
    form?.appendChild(note);
  }
});
