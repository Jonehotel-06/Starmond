/**
 * auth-page.js — sign in, register, verify email, password reset.
 * All credential handling is delegated to backend endpoints over HTTPS.
 */
import boot from '../boot.js';
import {
  login, register, requestPasswordReset, confirmPasswordReset,
  verifyEmail, resendVerification, isAuthenticated, isStaff, safeNext, initAuth,
} from '../auth.js';
import { withSubmit, formData, applyFormErrors, toast, resolveRegion, emptyState } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { $, esc, readQuery, isEmail, normalizePhone } from '../utils.js';
import api from '../api.js';

await boot();
await initAuth();

const params = readQuery();
const next = safeNext(params.next, '/account.html');

/* Password visibility toggles ------------------------------------------- */
document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const input = button.parentElement.querySelector('input');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(show));
    button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    button.innerHTML = icon(show ? 'eye-off' : 'eye', { size: 'sm' });
  });
});

/* Password strength meter (advisory only; backend enforces policy) -------- */
const passwordInput = $('#reg-password');
if (passwordInput) {
  const meter = $('[data-password-strength]');
  const fill = $('[data-strength-fill]');
  const label = $('[data-strength-label]');
  passwordInput.addEventListener('input', () => {
    const value = passwordInput.value;
    if (!value) { meter.hidden = true; return; }
    meter.hidden = false;
    let score = 0;
    if (value.length >= 8) score += 1;
    if (value.length >= 12) score += 1;
    if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
    if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score += 1;
    const labels = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'];
    fill.style.width = `${(score / 4) * 100}%`;
    fill.dataset.level = String(score);
    label.textContent = labels[score];
  });
}

/* Sign in ---------------------------------------------------------------- */
$('[data-login-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  const errors = {};
  if (!isEmail(values.email)) errors.email = 'Enter a valid email address.';
  if (!values.password) errors.password = 'Enter your password.';
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => login({
      email: String(values.email).trim().toLowerCase(),
      password: values.password,
    }));
    toast('Signed in successfully.', { type: 'success' });
    // Staff land on the admin console unless they were sent here from a specific page.
    window.location.assign(!params.next && isStaff() ? '/admin/index.html' : next);
  } catch { /* rendered on the form */ }
});

/* Register --------------------------------------------------------------- */
$('[data-register-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  const errors = {};
  if (String(values.full_name || '').trim().length < 2) errors.full_name = 'Enter your full name.';
  if (!isEmail(values.email)) errors.email = 'Enter a valid email address.';
  if (!values.phone) errors.phone = 'Enter a phone number.';
  if (String(values.password || '').length < 8) errors.password = 'Use at least 8 characters.';
  if (values.password !== values.password_confirm) errors.password_confirm = 'Passwords do not match.';
  if (!values.accept_terms) errors.accept_terms = 'Please accept the terms to continue.';
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => register({
      full_name: String(values.full_name).trim(),
      email: String(values.email).trim().toLowerCase(),
      phone: normalizePhone(values.phone),
      password: values.password,
    }));
    if (values.newsletter_opt_in) {
      // Optional and independent of the account: POST /notifications/newsletter/
      api.post('/notifications/newsletter/', { email: String(values.email).trim().toLowerCase() }).catch(() => {});
    }
    if (isAuthenticated()) {
      toast('Account created. Welcome to Starmond.', { type: 'success' });
      window.location.assign(next);
    } else {
      form.hidden = true;
      form.insertAdjacentHTML('afterend', `<div class="alert alert--success" role="status">
        <span class="alert__icon">${icon('mail')}</span>
        <div class="alert__body"><span class="alert__title">Verify your email</span>
        <span>We sent a verification link to ${esc(String(values.email).trim())}. Open it to activate your account, then sign in.</span></div>
      </div>`);
      hydrateIcons(form.parentElement);
    }
  } catch { /* rendered on the form */ }
});

/* Forgot password -------------------------------------------------------- */
$('[data-forgot-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  if (!isEmail(values.email)) { applyFormErrors(form, { email: 'Enter a valid email address.' }); return; }
  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => requestPasswordReset(String(values.email).trim().toLowerCase()));
    const success = form.querySelector('[data-form-success]');
    success.innerHTML = `<span class="alert__icon">${icon('mail')}</span><div class="alert__body"><span class="alert__title">Check your email</span><span>If an account exists for that address, a reset link is on its way. The link expires for your security.</span></div>`;
    success.hidden = false;
    hydrateIcons(success);
    form.querySelector('button[type="submit"]').disabled = true;
  } catch { /* rendered on the form */ }
});

/* Reset password --------------------------------------------------------- */
$('[data-reset-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  const errors = {};
  if (!params.token || !params.uid) errors.detail = 'This reset link is incomplete. Request a new one.';
  if (String(values.new_password || '').length < 8) errors.new_password = 'Use at least 8 characters.';
  if (values.new_password !== values.new_password_confirm) errors.new_password_confirm = 'Passwords do not match.';
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }
  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => confirmPasswordReset({
      token: params.token, uid: params.uid, new_password: values.new_password,
    }));
    toast('Password updated. You can now sign in.', { type: 'success' });
    setTimeout(() => window.location.assign('/login.html'), 1500);
  } catch { /* rendered on the form */ }
});

/* Email verification ----------------------------------------------------- */
const verifyRegion = $('[data-verify-region]');
if (verifyRegion) {
  const showResend = () => { $('[data-resend-form]').hidden = false; };
  if (!params.token) {
    resolveRegion(verifyRegion, emptyState({
      title: 'No verification token found',
      text: 'Open the link from your verification email, or request a new one below.',
      iconName: 'mail', inline: true,
    }));
    showResend();
  } else {
    try {
      await verifyEmail(params.token);
      resolveRegion(verifyRegion, `<div class="alert alert--success" role="status">
        <span class="alert__icon">${icon('check-circle')}</span>
        <div class="alert__body"><span class="alert__title">Email verified</span><span>Your account is active. You can now sign in.</span></div>
      </div><a class="btn btn--primary btn--block" href="/login.html" style="margin-top:1rem">Sign in</a>`);
    } catch (error) {
      resolveRegion(verifyRegion, `<div class="alert alert--danger" role="alert">
        <span class="alert__icon">${icon('alert-circle')}</span>
        <div class="alert__body"><span class="alert__title">Verification failed</span><span>${esc(error.userMessage || 'This link is invalid or has expired.')}</span></div>
      </div>`);
      showResend();
    }
  }
}

$('[data-resend-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formData(form);
  if (!isEmail(values.email)) { applyFormErrors(form, { email: 'Enter a valid email address.' }); return; }
  try {
    await withSubmit(form, form.querySelector('button[type="submit"]'), () => resendVerification(String(values.email).trim().toLowerCase()));
    const success = form.querySelector('[data-form-success]');
    success.innerHTML = `<span class="alert__icon">${icon('mail')}</span><div class="alert__body"><span>A new verification email has been sent if that account exists.</span></div>`;
    success.hidden = false;
    hydrateIcons(success);
  } catch { /* rendered on the form */ }
});

/* Prefill email on register from a payment result ------------------------- */
if (params.email && $('#reg-email')) $('#reg-email').value = params.email;
