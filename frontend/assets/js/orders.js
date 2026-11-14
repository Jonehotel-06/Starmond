/**
 * orders.js — order presentation shared by account, tracking and admin views.
 * Status vocabulary and lifecycle come from the backend; this module only maps
 * them to labels, colours and an accessible timeline.
 */

import api, { normalizeList } from './api.js';
import { esc, formatMoney, formatDate, formatDateTime } from './utils.js';
import { icon } from './icons.js';
import { renderProductLine } from './products.js';

export const LIFECYCLE = [
  ['pending_payment', 'Pending payment'],
  ['paid', 'Paid'],
  ['processing', 'Processing'],
  ['packed', 'Packed'],
  ['shipped', 'Shipped'],
  ['out_for_delivery', 'Out for delivery'],
  ['delivered', 'Delivered'],
  ['completed', 'Completed'],
];

const STATUS_TONE = {
  pending_payment: 'warning', paid: 'success', confirmed: 'success', processing: 'info',
  packed: 'info', shipped: 'info', out_for_delivery: 'info', delivered: 'success',
  completed: 'success', cancelled: 'danger', failed: 'danger', refunded: 'neutral',
  partially_refunded: 'warning', on_hold: 'warning', returned: 'neutral',
};

export function statusBadge(status, label = null) {
  const key = String(status || '').toLowerCase();
  const tone = STATUS_TONE[key] || 'neutral';
  const text = label || key.replace(/_/g, ' ') || 'unknown';
  return `<span class="badge badge--${tone} badge--dot">${esc(text)}</span>`;
}

export function listOrders(params = {}) {
  return api.privateGet('/orders/', { params }).then(normalizeList);
}

export function getOrder(reference, { token = null } = {}) {
  const path = token
    ? `/orders/guest/${encodeURIComponent(reference)}/`
    : `/orders/${encodeURIComponent(reference)}/`;
  return api.privateGet(path, { params: token ? { token } : undefined });
}

export function requestGuestAccess(payload) {
  return api.post('/orders/guest-access/', payload);
}

export function requestRefund(reference, payload) {
  return api.post(`/orders/${encodeURIComponent(reference)}/refund-requests/`, payload);
}

export function downloadReceipt(reference) {
  return api.download(`/orders/${encodeURIComponent(reference)}/receipt/`);
}

export function orderItems(order) {
  return order.items || order.lines || [];
}

export function orderTotal(order) {
  return order.total ?? order.totals?.total ?? null;
}

export function orderCurrency(order) {
  return order.currency || order.totals?.currency || 'NGN';
}

export function renderOrderCard(order) {
  const items = orderItems(order);
  const reference = order.reference || order.order_number || order.id;
  const detailUrl = order.access_url || `/order-detail.html?ref=${encodeURIComponent(reference)}`;
  return `<article class="order-card">
    <div class="order-card__head">
      <div class="stack stack--xs">
        <span class="order-card__ref">${esc(reference)}</span>
        <span class="t-meta">Placed ${esc(formatDate(order.created_at))}</span>
      </div>
      <div class="cluster cluster--sm">
        ${statusBadge(order.payment_status || 'pending_payment', order.payment_status_label)}
        ${statusBadge(order.fulfilment_status || order.status, order.fulfilment_status_label)}
      </div>
    </div>
    <div class="order-card__body">
      ${items.slice(0, 3).map((item) => renderProductLine({
        product: item.product || item,
        variation: item.variation,
        quantity: item.quantity,
        unitPrice: item.unit_price,
        lineTotal: item.line_total,
        currency: orderCurrency(order),
      })).join('')}
      ${items.length > 3 ? `<p class="t-meta">and ${items.length - 3} more item${items.length - 3 === 1 ? '' : 's'}</p>` : ''}
    </div>
    <div class="order-card__foot">
      <span class="price price--md">${orderTotal(order) != null ? esc(formatMoney(orderTotal(order), orderCurrency(order))) : '—'}</span>
      <div class="cluster cluster--sm">
        <a class="btn btn--secondary btn--sm" href="${esc(detailUrl)}">View details</a>
        ${order.tracking_number ? `<span class="t-meta">Tracking: ${esc(order.tracking_number)}</span>` : ''}
      </div>
    </div>
  </article>`;
}

