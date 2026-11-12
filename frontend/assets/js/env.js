/**
 * Normalised, read-only view of the runtime configuration.
 * A <meta name="starmond-*"> value always wins over assets/js/config.js so a
 * deployment can inject configuration without rewriting application code.
 */
function meta(name) {
  const el = document.querySelector(`meta[name="${name}"]`);
  return el ? el.getAttribute('content') : '';
}

const raw = window.STARMOND_CONFIG || {};

export const CONFIG = Object.freeze({
  API_BASE_URL: (meta('starmond-api-base') || raw.API_BASE_URL || '').replace(/\/+$/, ''),
  SITE_URL: (meta('starmond-site-url') || raw.SITE_URL || '').replace(/\/+$/, ''),
  PAYSTACK_PUBLIC_KEY: meta('starmond-paystack-key') || raw.PAYSTACK_PUBLIC_KEY || '',
  ENVIRONMENT: raw.ENVIRONMENT || 'production',
  API_VERSION: raw.API_VERSION || 'v1',
  USE_PRETTY_PRODUCT_URLS: Boolean(raw.USE_PRETTY_PRODUCT_URLS),
  CART_TOKEN_KEY: raw.CART_TOKEN_KEY || 'starmond_cart_token',
  ACCESS_TOKEN_KEY: raw.ACCESS_TOKEN_KEY || 'starmond_access_token',
  REFRESH_TOKEN_KEY: raw.REFRESH_TOKEN_KEY || 'starmond_refresh_token',
  WISHLIST_KEY: raw.WISHLIST_KEY || 'starmond_wishlist',
  CHECKOUT_DRAFT_KEY: raw.CHECKOUT_DRAFT_KEY || 'starmond_checkout_draft',
  BUY_NOW_KEY: raw.BUY_NOW_KEY || 'starmond_buy_now',
  REQUEST_TIMEOUT_MS: raw.REQUEST_TIMEOUT_MS || 20000,
  PRODUCTS_PER_PAGE: raw.PRODUCTS_PER_PAGE || 12
});

/** True when no backend is configured: sample data + visible banner. */
export const IS_DEMO = window.__STARMOND_BOOT__ ? window.__STARMOND_BOOT__.demo : !CONFIG.API_BASE_URL;

export const API_ROOT = CONFIG.API_BASE_URL
  ? `${CONFIG.API_BASE_URL}/api/${CONFIG.API_VERSION}`
  : `/api/${CONFIG.API_VERSION}`;
