/**
 * navigation.js — header behaviour, mega menu, mobile drawer, account menu.
 *
 * The primary navigation links are present in the initial HTML so they are
 * crawlable without JavaScript. This module only enhances them and injects the
 * dynamic category tree, which is a progressive enhancement over the static
 * "Shop" link that already exists.
 */

import { getCategories, renderMegaMenu, renderDrawerCategories, renderFooterCategories } from './categories.js';
import { getSettings, applyBusinessIdentity } from './site.js';
import { initAuth, onAuthChange, isAuthenticated, getUser, logout, isStaff } from './auth.js';
import { initCartBadge } from './cart.js';
import { createDrawer, trapFocus, toast, announce } from './ui.js';
import { hydrateIcons, icon } from './icons.js';
import { esc, $, $$ } from './utils.js';
import { initSearch } from './search.js';

/* ============================================================================
   Mega menu (desktop)
   ========================================================================== */

function initMegaMenu() {
  const trigger = $('[data-mega-trigger]');
  const panel = $('[data-mega-panel]');
  if (!trigger || !panel) return;

  let open = false;
  let closeTimer = null;
  let loaded = false;
  let releaseFocus = null;

  const setOpen = async (next) => {
    if (next === open) return;
    open = next;
    trigger.setAttribute('aria-expanded', String(open));
    panel.hidden = !open;
    if (open) {
      if (!loaded) {
        loaded = true;
        panel.querySelector('[data-mega-content]').innerHTML =
          '<div class="mega__grid" aria-hidden="true">' +
          Array.from({ length: 4 }, () => `<div class="stack stack--sm">
            <span class="sk sk--text sk--w-60"></span>
            ${Array.from({ length: 5 }, () => '<span class="sk sk--text-sm sk--w-80"></span>').join('')}
          </div>`).join('') + '</div>';
        try {
          const tree = await getCategories();
          panel.querySelector('[data-mega-content]').innerHTML = renderMegaMenu(tree);
          hydrateIcons(panel);
        } catch {
          panel.querySelector('[data-mega-content]').innerHTML = renderMegaMenu([]);
          hydrateIcons(panel);
        }
      }
      announce('Categories menu expanded');
    } else {
      releaseFocus?.();
      releaseFocus = null;
    }
  };

  trigger.addEventListener('click', (event) => { event.preventDefault(); setOpen(!open); });
  trigger.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true).then(() => panel.querySelector('a')?.focus()); }
  });

  const wrapper = trigger.closest('[data-mega-wrapper]') || trigger.parentElement;
  wrapper.addEventListener('mouseenter', () => { clearTimeout(closeTimer); if (window.matchMedia('(hover:hover)').matches) setOpen(true); });
  wrapper.addEventListener('mouseleave', () => { closeTimer = setTimeout(() => setOpen(false), 180); });
  panel.addEventListener('mouseenter', () => clearTimeout(closeTimer));
  panel.addEventListener('mouseleave', () => { closeTimer = setTimeout(() => setOpen(false), 180); });

  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && open) { setOpen(false); trigger.focus(); } });
  document.addEventListener('click', (event) => { if (open && !wrapper.contains(event.target) && !panel.contains(event.target)) setOpen(false); });
  panel.addEventListener('focusout', (event) => {
    if (!panel.contains(event.relatedTarget) && event.relatedTarget !== trigger) setOpen(false);
  });
}

/* ============================================================================
   Mobile drawer
   ========================================================================== */

function initMobileDrawer() {
  const drawer = $('[data-mobile-drawer]');
  const backdrop = $('[data-drawer-backdrop]');
  const trigger = $('[data-menu-trigger]');
  if (!drawer || !backdrop || !trigger) return;

  const controller = createDrawer({ drawer, backdrop, triggers: [trigger] });

  const holder = drawer.querySelector('[data-drawer-categories]');
  if (holder) {
    getCategories()
      .then((tree) => { holder.innerHTML = renderDrawerCategories(tree); hydrateIcons(holder); })
      .catch(() => { holder.innerHTML = renderDrawerCategories([]); });
  }
  return controller;
}

/* ============================================================================
   Account menu
   ========================================================================== */

function renderAccountLinks(user) {
  const staffLink = isStaff()
    ? `<a class="menu__item" href="/admin/index.html">${icon('dashboard', { size: 'sm' })}Administration</a>`
    : '';
  return `
    <div class="menu__head">
      <span class="menu__name">${esc(user?.first_name || user?.full_name || user?.email || 'My account')}</span>
      <span class="t-meta t-clamp-1">${esc(user?.email || '')}</span>
    </div>
    <a class="menu__item" href="/account.html">${icon('user', { size: 'sm' })}Account overview</a>
    <a class="menu__item" href="/orders.html">${icon('package', { size: 'sm' })}My orders</a>
    <a class="menu__item" href="/wishlist.html">${icon('heart', { size: 'sm' })}Wishlist</a>
    <a class="menu__item" href="/account.html#addresses">${icon('map-pin', { size: 'sm' })}Addresses</a>
    ${staffLink}
    <div class="menu__divider"></div>
    <button type="button" class="menu__item" data-logout>${icon('log-out', { size: 'sm' })}Sign out</button>`;
}

