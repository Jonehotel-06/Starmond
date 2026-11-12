/** Order progress timeline shared by the tracking page and the order page. */
import { esc, formatDateTime } from '../utils.js';

export const FULFILMENT_STEPS = [
  { key: 'pending_payment', label: 'Order placed', hint: 'Waiting for payment confirmation' },
  { key: 'paid', label: 'Payment confirmed', hint: 'Payment verified by our payment provider' },
  { key: 'processing', label: 'Processing', hint: 'Being picked and packed' },
  { key: 'shipped', label: 'Shipped', hint: 'Handed to our delivery partner' },
  { key: 'delivered', label: 'Delivered', hint: 'Delivered to the address on the order' }
];

export function renderTimeline(el, status, history = []) {
  if (!el) return;
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'cancelled' || normalized === 'refunded' || normalized === 'payment_failed') {
    const label = normalized === 'cancelled' ? 'Order cancelled'
      : normalized === 'refunded' ? 'Order refunded' : 'Payment was not completed';
    el.innerHTML = `<li class="is-done">
      <span class="timeline__dot"><svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg></span>
      <div><p class="timeline__title">${label}</p>
        <p class="timeline__meta">Contact support if you need more detail on this order.</p></div>
    </li>`;
    return;
  }
  const index = FULFILMENT_STEPS.findIndex((step) => step.key === normalized);
  el.innerHTML = FULFILMENT_STEPS.map((step, i) => {
    const done = index >= 0 && i < index;
    const current = index >= 0 && i === index;
    const entry = (history || []).find((h) => String(h.status).toLowerCase() === step.key);
    const when = entry?.created_at ? formatDateTime(entry.created_at) : '';
    return `<li class="${done ? 'is-done' : ''}${current ? ' is-current' : ''}">
      <span class="timeline__dot">${done ? '<svg class="icon" aria-hidden="true"><use href="#i-check"></use></svg>' : ''}</span>
      <div>
        <p class="timeline__title">${esc(step.label)}${current ? ' <span class="pill pill--info">Current</span>' : ''}</p>
        <p class="timeline__meta">${esc(when || step.hint)}</p>
      </div>
    </li>`;
  }).join('');
}

export const STATUS_PILL = {
  pending_payment: { label: 'Awaiting payment', cls: 'pill--warn' },
  paid: { label: 'Paid', cls: 'pill--ok' },
  processing: { label: 'Processing', cls: 'pill--info' },
  shipped: { label: 'Shipped', cls: 'pill--info' },
  delivered: { label: 'Delivered', cls: 'pill--ok' },
  cancelled: { label: 'Cancelled', cls: 'pill--danger' },
  refunded: { label: 'Refunded', cls: 'pill--warn' },
  payment_failed: { label: 'Payment failed', cls: 'pill--danger' }
};

export function statusPill(status = '') {
  const meta = STATUS_PILL[String(status).toLowerCase()] || { label: status || 'Unknown', cls: '' };
  return `<span class="pill ${meta.cls}">${esc(meta.label)}</span>`;
}
