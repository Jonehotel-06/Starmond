/** Customer account area: orders, addresses, profile, notifications, security. */
import { ready } from '../app.js';
import { account, auth, orders } from '../api.js';
import { session, wishlist } from '../store.js';
import { statusPill } from '../ui/timeline.js';
import { toast, notifyError } from '../ui/toast.js';
import {
  clearErrors, esc, fieldError, fillStates, formatDate, formatDateTime, money, qs, qsa,
  relativeTime, setBusy, sitePath, starRow, validate
} from '../utils.js';

const layout = qs('[data-account-layout]');
const guestAlert = qs('[data-account-guest]');
const titleEl = qs('[data-account-title]');
const subEl = qs('[data-account-sub]');
const tabs = qsa('[data-account-tabs] [role="tab"]');

let ordersPage = 1;
let ordersStatus = '';

/* -------------------------------------------------------------------- tabs */
function activateTab(tab, { focus = false } = {}) {
  tabs.forEach((t) => {
    const selected = t === tab;
    t.setAttribute('aria-selected', String(selected));
    t.tabIndex = selected ? 0 : -1;
    const panel = document.getElementById(t.getAttribute('aria-controls'));
    if (panel) panel.hidden = !selected;
  });
  if (focus) tab.focus();
  const id = (tab?.id || '').replace('tab-', '');
  if (id) history.replaceState(null, '', `#${id}`);
  if (id === 'orders') loadOrders(1);
  if (id === 'addresses') loadAddresses();
  if (id === 'notifications') loadNotifications();
}

function initTabs() {
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', (event) => {
      const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      let next = index;
      if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      activateTab(tabs[next], { focus: true });
    });
  });
  const fromHash = location.hash.replace('#', '');
  const initial = tabs.find((t) => t.id === `tab-${fromHash}`) || tabs[0];
  if (initial) activateTab(initial);
}

/* ------------------------------------------------------------------ orders */
function orderRow(order, { compact = false } = {}) {
  const items = order.item_count ?? (order.items || []).length;
  return `<tr>
    <td><a href="${sitePath('order.html')}?order=${encodeURIComponent(order.order_number || order.id)}">
      <strong>${esc(order.order_number || order.id)}</strong></a></td>
    <td>${formatDate(order.created_at)}</td>
    ${compact ? '' : `<td>${esc(items)}</td>`}
    <td>${statusPill(order.status)}</td>
    <td class="num">${money(order.total ?? order.totals?.total ?? 0, order.currency || 'NGN')}</td>
    <td><a class="btn btn--outline btn--sm" href="${sitePath('order.html')}?order=${encodeURIComponent(order.order_number || order.id)}">View</a></td>
  </tr>`;
}

async function loadOverview() {
  const recentBody = qs('[data-recent-orders]');
  try {
    const data = await orders.list({ page_size: 5 });
    const items = data.items;
    qs('[data-stat-orders]').textContent = String(data.count ?? items.length);
    const open = items.filter((o) => !['delivered', 'cancelled', 'refunded'].includes(String(o.status).toLowerCase())).length;
    qs('[data-stat-open]').textContent = String(open);
    qs('[data-stat-wishlist]').textContent = String(wishlist.count);
    recentBody.innerHTML = items.length
      ? items.slice(0, 3).map((o) => orderRow(o)).join('')
      : '<tr><td colspan="5" class="muted">You have not placed an order yet. <a href="' + sitePath('shop.html') + '">Start shopping</a>.</td></tr>';
  } catch (err) {
    recentBody.innerHTML = `<tr><td colspan="5" class="muted">${esc(err.message)}</td></tr>`;
  }
}

async function loadOrders(page = 1) {
  const body = qs('[data-orders-body]');
  const pager = qs('[data-orders-pager]');
  ordersPage = page;
  body.innerHTML = '<tr><td colspan="6"><div class="skeleton" style="height:34px"></div></td></tr>';
  try {
    const data = await orders.list({ page, page_size: 10, status: ordersStatus || undefined });
    body.innerHTML = data.items.length
      ? data.items.map((o) => orderRow(o)).join('')
      : '<tr><td colspan="6" class="muted">No orders match this filter.</td></tr>';
    if (pager) {
      pager.hidden = (data.pages || 1) <= 1;
      pager.innerHTML = '';
      if ((data.pages || 1) > 1) {
        const button = (label, target, disabled, current) =>
          `<button class="pager__link" type="button" data-orders-page="${target}"
            ${disabled ? 'aria-disabled="true" disabled' : ''} ${current ? 'aria-current="page"' : ''}>${label}</button>`;
        pager.innerHTML = [
          button('Prev', page - 1, page <= 1, false),
          ...Array.from({ length: data.pages }, (_, i) => i + 1)
            .slice(Math.max(0, page - 3), Math.max(0, page - 3) + 5)
            .map((p) => button(String(p), p, false, p === page)),
          button('Next', page + 1, page >= data.pages, false)
        ].join('');
        qsa('[data-orders-page]', pager).forEach((btn) => {
          btn.addEventListener('click', () => loadOrders(Number(btn.dataset.ordersPage)));
        });
      }
    }
  } catch (err) {
    body.innerHTML = `<tr><td colspan="6" class="muted">${esc(err.message)}</td></tr>`;
  }
}

