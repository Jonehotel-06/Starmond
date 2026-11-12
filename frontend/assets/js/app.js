/**
 * Storefront shell: header behaviour, search suggestions, cart/wishlist badges,
 * delegated product actions, session UI and Service Worker registration.
 * Imported by every public page.
 */
import { CONFIG, IS_DEMO } from './env.js';
import { catalog, checkout } from './api.js';
import { session, cart, wishlist, bus, initStores } from './store.js';
import { productRegistry } from './ui/cards.js';
import { toast, notifyError } from './ui/toast.js';
import { debounce, esc, money, qs, qsa, sessionStore, sitePath } from './utils.js';

/* -------------------------------------------------------------- demo banner */
function initDemoBanner() {
  const banner = qs('[data-demo-banner]');
  if (!banner) return;
  if (IS_DEMO) banner.hidden = false;
}

/* ------------------------------------------------------------ mobile nav */
function initNav() {
  const toggle = qs('[data-nav-toggle]');
  const nav = qs('#primary-nav');
  if (!toggle || !nav) return;
  const setOpen = (open) => {
    nav.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  };
  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  nav.addEventListener('click', (event) => { if (event.target.closest('a')) setOpen(false); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      setOpen(false);
      toggle.focus();
    }
  });
  window.addEventListener('resize', debounce(() => {
    if (window.innerWidth > 860) setOpen(false);
  }, 150));
}

/* ------------------------------------------------------- search suggestions */
function initSearch() {
  const form = qs('[data-search-form]');
  const input = qs('[data-search-input]');
  const panel = qs('[data-search-suggest]');
  if (!form || !input || !panel) return;

  let controller = null;
  let activeIndex = -1;
  let items = [];

  const close = () => {
    panel.hidden = true;
    panel.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
    items = [];
  };

  const render = (results, term) => {
    if (!results.length) {
      panel.innerHTML = `<p class="suggest__empty">No matches for “${esc(term)}”. Try a broader term.</p>`;
    } else {
      panel.innerHTML = results.slice(0, 6).map((item, i) => `
        <a class="suggest__item" role="option" id="suggest-${i}" aria-selected="false"
           href="${sitePath('product.html')}?slug=${encodeURIComponent(item.slug || '')}">
          ${item.primary_image ? `<img class="suggest__thumb" src="${esc(item.primary_image)}" alt="" width="38" height="38" loading="lazy">` : ''}
          <span>
            <span class="suggest__name">${esc(item.name)}</span><br>
            <span class="suggest__meta">${item.price !== undefined ? money(item.price) : ''}${item.category?.name ? ` · ${esc(item.category.name)}` : ''}</span>
          </span>
        </a>`).join('');
    }
    panel.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    items = Array.from(panel.querySelectorAll('.suggest__item'));
  };

  const search = debounce(async (term) => {
    controller?.abort();
    controller = new AbortController();
    try {
      const data = await catalog.suggestions(term, controller.signal);
      const results = Array.isArray(data) ? data : (data?.results || []);
      if (input.value.trim().length >= 2) render(results, term);
    } catch (err) {
      if (err?.code !== 'AbortError' && err?.name !== 'AbortError') close();
    }
  }, 220);

  input.addEventListener('input', () => {
    const term = input.value.trim();
    if (term.length < 2) { close(); return; }
    search(term);
  });

  input.addEventListener('keydown', (event) => {
    if (panel.hidden || !items.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = event.key === 'ArrowDown'
        ? Math.min(activeIndex + 1, items.length - 1)
        : Math.max(activeIndex - 1, 0);
      items.forEach((el, i) => el.setAttribute('aria-selected', String(i === activeIndex)));
      input.setAttribute('aria-activedescendant', items[activeIndex].id);
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      items[activeIndex].click();
    } else if (event.key === 'Escape') {
      close();
    }
  });

  form.addEventListener('submit', (event) => {
    const term = input.value.trim();
    if (!term) { event.preventDefault(); input.focus(); return; }
    input.value = term;
  });

  document.addEventListener('click', (event) => {
    if (!form.contains(event.target)) close();
  });
  document.addEventListener('focusin', (event) => {
    if (!form.contains(event.target)) close();
  });
}

/* ------------------------------------------------------------------ badges */
function initBadges() {
  const cartBadge = qs('[data-cart-count]');
  const wishBadge = qs('[data-wishlist-count]');
  const renderCount = (el, count) => {
    if (!el) return;
    el.textContent = count > 99 ? '99+' : String(count);
    el.hidden = !count;
  };
  const renderWish = () => renderCount(wishBadge, wishlist.count);
  bus.on('cart', (state) => renderCount(cartBadge, state.count));
  bus.on('wishlist', renderWish);
  renderWish();
  const cartLink = qs('.header-actions__cart');
  if (cartLink) {
    bus.on('cart', (state) => {
      cartLink.setAttribute('aria-label', `Shopping cart, ${state.count} item${state.count === 1 ? '' : 's'}`);
    });
  }
}