/** Vertical timeline built from backend events, falling back to the lifecycle. */
export function renderTimeline(order) {
  const events = order.timeline || order.events || order.status_history || [];
  if (events.length) {
    return `<ol class="order-timeline">${events.map((event, index) => {
      const isLast = index === events.length - 1;
      return `<li class="timeline-item ${isLast ? 'is-current' : 'is-done'}">
        <span class="timeline-item__dot">${icon(isLast ? 'clock' : 'check', { size: 'sm' })}</span>
        <span>
          <span class="timeline-item__title">${esc(event.label || String(event.status || '').replace(/_/g, ' '))}</span>
          <span class="timeline-item__time">${esc(formatDateTime(event.created_at || event.timestamp))}</span>
          ${event.note ? `<span class="timeline-item__note">${esc(event.note)}</span>` : ''}
        </span>
      </li>`;
    }).join('')}</ol>`;
  }

  const current = String(order.fulfilment_status || order.status || '').toLowerCase();
  const paid = ['paid', 'success', 'successful'].includes(String(order.payment_status || '').toLowerCase());
  const currentIndex = LIFECYCLE.findIndex(([key]) => key === current);
  const cancelled = ['cancelled', 'failed', 'refunded'].includes(current);

  if (cancelled) {
    return `<div class="alert alert--warning"><span class="alert__icon">${icon('alert-circle')}</span>
      <div class="alert__body"><span class="alert__title">This order is ${esc(current.replace(/_/g, ' '))}</span>
      <span>Contact customer support if you need help with this order.</span></div></div>`;
  }

  return `<ol class="order-timeline">${LIFECYCLE.map(([key, label], index) => {
    const reached = index === 0 ? paid || currentIndex >= 0 : currentIndex >= index;
    const isCurrent = currentIndex === index || (index === 0 && !paid && currentIndex < 0);
    return `<li class="timeline-item ${reached && !isCurrent ? 'is-done' : ''} ${isCurrent ? 'is-current' : ''}">
      <span class="timeline-item__dot">${reached && !isCurrent ? icon('check', { size: 'sm' }) : ''}</span>
      <span><span class="timeline-item__title">${esc(label)}</span></span>
    </li>`;
  }).join('')}</ol>`;
}