qs('[data-orders-filter]')?.addEventListener('change', (event) => {
  ordersStatus = event.target.value;
  loadOrders(1);
});

/* ---------------------------------------------------------------- addresses */
async function loadAddresses() {
  const list = qs('[data-address-list]');
  list.innerHTML = '<p class="muted small">Loading addresses…</p>';
  try {
    const data = await account.addresses();
    const items = Array.isArray(data) ? data : (data?.results || []);
    if (!items.length) {
      list.innerHTML = '<p class="muted">No saved addresses yet. Add one to speed up checkout.</p>';
      return;
    }
    list.innerHTML = items.map((address) => `<article class="address-card ${address.is_default ? 'address-card--default' : ''}">
      <h3>${esc(address.label || 'Address')}${address.is_default ? ' <span class="pill pill--ok">Default</span>' : ''}</h3>
      <p class="small">${esc(address.recipient_name || '')}<br>
      ${[address.line1, address.line2, address.area].filter(Boolean).map(esc).join(', ')}<br>
      ${esc(address.city || '')}, ${esc(address.state || '')}<br>
      ${esc(address.phone || '')}</p>
      <div class="address-card__actions">
        <button class="btn btn--outline btn--sm" type="button" data-address-edit="${esc(address.id)}">Edit</button>
        <button class="btn btn--danger btn--sm" type="button" data-address-delete="${esc(address.id)}">Delete</button>
      </div>
    </article>`).join('');

    qsa('[data-address-delete]', list).forEach((btn) => {
      btn.addEventListener('click', async () => {
        setBusy(btn, true);
        try {
          await account.deleteAddress(btn.dataset.addressDelete);
          toast('Address removed.', { type: 'info' });
          loadAddresses();
        } catch (err) { notifyError(err); setBusy(btn, false); }
      });
    });
    qsa('[data-address-edit]', list).forEach((btn) => {
      btn.addEventListener('click', () => {
        const address = items.find((a) => String(a.id) === btn.dataset.addressEdit);
        openAddressForm(address);
      });
    });
  } catch (err) {
    list.innerHTML = `<p class="alert alert--error">${esc(err.message)}</p>`;
  }
}

function openAddressForm(address = null) {
  const form = qs('[data-address-form]');
  clearErrors(form);
  form.hidden = false;
  form.querySelector('[data-address-form-title]').textContent = address ? 'Edit address' : 'New address';
  form.querySelector('[name="id"]').value = address?.id || '';
  ['label', 'recipient_name', 'phone', 'line1', 'line2', 'city', 'area', 'postal_code'].forEach((key) => {
    const input = form.querySelector(`[name="${key}"]`);
    if (input) input.value = address?.[key] || '';
  });
  const stateSelect = form.querySelector('[name="state"]');
  if (stateSelect) {
    if (!stateSelect.options.length || stateSelect.options.length < 5) fillStates(stateSelect);
    stateSelect.value = address?.state || session.user?.state || '';
  }
  form.querySelector('[name="is_default"]').checked = Boolean(address?.is_default);
  form.querySelector('input').focus();
  form.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

qs('[data-address-new]')?.addEventListener('click', () => openAddressForm(null));
qs('[data-address-cancel]')?.addEventListener('click', () => { qs('[data-address-form]').hidden = true; });

qs('[data-address-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const data = new FormData(form);
  const payload = {
    label: data.get('label') || '',
    recipient_name: data.get('recipient_name'),
    phone: data.get('phone'),
    line1: data.get('line1'),
    line2: data.get('line2') || '',
    city: data.get('city'),
    state: data.get('state'),
    area: data.get('area') || '',
    postal_code: data.get('postal_code') || '',
    country: 'NG',
    is_default: data.get('is_default') === 'on'
  };
  let valid = true;
  ['recipient_name', 'phone', 'line1', 'city', 'state'].forEach((field) => {
    if (!String(payload[field] || '').trim()) { fieldError(form, field, 'This field is required.'); valid = false; }
  });
  if (payload.phone && validate.phone(payload.phone)) { fieldError(form, 'phone', 'Enter a valid phone number.'); valid = false; }
  if (!valid) return;

  const id = data.get('id');
  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true);
  try {
    if (id) await account.updateAddress(id, payload);
    else await account.createAddress(payload);
    toast('Address saved.', { type: 'success' });
    form.hidden = true;
    loadAddresses();
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    notifyError(err);
  } finally {
    setBusy(button, false);
  }
});

