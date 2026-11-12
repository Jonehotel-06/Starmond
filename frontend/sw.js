/* ==========================================================================
   STARMOND TECHNOLOGY LIMITED — service worker
   Strategy
     • Pre-cache the shell: CSS, JS modules, brand images, offline page.
     • Navigations: network first, fall back to cache, then /offline.html.
     • Static assets: stale-while-revalidate.
     • NEVER cache API traffic, checkout, account, order or payment responses.
   ========================================================================== */
const VERSION = 'starmond-v1.0.0';
const SHELL_CACHE = `${VERSION}-shell`;
const RUNTIME_CACHE = `${VERSION}-runtime`;

const SHELL = [
  './',
  './index.html',
  './offline.html',
  './shop.html',
  './assets/css/main.css',
  './assets/css/admin.css',
  './assets/js/config.js',
  './assets/js/boot.js',
  './assets/js/app.js',
  './assets/js/env.js',
  './assets/js/api.js',
  './assets/js/utils.js',
  './assets/js/store.js',
  './assets/js/seo.js',
  './assets/js/ui/toast.js',
  './assets/js/ui/modal.js',
  './assets/js/ui/cards.js',
  './assets/js/ui/feedback.js',
  './assets/js/ui/timeline.js',
  './assets/img/favicon.svg',
  './assets/img/icon-192.png',
  './assets/img/icon-512.png'
];

/* Paths that must never be cached, even momentarily. */
const PRIVATE = [
  '/checkout', '/payment-callback', '/order', '/account', '/wishlist',
  '/cart', '/login', '/register', '/admin', '/api/', '/track-order'
];

function isPrivate(url) {
  return PRIVATE.some((fragment) => url.pathname.includes(fragment)) || url.searchParams.has('reference');
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL.map((path) => new Request(path, { cache: 'reload' }))))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isPrivate(url)) return; /* private data always goes to the network */

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined);
          return response;
        })
        .catch(async () => (await caches.match(request)) || caches.match('./offline.html'))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok && (url.pathname.endsWith('.css') || url.pathname.endsWith('.js')
              || url.pathname.match(/\.(svg|png|jpg|jpeg|webp|woff2?)$/))) {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined);
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
