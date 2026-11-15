/**
 * orders.js — order presentation shared by account, tracking and admin views.
 * Status vocabulary and lifecycle come from the backend; this module only maps
 * them to labels, colours and an accessible timeline.
 */

import api, { normalizeList } from './api.js';
import { esc, formatMoney, formatDate, formatDateTime } from './utils.js';
import { icon } from './icons.js';
import { renderProductLine } from './products.js';
import { getOrderAccess, rememberOrderAccess } from './checkout.js';

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
  completed: 'success', cancelled: 'danger', failed: 'danger', payment_failed: 'danger', expired: 'neutral',
  refunded: 'neutral', partially_refunded: 'warning', refund_requested: 'warning', pending: 'warning',
  successful: 'success', initialized: 'warning', abandoned: 'neutral', approved: 'success', rejected: 'danger', requested: 'warning',
};

export function statusBadge(status, label = null) {
  const key = String(status || '').toLowerCase();
  const tone = STATUS_TONE[key] || 'neutral';
  const text = label || key.replace(/_/g, ' ') || 'unknown';
  return `<span class="badge badge--${tone} badge--dot">${esc(text)}</span>`;
}

/* ============================================================================
   Data — backend contract (apps/orders, apps/refunds)
     GET  /orders/?status=&page=          signed-in customer's orders (summaries)
     GET  /orders/<reference>/?token=     owner, or a guest holding the access token
     POST /orders/<reference>/            cancel an order that is still awaiting payment
     POST /orders/lookup/ {reference,email}  guest lookup → access token
     POST /refunds/requests/ {order_reference, reason, amount?}
   ========================================================================== */

/** Map the backend order (summary or detail) onto the shape the renderers use. */
export function normalizeOrder(raw) {
  if (!raw || typeof raw !== 'object' || raw._normalized) return raw;
  const totals = raw.totals || {};
  const delivery = raw.delivery || {};
  const items = (raw.items || []).map((item) => ({
    id: item.id,
    quantity: item.quantity,
    unit_price: item.unit_price,
    line_total: item.line_total,
    customization: item.customization || null,
    product: {
      id: item.product,
      name: item.product_name,
      slug: item.product_slug || null,
      sku: item.sku,
      url: item.product_slug ? `/products/${item.product_slug}/` : '/shop.html',
    },
    variation: item.variation_label || null,
  }));
  return {
    ...raw,
    _normalized: true,
    items,
    item_count: raw.item_count ?? items.reduce((sum, i) => sum + (Number(i.quantity) || 0), 0),
    created_at: raw.placed_at || raw.created_at || null,
    fulfilment_status: raw.status,
    tracking_number: delivery.tracking_reference || raw.tracking_reference || null,
    estimated_delivery: delivery.estimate || null,
    total: totals.total ?? raw.total_amount ?? raw.total ?? null,
    currency: raw.currency || totals.currency || 'NGN',
    refunded_amount: totals.refunded ?? null,
    totals: {
      subtotal: totals.subtotal ?? null,
      discount_total: totals.discount ?? null,
      shipping_total: totals.shipping_fee ?? null,
      total: totals.total ?? raw.total_amount ?? null,
      currency: totals.currency || raw.currency || 'NGN',
    },
    customer: raw.contact || null,
    delivery: {
      ...delivery,
      method_name: delivery.method || raw.shipping_method_name || '',
      address_line1: delivery.street || '',
      address_line2: delivery.details || '',
    },
    refund_requested: raw.status === 'refund_requested',
  };
}

export function listOrders(params = {}) {
  return api.privateGet('/orders/', { params }).then((data) => {
    const list = normalizeList(data);
    return { ...list, results: list.results.map(normalizeOrder) };
  });
}

/**
 * Signed-in owners need no token. Guests use the access token the backend
 * issued at checkout or through the order lookup (kept in sessionStorage).
 */
export function getOrder(reference, { token = null } = {}) {
  const access = token || getOrderAccess(reference);
  return api.privateGet(`/orders/${encodeURIComponent(reference)}/`, { params: access ? { token: access } : undefined })
    .then(normalizeOrder);
}

/** Guest lookup: reference + checkout email → access token (stored for this tab). */
export async function requestGuestAccess({ reference, email }) {
  const data = await api.post('/orders/lookup/', { reference, email });
  const ref = data?.summary?.reference || String(reference).toUpperCase();
  if (data?.token) rememberOrderAccess(ref, data.token);
  return { reference: ref, summary: data?.summary ? normalizeOrder(data.summary) : null };
}

/** Cancel an order that has not been paid for. Stock reservations are released. */
export function cancelOrder(reference) {
  const token = getOrderAccess(reference);
  return api.post(`/orders/${encodeURIComponent(reference)}/`, token ? { token } : {});
}

