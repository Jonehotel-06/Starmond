/* ============================================================================
   Service worker — STARMOND TECHNOLOGY LIMITED
 *
 * Caching policy (deliberately conservative):
 *   • Precache: the offline page and the app shell's static CSS/JS/icons.
 *   • Runtime cache: same-origin STATIC assets only (stale-while-revalidate).
 *   • NEVER cached: any /api/ request, any HTML for cart/checkout/account/
 *     orders/payments/admin, and any response to a non-GET request.
 *   • Navigations: network-first with a short timeout, offline fallback page.
 *
 * A cached page can never claim an order or payment succeeded: those pages are
 * not cached at all and always require a live backend verification.
 * ========================================================================== */

const VERSION = 'starmond-v1.0.0';
const STATIC_CACHE = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;

const PRECACHE = [
  '/offline.html',
  '/assets/css/variables.css',
  '/assets/css/typography.css',
  '/assets/css/main.css',
  '/assets/css/components.css',
  '/assets/css/skeletons.css',
  '/assets/css/pages/storefront.css',
  '/assets/css/responsive.css',
  '/assets/js/config.js',
  '/assets/icons/favicon.svg',
  '/assets/icons/icon-192.png',
  '/manifest.webmanifest',
];

/** Paths that must never be served from a cache. */
const PRIVATE_PATH = /^\/(admin|api)(\/|$)|^\/(cart|checkout|account|orders|order-detail|wishlist|login|register|reset-password|forgot-password|verify-email|payment-success|payment-failed|payment-pending|track-order)\.html/;

const STATIC_EXT = /\.(css|js|mjs|svg|png|jpg|jpeg|webp|avif|gif|woff2?|webmanifest)$/i;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never intercept the API or private surfaces.
  if (PRIVATE_PATH.test(url.pathname) || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (STATIC_EXT.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request));
  }
});

async function networkFirstNavigation(request) {
  const url = new URL(request.url);
  if (PRIVATE_PATH.test(url.pathname)) return fetch(request);
  try {
    const response = await fetch(request);
    if (response.ok && response.type === 'basic') {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match('/offline.html');
    return offline || new Response('You are offline.', {
      status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request).then((response) => {
    if (response.ok && response.type === 'basic') cache.put(request, response.clone());
    return response;
  }).catch(() => null);
  return cached || (await network) || new Response('', { status: 504 });
}
