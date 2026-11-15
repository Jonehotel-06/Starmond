/**
 * account-page.js — profile, addresses, payment history, reviews, preferences.
 * Every section reads only the signed-in customer's own records; the backend
 * enforces that scoping on every endpoint.
 */

import boot from '../boot.js';
import api, { normalizeList } from '../api.js';
import {
  requireAuth, getUser, updateProfile, changePassword, updateNotificationPreferences, getCustomerProfile, logout,
} from '../auth.js';
import { listOrders, statusBadge } from '../orders.js';
import { listWishlist } from '../wishlist.js';
import { getDeliverableStates } from '../checkout.js';
import {
  resolveRegion, renderRegionError, emptyState, skeletons, toast, openDialog,
  confirmDialog, withSubmit, formData, downloadBlob,
} from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, formatDate, initials } from '../utils.js';

await boot();
// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await requireAuth()) {
  const user = getUser();

  /* ------------------------------------------------------------------ head -- */

  const greeting = $('[data-account-greeting]');
  if (greeting) {
    const name = String(user?.full_name || '').split(' ')[0];
    greeting.textContent = name ? `Welcome back, ${name}. Manage your profile, addresses and preferences.` : 'Manage your profile, addresses, orders and preferences.';
  }

  const profileForm = $('[data-profile-form]');
  if (profileForm) {
    ['full_name', 'email', 'phone'].forEach((field) => {
      if (profileForm.elements[field] && user?.[field]) profileForm.elements[field].value = user[field];
    });
  }

  $('[data-logout-page]')?.addEventListener('click', async () => {
    await logout();
    window.location.assign('/');
  });

  /* --------------------------------------------------------------- overview -- */

  async function loadStats() {
    const region = $('[data-account-stats]');
    try {
      // Real counts from the customer's own resources (no summary endpoint exists).
      const [orders, wishlist, addresses] = await Promise.all([
        listOrders({ page_size: 1 }),
        listWishlist().catch(() => ({ count: 0 })),
        api.privateGet('/customers/addresses/').then((d) => normalizeList(d)).catch(() => ({ count: 0 })),
      ]);
      const stats = [
        { label: 'Orders placed', value: orders.count, iconName: 'package', href: '/orders.html' },
        { label: 'Wishlist items', value: wishlist.count, iconName: 'heart', href: '/wishlist.html' },
        { label: 'Saved addresses', value: addresses.count, iconName: 'map-pin', href: '#addresses' },
      ];
      resolveRegion(region, stats.map((stat) => `<a class="stat-card" href="${esc(stat.href)}">
        <div class="stat-card__head"><span class="stat-card__label">${esc(stat.label)}</span><span class="stat-card__icon">${icon(stat.iconName, { size: 'sm' })}</span></div>
        <span class="stat-card__value">${esc(stat.value)}</span>
      </a>`).join(''));
    } catch (error) {
      renderRegionError(region, error, loadStats);
    }
  }

  /* -------------------------------------------------------------- addresses -- */

  let statesCache = null;

  async function loadAddresses() {
    const region = $('[data-addresses]');
    try {
      const data = await api.privateGet('/customers/addresses/');
      const addresses = normalizeList(data).results;
      if (!addresses.length) {
        resolveRegion(region, emptyState({
          title: 'No saved addresses', text: 'Save an address to check out faster next time.', iconName: 'map-pin', inline: true,
          actionHtml: '<button type="button" class="btn btn--primary btn--sm" data-address-add>Add an address</button>',
        }));
        return;
      }
      resolveRegion(region, `<div class="address-grid">${addresses.map((address) => `
        <div class="address-card">
          <div class="address-card__head">
            <span class="address-card__label">${esc(address.label || address.full_name || 'Address')}</span>
            ${address.is_default ? '<span class="badge badge--primary">Default</span>' : ''}
          </div>
          <p class="address-card__body">
            ${esc(address.full_name || '')}<br>
            ${esc(address.street || '')}${address.details ? `<br>${esc(address.details)}` : ''}<br>
            ${esc([address.city, address.state].filter(Boolean).join(', '))}<br>
            ${esc(address.phone || '')}
          </p>
          <div class="address-card__actions">
            <button type="button" class="btn btn--secondary btn--sm" data-address-edit="${esc(address.id)}">Edit</button>
            <button type="button" class="btn btn--ghost btn--sm" data-address-delete="${esc(address.id)}">Delete</button>
            ${!address.is_default ? `<button type="button" class="link-btn" data-address-default="${esc(address.id)}">Make default</button>` : ''}
          </div>
        </div>`).join('')}</div>`);
      region.__addresses = addresses;
    } catch (error) {
      renderRegionError(region, error, loadAddresses, { title: 'Addresses could not be loaded' });
    }
  }

  async function openAddressDialog(existing = null) {
    statesCache = statesCache || await getDeliverableStates();
    openDialog({
      title: existing ? 'Edit address' : 'Add an address',
      body: `<form class="stack" id="address-form" novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="form-grid">
          <div class="field"><label class="field__label" for="ad-label">Label</label><input class="input" id="ad-label" name="label" value="${esc(existing?.label || '')}" placeholder="Home, Office"></div>
          <div class="field"><label class="field__label" for="ad-name">Full name <span class="field__req">*</span></label><input class="input" id="ad-name" name="full_name" required value="${esc(existing?.full_name || '')}"><p class="field__error" data-error-for="full_name"></p></div>
          <div class="field"><label class="field__label" for="ad-phone">Phone <span class="field__req">*</span></label><input class="input" id="ad-phone" name="phone" type="tel" required value="${esc(existing?.phone || '')}"><p class="field__error" data-error-for="phone"></p></div>
          <div class="field"><label class="field__label" for="ad-state">State <span class="field__req">*</span></label>
            <select class="select" id="ad-state" name="state" required><option value="">Select state</option>${statesCache.map((s) => `<option value="${esc(s)}" ${existing?.state === s ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>
            <p class="field__error" data-error-for="state"></p></div>
          <div class="field form-grid__full"><label class="field__label" for="ad-city">City <span class="field__req">*</span></label><input class="input" id="ad-city" name="city" required value="${esc(existing?.city || '')}"><p class="field__error" data-error-for="city"></p></div>
          <div class="field form-grid__full"><label class="field__label" for="ad-line1">Address <span class="field__req">*</span></label><input class="input" id="ad-line1" name="street" required value="${esc(existing?.street || '')}"><p class="field__error" data-error-for="address_line1"></p></div>
          <div class="field form-grid__full"><label class="field__label" for="ad-line2">Additional details</label><input class="input" id="ad-line2" name="details" value="${esc(existing?.details || '')}"></div>
        </div>
        <label class="checkbox"><input type="checkbox" name="is_default" ${existing?.is_default ? 'checked' : ''}><span>Use as my default delivery address</span></label>
      </form>`,
      footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-save-address data-pending-label="Saving">Save address</button>',
      onMount({ element, close }) {
        const form = element.querySelector('#address-form');
        element.querySelector('[data-save-address]').addEventListener('click', async (event) => {
          const values = formData(form);
          try {
            await withSubmit(form, event.currentTarget, () => (existing
              ? api.patch(`/customers/addresses/${existing.id}/`, { ...values, is_default: !!values.is_default })
              : api.post('/customers/addresses/', { kind: 'shipping', ...values, is_default: !!values.is_default })));
            close();
            toast('Address saved.', { type: 'success' });
            loadAddresses();
          } catch { /* rendered on form */ }
        });
      },
    });
  }

  /* --------------------------------------------------------------- payments -- */

  async function loadPayments() {
    const region = $('[data-account-payments]');
    try {
      const data = await api.privateGet('/payments/mine/');
      const payments = normalizeList(data).results;
      if (!payments.length) {
        resolveRegion(region, emptyState({ title: 'No payments yet', text: 'Your payment receipts will appear here.', iconName: 'credit-card', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="table-wrap"><table class="table table--responsive">
        <caption class="sr-only">Payment history</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col">Date</th><th scope="col">Status</th><th scope="col" class="num">Amount</th></tr></thead>
        <tbody>${payments.map((payment) => `<tr>
          <td data-label="Reference"><span class="table__primary">${esc(payment.reference)}</span></td>
          <td data-label="Date">${esc(formatDate(payment.verified_at || payment.initialized_at))}</td>
          <td data-label="Status">${statusBadge(payment.status)}</td>
          <td data-label="Amount" class="num">${esc(formatMoney(payment.amount, payment.currency || 'NGN'))}</td>
        </tr>`).join('')}</tbody>
      </table></div>`);
    } catch (error) {
      renderRegionError(region, error, loadPayments, { title: 'Payment history could not be loaded' });
    }
  }

  /* ---------------------------------------------------------------- reviews -- */

  async function loadReviews() {
    const region = $('[data-account-reviews]');
    try {
      const data = await api.privateGet('/reviews/mine/');
      const reviews = normalizeList(data).results;
      if (!reviews.length) {
        resolveRegion(region, emptyState({ title: 'You have not written a review yet', text: 'Reviews help other shoppers choose with confidence.', iconName: 'star', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="card"><div class="card__body">${reviews.map((review) => `
        <article class="review">
          <div class="review__head">
            <span class="t-sm t-semibold">${esc(review.product_name || 'Product')}</span>
            <span class="badge badge--${review.moderation_status === 'approved' ? 'success' : review.moderation_status === 'rejected' ? 'danger' : 'warning'}">${review.moderation_status === 'approved' ? 'Published' : review.moderation_status === 'rejected' ? 'Not published' : 'Awaiting moderation'}</span>
          </div>
          ${review.title ? `<p class="review__title">${esc(review.title)}</p>` : ''}
          <p class="review__body">${esc(review.body || review.comment || '')}</p>
          <span class="t-meta">${esc(formatDate(review.created_at))} · ${esc(review.rating)}/5</span>
        </article>`).join('')}</div></div>`);
    } catch (error) {
      renderRegionError(region, error, loadReviews, { title: 'Your reviews could not be loaded' });
    }
  }

  /* ------------------------------------------------------------ preferences -- */

  async function loadPreferences() {
    const form = $('[data-preferences-form]');
    if (!form) return;
    try {
      const prefs = await getCustomerProfile();
      Object.entries(prefs || {}).forEach(([key, value]) => {
        if (form.elements[key]) form.elements[key].checked = !!value;
      });
    } catch {
      // Leave defaults unchecked rather than guessing the customer's consent.
    }
  }

  /* ----------------------------------------------------------------- events -- */

  profileForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await withSubmit(profileForm, profileForm.querySelector('button[type="submit"]'), () => {
        const { full_name, phone } = formData(profileForm);
        return updateProfile({ full_name, phone });
      });
      toast('Profile updated.', { type: 'success' });
    } catch { /* rendered on form */ }
  });

  $('[data-password-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = formData(form);
    if (values.new_password !== values.new_password_confirm) {
      const { applyFormErrors } = await import('../ui.js');
      applyFormErrors(form, { new_password_confirm: 'Passwords do not match.' });
      return;
    }
    try {
      await withSubmit(form, form.querySelector('button[type="submit"]'), () => changePassword(values));
      form.reset();
      toast('Password updated.', { type: 'success' });
    } catch { /* rendered on form */ }
  });

  $('[data-preferences-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await withSubmit(form, form.querySelector('button[type="submit"]'), () => updateNotificationPreferences({
        order_update_emails: !!form.elements.order_update_emails?.checked,
        marketing_emails: !!form.elements.marketing_emails?.checked,
        sms_updates: !!form.elements.sms_updates?.checked,
      }));
      toast('Notification preferences saved.', { type: 'success' });
    } catch { /* rendered on form */ }
  });

  document.addEventListener('click', async (event) => {
    if (event.target.closest('[data-address-add]')) { openAddressDialog(); return; }

    const edit = event.target.closest('[data-address-edit]');
    if (edit) {
      const list = $('[data-addresses]').__addresses || [];
      openAddressDialog(list.find((a) => String(a.id) === edit.dataset.addressEdit));
      return;
    }

    const del = event.target.closest('[data-address-delete]');
    if (del) {
      const confirmed = await confirmDialog({ title: 'Delete this address?', message: 'It will be removed from your account.', confirmLabel: 'Delete', tone: 'danger' });
      if (!confirmed) return;
      try { await api.delete(`/customers/addresses/${del.dataset.addressDelete}/`); toast('Address deleted.', { type: 'success' }); loadAddresses(); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
      return;
    }

    const makeDefault = event.target.closest('[data-address-default]');
    if (makeDefault) {
      try {
        await api.patch(`/customers/addresses/${makeDefault.dataset.addressDefault}/`, { is_default: true });
        toast('Default address updated.', { type: 'success' });
        loadAddresses();
      } catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }
  });

  /* -------------------------------------------------------------------- run -- */

  loadStats();
  loadAddresses();
  loadPayments();
  loadReviews();
  loadPreferences();

  if (location.hash) {
    requestAnimationFrame(() => document.querySelector(location.hash)?.scrollIntoView({ block: 'start' }));
  }
}
