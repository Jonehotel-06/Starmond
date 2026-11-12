/** Sign in, registration and password recovery (one module for four pages). */
import { ready } from '../app.js';
import { auth } from '../api.js';
import { session } from '../store.js';
import { toast } from '../ui/toast.js';
import { clearErrors, fieldError, qs, setBusy, sitePath, validate } from '../utils.js';

const page = document.body.dataset.page;
const nextParam = new URLSearchParams(location.search).get('next');

function goNext() {
  if (nextParam && /^\/|^[a-z0-9._-]+\.html/i.test(nextParam) && !/^(https?:)?\/\//i.test(nextParam)) {
    window.location.href = nextParam;
    return;
  }
  window.location.href = session.isStaff ? sitePath('admin/index.html') : sitePath('account.html');
}

/* -------------------------------------------------------------------- login */
qs('[data-login-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const errorEl = qs('[data-login-error]');
  errorEl.hidden = true;
  const data = new FormData(form);
  const email = String(data.get('email') || '').trim();
  const password = String(data.get('password') || '');
  let valid = true;
  if (validate.email(email)) { fieldError(form, 'email', validate.email(email)); valid = false; }
  if (!password) { fieldError(form, 'password', 'Enter your password.'); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true, 'Signing in…');
  try {
    await session.signIn({ email, password });
    toast(`Welcome back, ${session.displayName.split(' ')[0] || 'there'}.`, { type: 'success' });
    goNext();
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    errorEl.textContent = err.status === 401
      ? 'Those details do not match an account. Check your email and password, or reset your password.'
      : err.message;
    errorEl.hidden = false;
    setBusy(button, false);
  }
});

/* ----------------------------------------------------------------- register */
qs('[data-register-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const errorEl = qs('[data-register-error]');
  errorEl.hidden = true;
  const data = new FormData(form);
  const payload = {
    first_name: String(data.get('first_name') || '').trim(),
    last_name: String(data.get('last_name') || '').trim(),
    email: String(data.get('email') || '').trim(),
    phone: String(data.get('phone') || '').trim(),
    password: String(data.get('password') || ''),
    password_confirm: String(data.get('password_confirm') || '')
  };
  let valid = true;
  if (validate.required(payload.first_name, 'First name')) { fieldError(form, 'first_name', 'Enter your first name.'); valid = false; }
  if (validate.required(payload.last_name, 'Last name')) { fieldError(form, 'last_name', 'Enter your last name.'); valid = false; }
  if (validate.email(payload.email)) { fieldError(form, 'email', validate.email(payload.email)); valid = false; }
  if (validate.phone(payload.phone)) { fieldError(form, 'phone', validate.phone(payload.phone)); valid = false; }
  if (validate.minLen(payload.password, 8, 'Your password')) { fieldError(form, 'password', 'Use at least 8 characters.'); valid = false; }
  if (payload.password !== payload.password_confirm) { fieldError(form, 'password_confirm', 'The passwords do not match.'); valid = false; }
  if (!data.get('accept_terms')) { fieldError(form, 'accept_terms', 'Accept the terms to create an account.'); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true, 'Creating your account…');
  try {
    const result = await auth.register(payload);
    if (result?.access || result?.access_token) {
      await session.signIn({ email: payload.email, password: payload.password });
      toast('Your account is ready.', { type: 'success' });
      goNext();
      return;
    }
    toast(result?.detail || 'Account created. Check your email to verify the address, then sign in.', { type: 'success', timeout: 9000 });
    window.location.href = `${sitePath('login.html')}?registered=1`;
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    errorEl.textContent = err.message;
    errorEl.hidden = false;
    setBusy(button, false);
  }
});

/* ----------------------------------------------------------- forgot password */
qs('[data-forgot-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const errorEl = qs('[data-forgot-error]');
  const successEl = qs('[data-forgot-success]');
  errorEl.hidden = true;
  successEl.hidden = true;
  const email = String(new FormData(form).get('email') || '').trim();
  if (validate.email(email)) { fieldError(form, 'email', validate.email(email)); return; }

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true);
  try {
    await auth.requestPasswordReset(email);
    successEl.textContent = 'If an account exists for that address, a reset link is on its way. The link expires shortly after it is sent.';
    successEl.hidden = false;
    form.reset();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    setBusy(button, false);
  }
});

/* ------------------------------------------------------------ reset password */
qs('[data-reset-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const errorEl = qs('[data-reset-error]');
  const successEl = qs('[data-reset-success]');
  errorEl.hidden = true;
  successEl.hidden = true;
  const params = new URLSearchParams(location.search);
  const token = params.get('token') || params.get('uidb64') || '';
  const data = new FormData(form);
  const password = String(data.get('password') || '');
  const confirm = String(data.get('password_confirm') || '');

  if (!token) {
    errorEl.textContent = 'This reset link is missing its token. Request a new link from the forgot-password page.';
    errorEl.hidden = false;
    return;
  }
  let valid = true;
  if (validate.minLen(password, 8, 'Your password')) { fieldError(form, 'password', 'Use at least 8 characters.'); valid = false; }
  if (password !== confirm) { fieldError(form, 'password_confirm', 'The passwords do not match.'); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true);
  try {
    await auth.confirmPasswordReset({ token, uid: params.get('uid') || '', password });
    successEl.textContent = 'Password updated. You can now sign in with the new password.';
    successEl.hidden = false;
    form.reset();
    setTimeout(() => { window.location.href = sitePath('login.html'); }, 2200);
  } catch (err) {
    errorEl.textContent = err.status === 400
      ? 'That reset link is invalid or has expired. Request a new one.'
      : err.message;
    errorEl.hidden = false;
  } finally {
    setBusy(button, false);
  }
});

/* Demo-mode sign-in help: shown only when no backend is configured. */
ready.then(() => {
  if (page === 'login') {
    import('../env.js').then(({ IS_DEMO }) => {
      if (!IS_DEMO) return;
      const card = document.querySelector('.auth-card');
      if (!card || card.querySelector('[data-demo-creds]')) return;
      const box = document.createElement('div');
      box.className = 'alert alert--warn';
      box.setAttribute('data-demo-creds', '');
      box.setAttribute('role', 'note');
      box.innerHTML = `<div><p><strong>Demo mode credentials</strong> (sample data, no backend connected):</p>
        <p class="small">Customer: <code>customer@example.com</code> / <code>Customer123!</code><br>
        Staff / owner: <code>owner@starmond.demo</code> / <code>Owner123!</code></p></div>`;
      card.appendChild(box);
    });
  }
  if (session.isAuthenticated && (page === 'login' || page === 'register')) {
    goNext();
  }
  if (page === 'login' && new URLSearchParams(location.search).get('registered')) {
    toast('Account created — sign in to continue.', { type: 'success' });
  }
});
