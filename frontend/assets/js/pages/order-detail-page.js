/**
 * order-detail-page.js — a single order, for signed-in customers or via an
 * expiring signed guest link (?ref=...&token=...). Sequential IDs are never
 * used to look up private order data.
 */
import boot from '../boot.js';
import { getOrder, renderOrderDetail, cancelOrder, requestRefund } from '../orders.js';
import { retryPayment, redirectToPaystack } from '../payments.js';
import { initAuth, isAuthenticated } from '../auth.js';
import { getOrderAccess } from '../checkout.js';
import {
  resolveRegion, renderRegionError, emptyState, toast, openDialog, confirmDialog, withSubmit, formData, skeletons,
} from '../ui.js';
import { hydrateIcons } from '../icons.js';
import { esc, $, readQuery } from '../utils.js';

await boot();
await initAuth();

const params = readQuery();
const reference = params.ref || params.reference || '';
// Guest access tokens live in sessionStorage (set at checkout / order lookup).
// A ?token= in the URL is still honoured for links opened in a new tab.
const token = params.token || getOrderAccess(reference) || '';

async function load() {
  const region = $('[data-order-detail]');
  if (!reference) {
    resolveRegion(region, emptyState({
      title: 'No order reference provided',
      text: 'Open an order from your order history, or use the secure link we emailed you.',
      iconName: 'receipt',
      actionHtml: '<a class="btn btn--primary btn--sm" href="/orders.html">My orders</a><a class="btn btn--secondary btn--sm" href="/track-order.html">Track an order</a>',
    }));
    return;
  }
  if (!token && !isAuthenticated()) {
    window.location.assign(`/login.html?next=${encodeURIComponent(location.pathname + location.search)}`);
    return;
  }
  region.setAttribute('aria-busy', 'true');
  region.innerHTML = skeletons.list(3);
  try {
    const order = await getOrder(reference, { token: token || null });
    $('[data-order-title]').textContent = `Order ${order.reference || order.order_number || reference}`;
    document.title = `Order ${order.reference || reference} — Starmond Technology Limited`;
    resolveRegion(region, renderOrderDetail(order, { guest: !!token }));
    bindActions(region);
  } catch (error) {
    if (error.isNotFound || error.isForbidden || error.isAuth) {
      resolveRegion(region, emptyState({
        title: 'This order is not available',
        text: token
          ? 'The secure link may have expired. Request a new link from the track order page.'
          : 'You do not have access to this order, or the reference is incorrect.',
        iconName: 'lock',
        actionHtml: '<a class="btn btn--primary btn--sm" href="/track-order.html">Request a new link</a><a class="btn btn--secondary btn--sm" href="/orders.html">My orders</a>',
      }));
      return;
    }
    renderRegionError(region, error, load, { title: 'This order could not be loaded' });
  }
}

function bindActions(region) {
  region.querySelector('[data-print-order]')?.addEventListener('click', () => window.print());
  region.querySelector('[data-cancel-order]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const ok = await confirmDialog({
      title: 'Cancel this order?',
      message: 'The order has not been paid for. Cancelling releases the reserved items. This cannot be undone.',
      confirmLabel: 'Cancel order', tone: 'danger',
    });
    if (!ok) return;
    button.disabled = true;
    try {
      await cancelOrder(button.dataset.cancelOrder);
      toast('Order cancelled.', { type: 'success' });
      load();
    } catch (error) {
      toast(error?.userMessage || 'This order could not be cancelled.', { type: 'danger' });
      button.disabled = false;
    }
  });
  region.querySelector('[data-retry-payment]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const result = await retryPayment(button.dataset.retryPayment);
      redirectToPaystack(result.authorizationUrl);
    } catch (error) {
      toast(error?.userMessage || 'Could not restart payment.', { type: 'danger' });
      button.disabled = false;
    }
  });

  region.querySelector('[data-request-refund]')?.addEventListener('click', (event) => {
    const ref = event.currentTarget.dataset.requestRefund;
    openDialog({
      title: 'Request a refund',
      sub: `Order ${ref}`,
      body: `<form class="stack" id="refund-form" novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <p class="t-sm t-muted">Refund eligibility and timelines are described in our returns and refund policy. Our team reviews every request.</p>
        <div class="field">
          <label class="field__label" for="rf-reason">Reason <span class="field__req">*</span></label>
          <select class="select" id="rf-reason" name="reason" required>
            <option value="">Choose a reason</option>
            <option value="damaged">Arrived damaged</option>
            <option value="wrong_item">Wrong item received</option>
            <option value="not_as_described">Not as described</option>
            <option value="not_received">Never received</option>
            <option value="changed_mind">No longer needed</option>
            <option value="other">Other</option>
          </select>
          <p class="field__error" data-error-for="reason"></p>
        </div>
        <div class="field">
          <label class="field__label" for="rf-details">Details <span class="field__req">*</span></label>
          <textarea class="textarea" id="rf-details" name="details" rows="4" required maxlength="2000"></textarea>
          <p class="field__error" data-error-for="details"></p>
        </div>
      </form>`,
      footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-submit-refund data-pending-label="Submitting">Submit request</button>',
      onMount({ element, close }) {
        const form = element.querySelector('#refund-form');
        element.querySelector('[data-submit-refund]').addEventListener('click', async (event2) => {
          try {
            await withSubmit(form, event2.currentTarget, () => requestRefund(ref, formData(form)));
            close();
            toast('Refund request submitted. Our team will be in touch.', { type: 'success' });
            load();
          } catch { /* rendered on form */ }
        });
      },
    });
  });
}

load();
