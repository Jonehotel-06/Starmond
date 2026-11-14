/**
 * track-order-page.js — secure guest order access.
 * The backend emails an expiring signed link; no order data is returned here.
 */
import boot from '../boot.js';
import { requestGuestAccess } from '../orders.js';
import { withSubmit, formData, toast, resolveRegion } from '../ui.js';
import { icon } from '../icons.js';
import { $, readQuery, isEmail } from '../utils.js';
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
    await withSubmit(form, button, () => requestGuestAccess({
      reference: String(values.reference).trim(), email: String(values.email).trim().toLowerCase(),
    }));
    // Deliberately identical response whether or not the order exists, so the
    // endpoint cannot be used to enumerate orders.
    form.hidden = true;
    resolveRegion($('[data-track-result]'), `<div class="alert alert--success" role="status">
      <span class="alert__icon">${icon('mail')}</span>
      <div class="alert__body">
        <span class="alert__title">Check your email</span>
        <span>If an order matches that reference and email address, we have sent a secure access link. The link expires for your security.</span>
      </div>
    </div>`);
  } catch { /* withSubmit renders the error */ }
});