export function renderOrderDetail(order, { guest = false } = {}) {
  const items = orderItems(order);
  const currency = orderCurrency(order);
  const totals = order.totals || {};
  const reference = order.reference || order.order_number || order.id;
  const delivery = order.delivery || order.shipping_address || {};
  const canRefund = order.refund_eligible === true
    || (['delivered', 'completed'].includes(String(order.fulfilment_status || '').toLowerCase()) && order.refund_requested !== true);

  const row = (label, value, cls = '') => `<div class="summary-row ${cls}"><span class="summary-row__label">${esc(label)}</span><span class="summary-row__value">${value}</span></div>`;
  const money = (value) => (value != null ? esc(formatMoney(value, currency)) : '—');

  return `<div class="stack stack--lg">
    <div class="card">
      <div class="card__head">
        <div class="stack stack--xs">
          <span class="order-card__ref">${esc(reference)}</span>
          <span class="t-meta">Placed ${esc(formatDateTime(order.created_at))}</span>
        </div>
        <div class="cluster cluster--sm">
          ${statusBadge(order.payment_status, order.payment_status_label)}
          ${statusBadge(order.fulfilment_status || order.status, order.fulfilment_status_label)}
        </div>
      </div>
      <div class="card__body">
        <div class="order-meta-grid">
          <div><span class="order-meta__label">Payment</span><span class="order-meta__value">${esc(order.payment_method || 'Paystack')}</span></div>
          <div><span class="order-meta__label">Delivery method</span><span class="order-meta__value">${esc(delivery.method_name || delivery.method || '—')}</span></div>
          <div><span class="order-meta__label">Items</span><span class="order-meta__value">${items.length}</span></div>
          <div><span class="order-meta__label">Total</span><span class="order-meta__value price">${money(orderTotal(order))}</span></div>
          ${order.tracking_number ? `<div><span class="order-meta__label">Tracking number</span><span class="order-meta__value">${esc(order.tracking_number)}</span></div>` : ''}
          ${order.estimated_delivery ? `<div><span class="order-meta__label">Estimated delivery</span><span class="order-meta__value">${esc(formatDate(order.estimated_delivery))}</span></div>` : ''}
        </div>
      </div>
      <div class="card__foot cluster cluster--between">
        <div class="cluster cluster--sm">
          <button type="button" class="btn btn--secondary btn--sm" data-download-receipt="${esc(reference)}">${icon('download', { size: 'sm' })} Receipt</button>
          ${canRefund ? `<button type="button" class="btn btn--ghost btn--sm" data-request-refund="${esc(reference)}">${icon('undo', { size: 'sm' })} Request refund</button>` : ''}
          ${order.refund_requested ? '<span class="badge badge--warning">Refund requested</span>' : ''}
        </div>
        ${String(order.payment_status).toLowerCase() === 'pending_payment' && !guest
          ? `<button type="button" class="btn btn--primary btn--sm" data-retry-payment="${esc(reference)}">Complete payment</button>` : ''}
      </div>
    </div>

    <div class="admin-grid-2-1">
      <div class="card">
        <div class="card__head"><h2 class="card__title">Items in this order</h2></div>
        <div class="card__body">
          ${items.map((item) => renderProductLine({
            product: item.product || item,
            variation: item.variation,
            quantity: item.quantity,
            unitPrice: item.unit_price,
            lineTotal: item.line_total,
            currency,
          })).join('')}
          <hr class="divider" style="margin-block:var(--space-4)">
          <div class="summary-rows">
            ${row('Subtotal', money(totals.subtotal ?? order.subtotal))}
            ${Number(totals.discount_total ?? order.discount_total) > 0 ? row('Discount', `−${money(totals.discount_total ?? order.discount_total)}`, 'summary-row--discount') : ''}
            ${row('Delivery', money(totals.shipping_total ?? order.shipping_total))}
            ${Number(totals.tax_total ?? order.tax_total) > 0 ? row('Tax', money(totals.tax_total ?? order.tax_total)) : ''}
            ${row('Total', money(orderTotal(order)), 'summary-row--total')}
            ${Number(order.refunded_amount) > 0 ? row('Refunded', `−${money(order.refunded_amount)}`, 'summary-row--discount') : ''}
          </div>
        </div>
      </div>

      <div class="stack stack--lg">
        <div class="card">
          <div class="card__head"><h2 class="card__title">Order progress</h2></div>
          <div class="card__body">${renderTimeline(order)}</div>
        </div>
        <div class="card">
          <div class="card__head"><h2 class="card__title">Delivery details</h2></div>
          <div class="card__body stack stack--sm">
            <p class="t-sm t-semibold">${esc(order.customer?.full_name || delivery.full_name || '')}</p>
            <p class="t-sm t-muted">
              ${esc(delivery.address_line1 || '')}${delivery.address_line2 ? `<br>${esc(delivery.address_line2)}` : ''}
              <br>${esc([delivery.city, delivery.state].filter(Boolean).join(', '))}
            </p>
            ${order.customer?.phone ? `<p class="t-sm t-muted">${esc(order.customer.phone)}</p>` : ''}
            ${delivery.instructions ? `<p class="t-xs t-muted"><strong>Instructions:</strong> ${esc(delivery.instructions)}</p>` : ''}
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

export default { listOrders, getOrder, renderOrderCard, renderOrderDetail, statusBadge };
