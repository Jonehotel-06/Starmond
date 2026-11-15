/**
 * track-order-page.js — secure guest order access.
 * The backend emails an expiring signed link; no order data is returned here.
 */
import boot from '../boot.js';
import { requestGuestAccess, statusBadge } from '../orders.js';
import { withSubmit, formData, toast, resolveRegion } from '../ui.js';
import { icon } from '../icons.js';
import { $, esc, readQuery, isEmail, formatDate, formatMoney } from '../utils.js';
import { applyFormErrors } from '../ui.js';

await boot();

const params = readQuery();
const form = $('[data-track-form]');
if (params.reference && form) form.elements.reference.value = params.reference;
if (params.email && form) form.elements.email.value = params.email;

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = formData(form);
  const errors = {};
  if (!String(values.reference || '').trim()) errors.reference = 'Enter the order reference from your receipt.';
  if (!isEmail(values.email)) errors.email = 'Enter the email address used at checkout.';
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

  const button = form.querySelector('button[type="submit"]');
  try {
    const result = await withSubmit(form, button, () => requestGuestAccess({
      reference: String(values.reference).trim().toUpperCase(), email: String(values.email).trim().toLowerCase(),
    }));
    // The backend verified reference + email and issued an access token, which
    // is kept in this tab's sessionStorage (never placed in the URL).
    const summary = result.summary;
    form.hidden = true;
    resolveRegion($('[data-track-result]'), `<div class="card"><div class="card__body stack">
      <div class="cluster cluster--between">
        <span class="order-card__ref">${esc(result.reference)}</span>
        ${summary ? statusBadge(summary.status) : ''}
      </div>
      ${summary ? `<p class="t-sm t-muted">Placed ${esc(formatDate(summary.created_at))} · ${esc(summary.item_count || 0)} item${Number(summary.item_count) === 1 ? '' : 's'}
        · ${esc(formatMoney(summary.total, summary.currency))}</p>` : ''}
      <div class="cluster cluster--sm">
        <a class="btn btn--primary" href="/order-detail.html?reference=${encodeURIComponent(result.reference)}">${icon('receipt', { size: 'sm' })} View full order</a>
        <button type="button" class="btn btn--secondary" data-track-again>Track another order</button>
      </div>
    </div></div>`);
    $('[data-track-again]')?.addEventListener('click', () => {
      form.hidden = false; form.reset(); $('[data-track-result]').innerHTML = '';
    });
  } catch { /* withSubmit renders the error */ }
});
