/**
 * contact-page.js — enquiry form. Submissions create backend enquiry records.
 */
import boot from '../boot.js';
import api from '../api.js';
import { getSettings } from '../site.js';
import { withSubmit, formData, applyFormErrors, toast } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { $, isEmail, normalizePhone } from '../utils.js';

await boot();

getSettings().then((settings) => {
  const hasContact = settings?.business?.email || settings?.business?.phone || settings?.business?.address;
  const fallback = $('[data-contact-fallback]');
  if (fallback) fallback.hidden = !!hasContact;
});

$('[data-contact-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  const errors = {};
  if (!String(values.name || '').trim()) errors.name = 'Enter your name.';
  if (!isEmail(values.email)) errors.email = 'Enter a valid email address.';
  if (!values.subject) errors.subject = 'Choose a subject.';
  if (String(values.message || '').trim().length < 10) errors.message = 'Please describe your enquiry in a little more detail.';
  if (!values.consent) errors.consent = 'Please give consent so we can reply to you.';
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => api.post('/enquiries/', {
      name: String(values.name).trim(),
      email: String(values.email).trim().toLowerCase(),
      phone: values.phone ? normalizePhone(values.phone) : '',
      subject: values.subject,
      order_reference: String(values.order_reference || '').trim(),
      message: String(values.message).trim(),
      consent: true,
    }));
    form.reset();
    const success = form.querySelector('[data-form-success]');
    success.innerHTML = `<span class="alert__icon">${icon('check-circle')}</span>
      <div class="alert__body"><span class="alert__title">Message sent</span>
      <span>Thank you. Our team has received your enquiry and will reply by email.</span></div>`;
    success.hidden = false;
    hydrateIcons(success);
    success.scrollIntoView({ block: 'center', behavior: 'smooth' });
    toast('Your message has been sent.', { type: 'success' });
  } catch { /* rendered on the form */ }
});