/* ------------------------------------------------------------------ profile */
function fillProfile() {
  const user = session.user || {};
  const form = qs('[data-profile-form]');
  if (!form) return;
  form.querySelector('[name="first_name"]').value = user.first_name || '';
  form.querySelector('[name="last_name"]').value = user.last_name || '';
  form.querySelector('[name="email"]').value = user.email || '';
  form.querySelector('[name="phone"]').value = user.phone || '';
}

qs('[data-profile-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const data = new FormData(form);
  const button = form.querySelector('button[type="submit"]');
  const success = qs('[data-profile-success]');
  setBusy(button, true);
  try {
    await account.updateProfile({
      first_name: data.get('first_name'),
      last_name: data.get('last_name'),
      phone: data.get('phone')
    });
    await session.load();
    if (success) { success.hidden = false; setTimeout(() => { success.hidden = true; }, 4000); }
    toast('Profile updated.', { type: 'success' });
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    notifyError(err);
  } finally {
    setBusy(button, false);
  }
});

/* ------------------------------------------------------------ notifications */
async function loadNotifications() {
  const list = qs('[data-notifications]');
  list.innerHTML = '<li class="muted small">Loading notifications…</li>';
  try {
    const data = await account.notifications();
    const items = Array.isArray(data) ? data : (data?.results || []);
    list.innerHTML = items.length ? items.map((note) => `<li class="notif ${note.is_read ? '' : 'notif--unread'}">
      <svg class="icon icon--sm" aria-hidden="true"><use href="#i-bell"></use></svg>
      <div class="notif__body">
        <p class="notif__title">${esc(note.title || 'Update')}</p>
        <p class="notif__text">${esc(note.message || note.body || '')}</p>
        <span class="notif__time">${relativeTime(note.created_at)}</span>
      </div>
      ${note.is_read ? '' : `<button class="btn btn--link" type="button" data-notif-read="${esc(note.id)}">Mark read</button>`}
    </li>`).join('') : '<li class="muted">No notifications yet. Order and delivery updates will appear here.</li>';

    qsa('[data-notif-read]', list).forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await account.readNotification(btn.dataset.notifRead);
          loadNotifications();
        } catch (err) { notifyError(err); }
      });
    });
  } catch (err) {
    list.innerHTML = `<li class="alert alert--error">${esc(err.message)}</li>`;
  }
}

qs('[data-notifications-read-all]')?.addEventListener('click', async (event) => {
  setBusy(event.currentTarget, true);
  try {
    await account.readAllNotifications();
    loadNotifications();
  } catch (err) { notifyError(err); } finally { setBusy(event.currentTarget, false); }
});

qs('[data-prefs-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const success = qs('[data-prefs-success]');
  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true);
  try {
    await account.updatePreferences({
      order_updates: data.get('order_updates') === 'on',
      promotions: data.get('promotions') === 'on',
      price_drops: data.get('price_drops') === 'on'
    });
    if (success) { success.hidden = false; setTimeout(() => { success.hidden = true; }, 4000); }
  } catch (err) { notifyError(err); } finally { setBusy(button, false); }
});

/* ----------------------------------------------------------------- security */
qs('[data-password-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  clearErrors(form);
  const data = new FormData(form);
  const current = String(data.get('current_password') || '');
  const next = String(data.get('new_password') || '');
  const confirm = String(data.get('confirm_password') || '');
  let valid = true;
  if (!current) { fieldError(form, 'current_password', 'Enter your current password.'); valid = false; }
  if (validate.minLen(next, 8, 'Your new password')) { fieldError(form, 'new_password', validate.minLen(next, 8, 'Your new password')); valid = false; }
  if (next !== confirm) { fieldError(form, 'confirm_password', 'The passwords do not match.'); valid = false; }
  if (!valid) return;

  const button = form.querySelector('button[type="submit"]');
  const success = qs('[data-password-success]');
  setBusy(button, true);
  try {
    await auth.changePassword({ current_password: current, new_password: next });
    form.reset();
    if (success) { success.hidden = false; setTimeout(() => { success.hidden = true; }, 5000); }
    toast('Password updated.', { type: 'success' });
  } catch (err) {
    if (err.fields) Object.entries(err.fields).forEach(([f, m]) => fieldError(form, f, m));
    notifyError(err);
  } finally { setBusy(button, false); }
});

qs('[data-logout]')?.addEventListener('click', async () => {
  await session.signOut();
  window.location.href = sitePath('index.html');
});

/* --------------------------------------------------------------------- boot */
async function init() {
  await ready;
  if (!session.isAuthenticated) {
    if (layout) layout.hidden = true;
    if (guestAlert) guestAlert.hidden = false;
    if (titleEl) titleEl.textContent = 'Your account';
    if (subEl) subEl.textContent = 'Sign in to see your orders, addresses and notifications.';
    return;
  }
  if (layout) layout.hidden = false;
  if (guestAlert) guestAlert.hidden = true;
  if (titleEl) titleEl.textContent = `Hello, ${session.displayName.split(' ')[0] || 'there'}`;
  if (subEl) subEl.textContent = session.user?.email || '';
  initTabs();
  fillProfile();
  loadOverview();
}

init();
