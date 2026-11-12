/** Order detail: payment status, fulfilment progress, items and actions. */
import { ready } from '../app.js';
import { orders, payments } from '../api.js';
import { session } from '../store.js';
import { toast, notifyError } from '../ui/toast.js';
import { confirmDialog } from '../ui/modal.js';
import { renderTimeline, statusPill } from '../ui/timeline.js';
import { esc, formatDate, formatDateTime, money, qs, setBusy, sitePath } from '../utils.js';

const el = {
  title: qs('[data-order-title]'),
  eyebrow: qs('[data-order-eyebrow]'),
  meta: qs('[data-order-meta]'),
  error: qs('[data-order-error]'),
  layout: qs('[data-order-layout]'),
  timeline: qs('[data-timeline]'),
  items: qs('[data-order-items]'),
  subtotal: qs('[data-order-subtotal]'),
  discountRow: qs('[data-order-discount-row]'),
  discount: qs('[data-order-discount]'),
  shipping: qs('[data-order-shipping]'),
  total: qs('[data-order-total]'),
  paymentStatus: qs('[data-order-payment-status]'),
  paymentNote: qs('[data-order-payment-note]'),
  reference: qs('[data-order-reference]'),
  address: qs('[data-order-address]'),
  shippingMethod: qs('[data-order-shipping-method]'),
  notes: qs('[data-order-notes]'),
  numberInline: qs('[data-order-number-inline]'),
  actions: qs('[data-order-actions]'),
  payNow: qs('[data-pay-now]'),
  cancel: qs('[data-cancel-order]')
};

let order = null;
const orderParam = new URLSearchParams(location.search).get('order')
  || new URLSearchParams(location.search).get('order_number')
  || new URLSearchParams(location.search).get('id');

function renderOrder(data) {
  order = data?.order || data;
  el.layout.removeAttribute('aria-busy');
  el.eyebrow.textContent = `Order ${order.order_number || ''}`;
  el.title.textContent = order.order_number ? `Order ${order.order_number}` : 'Your order';
  el.meta.textContent = [
    order.created_at ? `Placed ${formatDate(order.created_at)}` : '',
    order.item_count ? `${order.item_count} item${order.item_count === 1 ? '' : 's'}` : '',
    order.email || order.customer?.email || ''
  ].filter(Boolean).join(' · ');
  el.numberInline.textContent = order.order_number || '—';

  renderTimeline(el.timeline, order.status, order.status_history || order.history || []);

  const items = order.items || order.line_items || [];
  el.items.innerHTML = items.length ? items.map((item) => {
    const product = item.product || {};
    const name = product.name || item.name || 'Product';
    const slug = product.slug || item.slug;
    const img = item.image || product.primary_image;
    const imgUrl = typeof img === 'string' ? img : (img?.url || '');
    const variant = item.variant?.name
      || Object.entries(item.variant?.attributes || {}).map(([k, v]) => `${k}: ${v}`).join(' · ');
    return `<li class="mini-item">
      <span class="mini-item__media">${imgUrl ? `<img src="${esc(imgUrl)}" alt="" width="52" height="52" loading="lazy">` : ''}</span>
      <span>
        <span class="mini-item__name">${slug ? `<a href="${sitePath('product.html')}?slug=${encodeURIComponent(slug)}">${esc(name)}</a>` : esc(name)}</span>
        <span class="mini-item__meta">${variant ? `${esc(variant)} · ` : ''}Qty ${esc(item.quantity)} · ${money(item.unit_price ?? item.price)} each</span>
      </span>
      <span class="mini-item__price">${money(item.line_total ?? item.total ?? 0)}</span>
    </li>`;
  }).join('') : '<li class="mini-item">No items recorded on this order.</li>';

  const totals = order.totals || order;
  el.subtotal.textContent = money(totals.subtotal ?? 0);
  const discount = Number(totals.discount_total ?? 0);
  el.discountRow.hidden = !discount;
  if (discount) el.discount.textContent = `−${money(discount)}`;
  el.shipping.textContent = money(totals.shipping_total ?? totals.shipping ?? 0);
  el.total.textContent = money(totals.total ?? 0);

  const payment = order.payment || {};
  el.paymentStatus.innerHTML = statusPill(order.payment_status || payment.status || (order.paid ? 'paid' : 'pending_payment'));
  el.paymentNote.textContent = payment.gateway_response
    || (order.payment_status === 'paid'
      ? `Verified ${order.paid_at ? formatDateTime(order.paid_at) : 'with Paystack'}.`
      : 'Your order will be marked paid only after our server verifies the payment with Paystack.');
  el.reference.textContent = payment.reference || order.payment_reference ? `Reference: ${payment.reference || order.payment_reference}` : '';

  const addr = order.shipping_address || order.delivery_address || {};
  el.address.innerHTML = [
    [addr.first_name, addr.last_name].filter(Boolean).join(' '),
    addr.line1, addr.line2, addr.area, addr.city, addr.state, addr.postal_code,
    addr.phone || order.phone
  ].filter(Boolean).map((line) => esc(line)).join('<br>') || 'No delivery address recorded.';

  const method = order.shipping_method;
  el.shippingMethod.textContent = method
    ? `${method.name || method.label || 'Delivery'}${method.eta ? ` · ${method.eta}` : ''}`
    : '';
  if (order.delivery_notes) { el.notes.hidden = false; el.notes.textContent = `Delivery notes: ${order.delivery_notes}`; }

  /* Actions are permission-aware and state-aware, driven by backend flags. */
  el.actions.hidden = false;
  el.payNow.hidden = !(order.can_pay === true || String(order.status).toLowerCase() === 'pending_payment');
  el.cancel.hidden = !(order.can_cancel === true);
}

