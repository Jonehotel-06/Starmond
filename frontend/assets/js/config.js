/**
 * STARMOND TECHNOLOGY LIMITED — runtime configuration.
 *
 * This is the ONLY place deployment-specific values live. Replace the values
 * below (or inject them at deploy time) — never hardcode a backend URL inside
 * application modules, and never put secret keys here: this file is public.
 *
 * Deployment note: if the host can rewrite files, generate this file with the
 * real values. If it cannot, set the values in <meta> tags in the page <head>
 * (see assets/js/env.js) — a <meta> value always wins over this file.
 */
window.STARMOND_CONFIG = {
  /* Base URL of the Django REST Framework deployment, WITHOUT a trailing slash.
     Example: "https://api.starmondtechnology.com"
     Leave empty to run in demo mode (sample data, no API calls). */
  API_BASE_URL: '',

  /* Public site origin, used for canonical URLs and share links. */
  SITE_URL: 'https://www.starmondtechnology.com',

  /* Paystack PUBLIC key only. Payment initialisation still happens server-side. */
  PAYSTACK_PUBLIC_KEY: '',

  /* "production" | "staging" | "development" */
  ENVIRONMENT: 'production',

  /* Hosts where the storefront is expected to serve real traffic. Outside this
     list (and with no API_BASE_URL) the site runs in demo mode with a visible
     sample-data banner so it can never be mistaken for live business data. */
  PRODUCTION_HOSTS: ['www.starmondtechnology.com', 'starmondtechnology.com'],

  API_VERSION: 'v1',

  /* When the backend serves the server-rendered route /product/<slug>/ (see
     reports/SEO_STRATEGY.md), set this to true so every internal product link
     points at the crawlable pretty URL instead of product.html?slug=… */
  USE_PRETTY_PRODUCT_URLS: false,
  CART_TOKEN_KEY: 'starmond_cart_token',
  ACCESS_TOKEN_KEY: 'starmond_access_token',
  REFRESH_TOKEN_KEY: 'starmond_refresh_token',
  WISHLIST_KEY: 'starmond_wishlist',
  CHECKOUT_DRAFT_KEY: 'starmond_checkout_draft',
  BUY_NOW_KEY: 'starmond_buy_now',
  REQUEST_TIMEOUT_MS: 20000,
  PRODUCTS_PER_PAGE: 12
};
