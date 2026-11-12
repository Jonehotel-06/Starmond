/**
 * Administration shell: staff authentication gate, permission-aware navigation
 * and hash routing between the views in ./views.js.
 *
 * Nothing is rendered that the backend has not returned. Routes the account is
 * not permitted to open show an explicit message instead of pretending to load.
 */
import '../app.js';
import { ready } from '../app.js';
import { session } from '../store.js';
import { notifyError } from '../ui/toast.js';
import { closeModal } from '../ui/modal.js';
import { qs, qsa, setBusy } from '../utils.js';
import { views, VIEW_META } from './views.js';

const gate = qs('[data-admin-gate]');
const gateMessage = qs('[data-admin-gate-message]');
const viewRoot = qs('[data-admin-view]');
const titleEl = qs('[data-admin-title]');
const subtitleEl = qs('[data-admin-subtitle]');
const sidebar = qs('#admin-sidebar');
const navToggle = qs('[data-admin-nav-toggle]');

let pendingOptions = {};
let currentView = 'dashboard';

/* ------------------------------------------------------------------- gate */
function showGate(message) {
  if (!gate) return;
  gate.hidden = false;
  if (message && gateMessage) gateMessage.textContent = message;
  document.body.style.overflow = 'hidden';
  qs('#ag-email')?.focus();
}

function hideGate() {
  if (gate) gate.hidden = true;
  document.body.style.overflow = '';
}

qs('[data-admin-login]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const errorEl = form.querySelector('[data-admin-login-error]');
  errorEl.hidden = true;
  const data = new FormData(form);
  const email = String(data.get('email') || '').trim();
  const password = String(data.get('password') || '');
  const button = form.querySelector('button[type="submit"]');
  setBusy(button, true, 'Signing in…');
  try {
    await session.signIn({ email, password });
    if (!session.isStaff) {
      await session.signOut();
      errorEl.textContent = 'That account is a customer account and cannot open the dashboard. Sign in with a staff account.';
      errorEl.hidden = false;
      setBusy(button, false);
      return;
    }
    hideGate();
    paintUser();
    filterNav();
    route();
  } catch (err) {
    errorEl.textContent = err.status === 401
      ? 'Those credentials were not accepted. Check the email and password.'
      : err.message;
    errorEl.hidden = false;
    setBusy(button, false);
  }
});

qs('[data-admin-signout]')?.addEventListener('click', async () => {
  await session.signOut();
  window.location.reload();
});

/* -------------------------------------------------------------------- nav */
function paintUser() {
  const user = session.user || {};
  const wrap = qs('[data-admin-user]');
  if (wrap) wrap.hidden = !session.user;
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.name || user.email || '';
  qs('[data-admin-name]') && (qs('[data-admin-name]').textContent = name || 'Staff');
  qs('[data-admin-role]') && (qs('[data-admin-role]').textContent = String(user.role || 'staff'));
  const initials = (name || 'ST').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  qs('[data-admin-initials]') && (qs('[data-admin-initials]').textContent = initials || 'ST');
}

function filterNav() {
  qsa('[data-perm]').forEach((link) => {
    link.hidden = !session.can(link.dataset.perm);
  });
}

function markActive(name) {
  qsa('[data-admin-link]').forEach((link) => {
    if (link.dataset.adminLink === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function openSidebar(open) {
  if (!sidebar) return;
  sidebar.classList.toggle('is-open', open);
  navToggle?.setAttribute('aria-expanded', String(open));
}

navToggle?.addEventListener('click', () => openSidebar(!sidebar.classList.contains('is-open')));
qs('[data-admin-nav-close]')?.addEventListener('click', () => openSidebar(false));
qsa('[data-admin-link]').forEach((link) => link.addEventListener('click', () => {
  if (window.innerWidth <= 980) openSidebar(false);
}));

/* ----------------------------------------------------------------- router */
function parseRoute() {
  const raw = (window.location.hash || '#/dashboard').replace(/^#\/?/, '');
  const name = raw.split('?')[0].split('/')[0] || 'dashboard';
  return views[name] ? name : 'dashboard';
}

const ctx = {
  navigate(name, options = {}) {
    const target = `#/${name}`;
    pendingOptions = options;
    if (window.location.hash === target) route();
    else window.location.hash = target;
  },
  setSubtitle(text) { if (subtitleEl) subtitleEl.textContent = text; },
  get options() { return pendingOptions; }
};

async function route() {
  /* A dialog left open by the previous module must never sit over the next one. */
  if (!document.querySelector('[data-modal]')?.hidden) closeModal();
  const name = parseRoute();
  const meta = VIEW_META[name] || { title: name, permission: null };
  currentView = name;
  markActive(name);
  if (titleEl) titleEl.textContent = meta.title;
  if (subtitleEl) subtitleEl.textContent = 'Loading…';

  if (meta.permission && !session.can(meta.permission)) {
    if (subtitleEl) subtitleEl.textContent = '';
    viewRoot.innerHTML = `<section class="panel"><div class="panel__body">
      <div class="alert alert--warn" role="alert"><div>
        <p><strong>You do not have access to ${meta.title.toLowerCase()}.</strong></p>
        <p class="small">Your account does not include the <code>${meta.permission}</code> permission. Ask the business owner to update your role if you need it.</p>
        <button class="btn btn--outline btn--sm" type="button" data-goto-dash>Back to the dashboard</button>
      </div></div></div></section>`;
    viewRoot.querySelector('[data-goto-dash]')?.addEventListener('click', () => ctx.navigate('dashboard'));
    return;
  }

  try {
    await views[name](viewRoot, ctx);
    if (subtitleEl && subtitleEl.textContent === 'Loading…') subtitleEl.textContent = '';
  } catch (err) {
    notifyError(err);
    viewRoot.innerHTML = `<section class="panel"><div class="panel__body">
      <div class="alert alert--error" role="alert"><div>
        <p><strong>${meta.title} could not be loaded.</strong></p>
        <p class="small">${err.message}</p>
        <button class="btn btn--outline btn--sm" type="button" data-retry-view>Try again</button>
      </div></div></div></section>`;
    viewRoot.querySelector('[data-retry-view]')?.addEventListener('click', route);
  } finally {
    pendingOptions = {};
  }
}

window.addEventListener('hashchange', route);
qs('[data-admin-refresh]')?.addEventListener('click', () => route());

/* ------------------------------------------------------------------- boot */
async function init() {
  await ready;
  paintUser();
  if (!session.isAuthenticated || !session.isStaff) {
    filterNav();
    showGate(session.isAuthenticated
      ? 'This account is not a staff account. Sign in with a staff account to continue.'
      : undefined);
    return;
  }
  hideGate();
  filterNav();
  route();
}

init();