function showError(err) {
  el.layout.removeAttribute('aria-busy');
  el.layout.hidden = true;
  el.error.hidden = false;
  el.error.innerHTML = `<div>
    <p><strong>${err.status === 404 ? 'We could not find that order.' : 'This order could not be loaded.'}</strong></p>
    <p>${esc(err.message)}</p>
    <p><a href="${sitePath('account.html')}">Go to your account</a> · <a href="${sitePath('contact.html')}">Contact support</a></p>
  </div>`;
}

async function loadOrder() {
  if (!orderParam) { showError({ status: 404, message: 'No order was specified.' }); return; }
  try {
    const data = await orders.get(orderParam);
    renderOrder(data);
  } catch (err) {
    showError(err);
  }
}

el.payNow?.addEventListener('click', async (event) => {
  const btn = event.currentTarget;
  setBusy(btn, true);
  try {
    const init = await payments.initialize({ order_id: order.id });
    const url = init?.authorization_url || init?.checkout_url;
    if (!url) throw new Error('The payment provider did not return a payment link.');
    window.location.assign(url);
  } catch (err) {
    notifyError(err);
    setBusy(btn, false);
  }
});

el.cancel?.addEventListener('click', async () => {
  const confirmed = await confirmDialog({
    title: 'Cancel this order?',
    message: 'If you have already paid, cancellation is subject to a refund review. Stock will be released back to inventory.',
    confirmLabel: 'Cancel order',
    danger: true
  });
  if (!confirmed) return;
  setBusy(el.cancel, true);
  try {
    await orders.cancel(order.order_number || order.id);
    toast('Order cancelled.', { type: 'info' });
    await loadOrder();
  } catch (err) {
    notifyError(err);
  } finally {
    setBusy(el.cancel, false);
  }
});

async function init() {
  await ready;
  if (!session.isAuthenticated) {
    const next = location.pathname + location.search;
    el.layout.hidden = true;
    el.layout.removeAttribute('aria-busy');
    el.error.hidden = false;
    el.error.className = 'alert alert--info';
    el.error.innerHTML = `<div>
      <p><strong>Sign in to view this order.</strong></p>
      <p>Order details are private to the account that placed them.</p>
      <p><a class="btn btn--primary" href="${sitePath('login.html')}?next=${encodeURIComponent(next)}">Sign in</a>
         <a class="btn btn--outline" href="${sitePath('track-order.html')}">Track with order number</a></p>
    </div>`;
    return;
  }
  loadOrder();
}

init();