/** Signed-in customers only. Reviewed by staff before any money moves. */
export function requestRefund(reference, { reason, details = '' }) {
  const text = [reason, details].filter(Boolean).join(' — ');
  return api.post('/refunds/requests/', { order_reference: reference, reason: text });
}

export function listRefunds() {
  return api.privateGet('/refunds/requests/').then(normalizeList);
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
  const detailUrl = `/order-detail.html?reference=${encodeURIComponent(reference)}`;
  return `<article class="order-card">
    <div class="order-card__head">
      <div class="stack stack--xs">
        <span class="order-card__ref">${esc(reference)}</span>
        <span class="t-meta">Placed ${esc(formatDate(order.created_at))}</span>
      </div>
      <div class="cluster cluster--sm">
        ${statusBadge(order.payment_status || 'pending', `Payment: ${String(order.payment_status || 'pending').replace(/_/g, ' ')}`)}
        ${statusBadge(order.status)}
      </div>
    </div>
    <div class="order-card__body">
      ${items.length ? items.slice(0, 3).map((item) => renderProductLine({
        product: item.product || item,
        variation: item.variation,
        quantity: item.quantity,
        unitPrice: item.unit_price,
        lineTotal: item.line_total,
        currency: orderCurrency(order),
      })).join('') : `<p class="t-sm t-muted">${esc(order.item_count || 0)} item${Number(order.item_count) === 1 ? '' : 's'}${order.shipping_method_name ? ` · ${esc(order.shipping_method_name)}` : ''}</p>`}
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
  const paid = ['paid', 'partially_refunded'].includes(String(order.payment_status || '').toLowerCase());
  const currentIndex = LIFECYCLE.findIndex(([key]) => key === current);
  const cancelled = ['cancelled', 'payment_failed', 'expired', 'refunded', 'refund_requested', 'partially_refunded'].includes(current);

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

export function renderOrderDetail(order, { guest = false, staff = false } = {}) {
  const items = orderItems(order);
  const currency = orderCurrency(order);
  const totals = order.totals || {};
  const reference = order.reference || order.order_number || order.id;
  const delivery = order.delivery || order.shipping_address || {};
  const status = String(order.status || '').toLowerCase();
  const awaitingPayment = status === 'pending_payment';
  // Refund requests need an account (POST /refunds/requests/) and a paid order.
  const canRefund = !guest && !staff && String(order.payment_status).toLowerCase() === 'paid'
    && !['refund_requested', 'refunded', 'cancelled'].includes(status);

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
          ${statusBadge(order.payment_status, `Payment: ${String(order.payment_status || 'pending').replace(/_/g, ' ')}`)}
          ${statusBadge(order.status)}
        </div>
      </div>
      <div class="card__body">
        <div class="order-meta-grid">
          <div><span class="order-meta__label">Payment</span><span class="order-meta__value">Paystack${order.paid_at ? ` · paid ${esc(formatDateTime(order.paid_at))}` : ''}</span></div>
          <div><span class="order-meta__label">Delivery method</span><span class="order-meta__value">${esc(delivery.method_name || delivery.method || '—')}</span></div>
          <div><span class="order-meta__label">Items</span><span class="order-meta__value">${esc(order.item_count ?? items.length)}</span></div>
          <div><span class="order-meta__label">Total</span><span class="order-meta__value price">${money(orderTotal(order))}</span></div>
          ${order.tracking_number ? `<div><span class="order-meta__label">Tracking number</span><span class="order-meta__value">${esc(order.tracking_number)}</span></div>` : ''}
          ${order.estimated_delivery ? `<div><span class="order-meta__label">Estimated delivery</span><span class="order-meta__value">${esc(order.estimated_delivery)}</span></div>` : ''}
        </div>
      </div>
      <div class="card__foot cluster cluster--between" ${staff ? 'hidden' : ''}>
        <div class="cluster cluster--sm">
          <button type="button" class="btn btn--secondary btn--sm" data-print-order>${icon('download', { size: 'sm' })} Print / save</button>
          ${canRefund ? `<button type="button" class="btn btn--ghost btn--sm" data-request-refund="${esc(reference)}">${icon('undo', { size: 'sm' })} Request refund</button>` : ''}
          ${order.refund_requested ? '<span class="badge badge--warning">Refund requested</span>' : ''}
        </div>
        ${awaitingPayment && !staff
          ? `<div class="cluster cluster--sm">
               <button type="button" class="btn btn--ghost btn--sm" data-cancel-order="${esc(reference)}">Cancel order</button>
               <button type="button" class="btn btn--primary btn--sm" data-retry-payment="${esc(reference)}">Complete payment</button>
             </div>` : ''}
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

export default { listOrders, getOrder, cancelOrder, requestRefund, renderOrderCard, renderOrderDetail, statusBadge, normalizeOrder };