function initAccountMenu() {
  const trigger = $('[data-account-trigger]');
  const menu = $('[data-account-menu]');
  if (!trigger || !menu) return;

  let open = false;
  let releaseFocus = null;

  const setOpen = (next) => {
    open = next;
    trigger.setAttribute('aria-expanded', String(open));
    menu.hidden = !open;
    if (open) {
      releaseFocus = trapFocus(menu, { onEscape: () => { setOpen(false); trigger.focus(); } });
    } else {
      releaseFocus?.(); releaseFocus = null;
    }
  };

  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    if (!isAuthenticated()) {
      window.location.assign(`/login.html?next=${encodeURIComponent(location.pathname + location.search)}`);
      return;
    }
    setOpen(!open);
  });

  document.addEventListener('click', (event) => {
    if (open && !menu.contains(event.target) && !trigger.contains(event.target)) setOpen(false);
  });

  menu.addEventListener('click', async (event) => {
    if (!event.target.closest('[data-logout]')) return;
    setOpen(false);
    await logout();
    toast('You have been signed out.', { type: 'success' });
    window.location.assign('/');
  });

  const render = () => {
    if (isAuthenticated()) {
      menu.innerHTML = renderAccountLinks(getUser());
      trigger.setAttribute('aria-label', 'Account menu');
      trigger.setAttribute('data-authenticated', 'true');
    } else {
      menu.innerHTML = `
        <div class="menu__head"><span class="menu__name">Welcome</span><span class="t-meta">Sign in for orders, wishlist and faster checkout.</span></div>
        <a class="menu__item" href="/login.html">${icon('log-in', { size: 'sm' })}Sign in</a>
        <a class="menu__item" href="/register.html">${icon('user-plus', { size: 'sm' })}Create account</a>
        <a class="menu__item" href="/track-order.html">${icon('truck', { size: 'sm' })}Track an order</a>`;
      trigger.setAttribute('aria-label', 'Sign in or create an account');
      trigger.removeAttribute('data-authenticated');
    }
    hydrateIcons(menu);
    $$('[data-auth-guest]').forEach((n) => { n.hidden = isAuthenticated(); });
    $$('[data-auth-user]').forEach((n) => { n.hidden = !isAuthenticated(); });
    $$('[data-user-name]').forEach((n) => { n.textContent = getUser()?.first_name || getUser()?.email || ''; });
  };

  onAuthChange(render);
  render();
}

/* ============================================================================
   Footer + identity
   ========================================================================== */

async function initFooterCategories() {
  const holder = $('[data-footer-categories]');
  if (!holder) return;
  try {
    const tree = await getCategories();
    holder.innerHTML = renderFooterCategories(tree);
  } catch {
    holder.innerHTML = '<li><a href="/shop.html">All products</a></li>';
  }
}

function markCurrentNav() {
  const path = location.pathname.replace(/\/index\.html$/, '/');
  $$('.main-nav__link, .drawer-nav__link').forEach((link) => {
    const href = link.getAttribute('href');
    if (!href) return;
    const target = href.replace(/\/index\.html$/, '/');
    const isCurrent = target === path || (target !== '/' && path.startsWith(target) && target.length > 1);
    if (isCurrent) link.setAttribute('aria-current', 'page');
  });
}

/* ============================================================================
   Contract-preview banner (never enabled in production)
   ========================================================================== */

function initPreviewBanner() {
  const config = window.STARMOND_CONFIG || {};
  if (!config.CONTRACT_PREVIEW) return;
  if (document.querySelector('[data-preview-banner]')) return;
  const banner = document.createElement('div');
  banner.dataset.previewBanner = 'true';
  banner.setAttribute('role', 'note');
  banner.style.cssText = 'background:#8A5A0A;color:#fff;font-size:12px;font-weight:600;padding:8px 16px;text-align:center;position:relative;z-index:700';
  banner.textContent = config.CONTRACT_PREVIEW_LABEL || 'Contract preview — synthetic test data. Not a live store.';
  document.body.prepend(banner);
}

/* ============================================================================
   Boot
   ========================================================================== */

export async function initShell({ auth = true } = {}) {
  hydrateIcons(document);
  initPreviewBanner();
  markCurrentNav();
  initMegaMenu();
  initMobileDrawer();
  initAccountMenu();
  initSearch();
  initCartBadge();
  initFooterCategories();

  // Identity and auth are independent; neither blocks the other.
  getSettings().then((settings) => { applyBusinessIdentity(settings); hydrateIcons(document); });
  if (auth) await initAuth();

  // Offline / online messaging.
  window.addEventListener('offline', () => toast('You are offline. Browsing cached pages only.', { type: 'warning', duration: 6000 }));
  window.addEventListener('online', () => toast('Back online.', { type: 'success', duration: 2500 }));
}

export { icon };
export default initShell;
