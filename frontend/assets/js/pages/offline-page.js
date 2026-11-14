/**
 * offline-page.js — deliberately minimal. Makes no API calls.
 */
import { hydrateIcons, icon } from '../icons.js';
import { toast, initLiveRegions } from '../ui.js';
import { $ } from '../utils.js';

hydrateIcons(document);
initLiveRegions();

// This page must work with no network, so it deliberately does NOT call the
// API. The shared header/drawer still ship category placeholders, though —
// resolve them to a real offline fallback instead of leaving skeletons
// animating indefinitely.
const drawerCategories = $('[data-drawer-categories]');
if (drawerCategories) {
  drawerCategories.innerHTML = `<p class="t-sm t-muted" style="padding:var(--space-3)">
    Categories are unavailable offline. <a href="/shop.html">Browse the shop</a> when you reconnect.
  </p>`;
}
const megaContent = $('[data-mega-content]');
if (megaContent) megaContent.innerHTML = '';
document.querySelectorAll('[data-loading-region]').forEach((node) => node.setAttribute('aria-busy', 'false'));

document.querySelector('[data-retry-connection]')?.addEventListener('click', () => {
  if (navigator.onLine) {
    window.location.assign('/');
  } else {
    toast('Still offline. Reconnect to the internet and try again.', { type: 'warning' });
  }
});

window.addEventListener('online', () => {
  toast('Connection restored. Reloading…', { type: 'success', duration: 1500 });
  setTimeout(() => window.location.assign('/'), 1200);
});
