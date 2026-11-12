/** Contact form — posts to the backend support inbox. */
import { ready } from '../app.js';
import { support } from '../api.js';
import { clearErrors, fieldError, qs, setBusy, validate } from '../utils.js';
import { toast } from '../ui/toast.js';

const form = qs('[data-contact-form]');

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearErrors(form);
  const errorEl = qs('[data-contact-error]');
  const successEl = qs('[data-contact-success]');
  errorEl.hidden = true;
  successEl.hidden = true;

  const data = new FormData(form);
  const payload = {
    name: String(data.get('name') || '').trim(),
    email: String(data.get('email') || '').trim(),
    phone: String(data.get('phone') || '').trim(),
    topic: String(data.get('topic') || 'other'),
    order_number: String(data.get('order_number') || '').trim(),
    message: String(data.get('message') || '').trim()
  };
  let valid = true;
  if (validate.required(payload.name, 'Your name')) { fieldError(form, 'name', 'Enter your name.'); valid = false; }
  if (validate.email(payload.email)) { fieldError(form, 'email', validate.email(payload.email)); valid = false; }
  if (payload.phone && validate.phone(payload.phone)) { fieldError(form, 'phone', validate.phone(payload.phone)); valid = false; }
  if (validate.minLen(payload.message, 10, 'Your message')) { fieldError(form, 'message', 'Please give us a little more detail (at least 10 characters).'); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true, 'Sending…');
  try {
    const result = await support.sendMessage(payload);
    successEl.textContent = result?.detail || 'Message received. We reply during business hours to the email address you provided.';
    successEl.hidden = false;
    form.reset();
    toast('Message sent.', { type: 'success' });
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    setBusy(button, false);
  }
});

ready.then(() => {
  const session = window.starmond?.session;
  if (session?.isAuthenticated) {
    const user = session.user || {};
    const set = (name, value) => {
      const input = form?.querySelector(`[name="${name}"]`);
      if (input && !input.value) input.value = value || '';
    };
    set('name', [user.first_name, user.last_name].filter(Boolean).join(' '));
    set('email', user.email);
    set('phone', user.phone);
  }
  const orderParam = new URLSearchParams(location.search).get('order');
  if (orderParam) {
    const input = form?.querySelector('[name="order_number"]');
    if (input) input.value = orderParam;
  }
});