/* --------------------------------------------------------- session-aware UI */
function initSessionUi() {
  const label = qs('[data-auth-label]');
  const accountLink = qs('[data-auth-href]');
  const render = () => {
    if (label) label.textContent = session.isAuthenticated ? (session.displayName.split(' ')[0] || 'Account') : 'Sign in';
    if (accountLink && session.isAuthenticated) accountLink.setAttribute('href', sitePath('account.html'));
    qsa('[data-staff-only]').forEach((el) => { el.hidden = !session.isStaff; });
  };
  bus.on('session', render);
  render();
  window.addEventListener('starmond:session-expired', () => {
    toast('Your session expired. Please sign in again to continue.', { type: 'warn' });
  });
}

/* --------------------------------------------- delegated product actions */
async function addToCartFromCard(card, button) {
  const product = productRegistry.get(String(card.dataset.productId));
  if (!product) return;
  button.disabled = true;
  try {
    await cart.add({ product_id: product.id, quantity: 1 });
    toast(`${product.name} added to your cart.`, { type: 'success' });
  } catch (err) {
    notifyError(err);
  } finally {
    button.disabled = false;
  }
}

async function buyNowFromCard(card, button) {
  const product = productRegistry.get(String(card.dataset.productId));
  if (!product) return;
  button.disabled = true;
  try {
    const data = await checkout.buyNow({ product_id: product.id, quantity: 1 });
    sessionStore(CONFIG.BUY_NOW_KEY, {
      token: data?.buy_now_token || data?.token || null,
      subtotal: data?.subtotal ?? null,
      line_items: data?.line_items || data?.items || [],
      created: Date.now(),
      product_slug: product.slug,
      display_only: true
    });
    window.location.href = `${sitePath('checkout.html')}?mode=buy_now`;
  } catch (err) {
    notifyError(err);
    button.disabled = false;
  }
}

async function toggleWishlistFromCard(card, button) {
  const product = productRegistry.get(String(card.dataset.productId));
  if (!product) return;
  try {
    const { added } = await wishlist.toggle(product);
    button.setAttribute('aria-pressed', String(added));
    button.setAttribute('aria-label', added ? 'Remove from wishlist' : 'Save to wishlist');
    toast(added ? 'Saved to your wishlist.' : 'Removed from your wishlist.', { type: added ? 'success' : 'info' });
  } catch (err) {
    notifyError(err);
  }
}

function initDelegatedActions() {
  document.addEventListener('click', (event) => {
    const wishBtn = event.target.closest('.p-card [data-wishlist-toggle]');
    if (wishBtn) {
      event.preventDefault();
      toggleWishlistFromCard(wishBtn.closest('.p-card'), wishBtn);
      return;
    }
    const addBtn = event.target.closest('.p-card [data-add-to-cart]');
    if (addBtn) { event.preventDefault(); addToCartFromCard(addBtn.closest('.p-card'), addBtn); return; }
    const buyBtn = event.target.closest('.p-card [data-buy-now]');
    if (buyBtn) { event.preventDefault(); buyNowFromCard(buyBtn.closest('.p-card'), buyBtn); }
  });
}

/* -------------------------------------------------------- offline / online */
function initConnectivity() {
  window.addEventListener('online', () => toast('You are back online.', { type: 'success' }));
  window.addEventListener('offline', () => toast('You are offline. Prices and checkout need a connection.', { type: 'warn', timeout: 8000 }));
  const retry = qs('[data-retry-connection]');
  retry?.addEventListener('click', () => window.location.reload());
}

/* -------------------------------------------------------------------- PWA */
function initServiceWorker() {
  if (!('serviceWorker' in navigator) || IS_DEMO === null) return;
  if (!/^https?:$/.test(window.location.protocol)) return;
  window.addEventListener('load', () => {
    const url = sitePath('sw.js');
    navigator.serviceWorker.register(url, { scope: sitePath('') || '/' }).catch((err) => {
      console.warn('[starmond] Service worker registration skipped:', err?.message);
    });
  });
}

/* ------------------------------------------------------------------- boot */
export async function bootShell() {
  initDemoBanner();
  initNav();
  initSearch();
  initBadges();
  initDelegatedActions();
  initConnectivity();
  initServiceWorker();
  await initStores();
  initSessionUi();
  return { session, cart, wishlist };
}

/* Helper used by pages that need a signed-in customer. */
export function requireAuth(nextPath) {
  if (session.isAuthenticated) return true;
  const here = nextPath || window.location.pathname + window.location.search;
  window.location.href = `${sitePath('login.html')}?next=${encodeURIComponent(here)}`;
  return false;
}

/** Resolves when the shell, session, cart and wishlist state are ready.
    Page modules `await ready` before their first render. */
export const ready = bootShell();

window.starmond = { ready, session, cart, wishlist, toast };
