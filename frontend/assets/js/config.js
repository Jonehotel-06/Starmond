/**
 * config.js — PUBLIC, deployment-time configuration.
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ THIS FILE IS GENERATED. Do not hand-edit in a deployed environment.      │
 * │ Regenerate with:  node tools/write-config.mjs                            │
 * │ It reads API_BASE_URL (and friends) from the build environment / .env.   │
 * └──────────────────────────────────────────────────────────────────────────┘
 *
 * A browser cannot read a server-side .env file. The build step therefore
 * writes the *public* values here, and this module is loaded before api.js.
 *
 * SECURITY: only public values belong here. Never put a Paystack secret key,
 * Django SECRET_KEY, database credential or API token in this file — it is
 * served to every visitor.
 *
 * API_BASE_URL defaults to a SAME-ORIGIN relative path. That is deliberately
 * not a hardcoded backend host: production deployments either
 *   (a) reverse-proxy /api/ to Django (recommended — no CORS, cookies work), or
 *   (b) inject an absolute https://api.your-domain.example at build time.
 */
(function initStarmondConfig(global) {
  'use strict';

  var DEFAULTS = {
    /** Public REST root. Relative = same-origin reverse proxy. */
    API_BASE_URL: '/api',

    /** Canonical public origin of this storefront, e.g. https://starmond.example
     *  Empty string = derive from window.location.origin at runtime. */
    SITE_URL: '',

    /** 'session' (DRF session cookie + CSRF — the safer default) or 'token'
     *  (DRF TokenAuthentication header, for cross-site deployments where
     *  cookies cannot be used). 'jwt' is accepted as an alias of 'token'. */
    AUTH_MODE: 'session',

    /** Name of the CSRF cookie Django sets (django.middleware.csrf). */
    CSRF_COOKIE_NAME: 'csrftoken',
    CSRF_HEADER_NAME: 'X-CSRFToken',

    /** Request behaviour. */
    REQUEST_TIMEOUT_MS: 20000,
    RETRY_ATTEMPTS: 2,
    RETRY_BASE_DELAY_MS: 400,

    /** Public catalogue cache TTL (never used for cart/checkout/account). */
    PUBLIC_CACHE_TTL_MS: 60000,

    /** Search debounce, per the UX spec. */
    SEARCH_DEBOUNCE_MS: 300,

    /** Default currency; the API remains authoritative on every money value. */
    CURRENCY: 'NGN',
    LOCALE: 'en-NG',

    /** Paystack PUBLIC key is NOT needed: the backend initialises the
     *  transaction and returns an authorization_url we redirect to. */

    /** Set true only for a local contract-mock preview. Adds a persistent,
     *  unmistakable banner. MUST be false in production. */
    CONTRACT_PREVIEW: false,
    CONTRACT_PREVIEW_LABEL: 'Contract preview — synthetic test data from a local mock API. Not real products, prices or stock.',

    /** Service worker registration. */
    ENABLE_SW: true,

    /** Build stamp, replaced by the build tool for cache versioning. */
    BUILD_ID: 'dev'
  };

  var provided = global.STARMOND_CONFIG || {};

  // A <meta name="starmond:api-base" content="..."> tag allows an operator to
  // override the API root without a rebuild (useful for staging smoke tests).
  var metaOverride = null;
  if (typeof document !== 'undefined') {
    var meta = document.querySelector('meta[name="starmond:api-base"]');
    if (meta && meta.content) metaOverride = { API_BASE_URL: meta.content };
  }

  var merged = Object.assign({}, DEFAULTS, provided, metaOverride || {});

  // Normalise: strip a trailing slash so callers can always append '/path/'.
  if (typeof merged.API_BASE_URL === 'string') {
    merged.API_BASE_URL = merged.API_BASE_URL.replace(/\/+$/, '');
  }
  if (typeof merged.SITE_URL === 'string') {
    merged.SITE_URL = merged.SITE_URL.replace(/\/+$/, '');
  }

  global.STARMOND_CONFIG = Object.freeze(merged);
})(typeof window !== 'undefined' ? window : globalThis);
