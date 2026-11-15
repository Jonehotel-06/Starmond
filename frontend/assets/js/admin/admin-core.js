/**
 * admin-core.js — administration shell.
 *
 * Permission checks here are PRESENTATION ONLY. They hide or disable controls
 * the backend says the user may not use. Every request is still authorized
 * server-side; a hidden button is never a security control.
 */

import { initAuth, isAuthenticated, getUser, can, logout, isStaff } from '../auth.js';
import { createDrawer, trapFocus, toast, openDialog, emptyState } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { esc, $, $$ } from '../utils.js';
import { registerServiceWorker } from '../pwa.js';
import { initLiveRegions } from '../ui.js';

let ready = false;
let booting = null;

export async function initAdmin(options = {}) {
  if (ready) return true;
  if (booting) return booting;
  booting = runInitAdmin(options).finally(() => { booting = null; });
  return booting;
}

async function runInitAdmin({ permission = null } = {}) {
  hydrateIcons(document);
  initLiveRegions();
  initPreviewBanner();

  // Admin is a protected surface: always ask the backend authoritatively.
  await initAuth({ force: true });

  if (!isAuthenticated()) {
    window.location.assign(`/login.html?next=${encodeURIComponent(location.pathname + location.search)}`);
    return false;
  }

  if (!isStaff()) {
    renderNoAccess('This account does not have administration access.');
    return false;
  }

  applyPermissions();
  initSidebar();
  initProfileMenu();
  initGlobalSearch();
  registerServiceWorker();
  ready = true;
  return true;
}

function initPreviewBanner() {
  const config = window.STARMOND_CONFIG || {};
  if (!config.CONTRACT_PREVIEW || document.querySelector('[data-preview-banner]')) return;
  const banner = document.createElement('div');
  banner.dataset.previewBanner = 'true';
  banner.setAttribute('role', 'note');
  banner.style.cssText = 'background:#8A5A0A;color:#fff;font-size:12px;font-weight:600;padding:8px 16px;text-align:center;position:fixed;top:0;left:0;right:0;z-index:700';
  banner.textContent = config.CONTRACT_PREVIEW_LABEL || 'Contract preview — synthetic test data.';
  document.body.prepend(banner);
  document.querySelector('.admin-shell').style.paddingTop = '32px';
}

function renderNoAccess(message) {
  const content = $('.admin-content');
  if (!content) return;
  content.innerHTML = emptyState({
    title: 'Access denied',
    text: message,
    iconName: 'lock',
    actionHtml: '<a class="btn btn--primary btn--sm" href="/">Return to storefront</a><button type="button" class="btn btn--secondary btn--sm" data-admin-logout>Sign out</button>',
  });
  hydrateIcons(content);
  content.querySelector('[data-admin-logout]')?.addEventListener('click', async () => {
    await logout();
    window.location.assign('/login.html');
  });
}

/** Hide/disable controls the backend has not granted. */
export function applyPermissions(root = document) {
  root.querySelectorAll('[data-perm]').forEach((node) => {
    const permission = node.dataset.perm;
    if (can(permission)) {
      node.hidden = false;
      node.removeAttribute('aria-disabled');
      if ('disabled' in node) node.disabled = false;
      return;
    }
    if (node.dataset.permBehavior === 'disable') {
      node.setAttribute('aria-disabled', 'true');
      if ('disabled' in node) node.disabled = true;
      node.title = 'You do not have permission for this action';
    } else {
      node.hidden = true;
    }
  });
  // Hide sidebar section headings that have no visible links left.
  document.querySelectorAll('.admin-nav__group').forEach((group) => {
    const links = [...group.querySelectorAll('a[href]')];
    group.hidden = links.length > 0 && links.every((link) => link.hidden || link.closest('[hidden]'));
  });
}

function initSidebar() {
  const sidebar = $('[data-admin-sidebar]');
  const backdrop = $('[data-admin-backdrop]');
  const trigger = $('[data-admin-menu]');
  if (!sidebar || !backdrop || !trigger) return;

  if (window.matchMedia('(max-width: 1023px)').matches) {
    const drawer = createDrawer({ drawer: sidebar, backdrop, triggers: [trigger] });
    sidebar.querySelectorAll('[data-admin-close]').forEach((button) => button.addEventListener('click', () => drawer.close()));
  } else {
    sidebar.querySelectorAll('[data-admin-close]').forEach((button) => { button.hidden = true; });
  }

  $('[data-admin-logout]')?.addEventListener('click', async () => {
    await logout();
    window.location.assign('/login.html');
  });
}

function initProfileMenu() {
  const trigger = $('[data-admin-profile]');
  const menu = $('[data-admin-profile-menu]');
  if (!trigger || !menu) return;
  const user = getUser();
  let open = false;
  let release = null;

  menu.innerHTML = `
    <div class="menu__head">
      <span class="menu__name">${esc(user?.full_name || [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Administrator')}</span>
      <span class="t-meta">${esc(user?.email || '')}</span>
      <span class="t-meta">${esc(user?.is_superuser ? 'Super administrator' : (user?.role?.name || user?.role || 'Staff'))}</span>
    </div>
    <a class="menu__item" href="/account.html">${icon('user', { size: 'sm' })} My profile</a>
    <a class="menu__item" href="/admin/settings.html">${icon('settings', { size: 'sm' })} Business settings</a>
    <a class="menu__item" href="/" target="_blank" rel="noopener">${icon('external-link', { size: 'sm' })} View storefront</a>
    <div class="menu__divider"></div>
    <button type="button" class="menu__item" data-admin-logout-menu>${icon('log-out', { size: 'sm' })} Sign out</button>`;
  hydrateIcons(menu);

  const setOpen = (next) => {
    open = next;
    menu.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
    if (open) release = trapFocus(menu, { onEscape: () => { setOpen(false); trigger.focus(); } });
    else { release?.(); release = null; }
  };

  trigger.addEventListener('click', () => setOpen(!open));
  document.addEventListener('click', (event) => {
    if (open && !menu.contains(event.target) && !trigger.contains(event.target)) setOpen(false);
  });
  menu.querySelector('[data-admin-logout-menu]')?.addEventListener('click', async () => {
    await logout();
    window.location.assign('/login.html');
  });
}

function initGlobalSearch() {
  const input = $('[data-admin-search]');
  if (!input) return;
  input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    const query = input.value.trim();
    if (!query) return;
    // Route to the most likely module; each module also has its own search.
    const target = /^str[-_]/i.test(query) ? 'orders' : /^\d+$/.test(query) ? 'orders' : 'products';
    window.location.assign(`/admin/${target}.html?q=${encodeURIComponent(query)}`);
  });
}

/** Guard a page against a missing permission after auth resolves. */
export function guardPermission(permission) {
  if (!permission || can(permission)) return true;
  renderNoAccess('Your role does not include permission to view this module.');
  return false;
}

export { can, getUser, toast, openDialog, hydrateIcons, icon, esc, $, $$ };
export default initAdmin;
