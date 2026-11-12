/**
 * CENTRALISED API CLIENT — frontend/assets/js/api.js
 *
 * Every backend call in this storefront goes through this module. Nothing else
 * in the codebase is allowed to call fetch() against the API.
 *
 * Responsibilities
 *  - Build URLs from the runtime-configured API base (never hardcoded).
 *  - Attach authentication (Bearer access token) and the guest cart token.
 *  - JSON encode/decode, request timeout, single retry after a 401 refresh.
 *  - Normalise DRF responses (paginated or list) and DRF errors
 *    ({detail}, {"field": ["msg"]}) into one ApiError shape.
 *  - Delegate to the clearly-labelled sample-data module in demo mode only.
 *
 * The backend is the single source of truth for prices, stock, totals, order
 * state and permissions. This client never computes money or business state.
 */
import { CONFIG, API_ROOT, IS_DEMO } from './env.js';
import { stored, forget, store } from './utils.js';

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', fields = null, payload = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.payload = payload;
  }
  get isNetwork() { return this.status === 0; }
  get isAuth() { return this.status === 401 || this.status === 403; }
  get isValidation() { return this.status === 400 || this.status === 422; }
}

/* ------------------------------------------------------------------ tokens */
let refreshPromise = null;

export function getAccessToken() { return stored(CONFIG.ACCESS_TOKEN_KEY, null); }
export function getRefreshToken() { return stored(CONFIG.REFRESH_TOKEN_KEY, null); }

export function saveTokens({ access, refresh } = {}) {
  if (access) store(CONFIG.ACCESS_TOKEN_KEY, access);
  if (refresh) store(CONFIG.REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens() {
  forget(CONFIG.ACCESS_TOKEN_KEY);
  forget(CONFIG.REFRESH_TOKEN_KEY);
}

function cartToken() { return stored(CONFIG.CART_TOKEN_KEY, null); }

/* ------------------------------------------------------- helpers / shaping */
function buildUrl(path, params) {
  const clean = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${API_ROOT}${clean}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '' || value === false) return;
      if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v));
      else url.searchParams.set(key, String(value === true ? '1' : value));
    });
  }
  return url.toString();
}

function extractErrorMessage(payload, status) {
  if (!payload) return defaultMessageForStatus(status);
  if (typeof payload === 'string') return payload;
  if (payload.detail) return payload.detail;
  if (payload.message) return payload.message;
  const firstKey = Object.keys(payload)[0];
  if (firstKey) {
    const value = payload[firstKey];
    const text = Array.isArray(value) ? value[0] : String(value);
    return firstKey === 'non_field_errors' ? text : `${prettifyField(firstKey)}: ${text}`;
  }
  return defaultMessageForStatus(status);
}

function prettifyField(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function defaultMessageForStatus(status) {
  if (status === 0) return 'We could not reach the server. Check your connection and try again.';
  if (status === 400 || status === 422) return 'Some of the details provided were not accepted.';
  if (status === 401) return 'Your session has expired. Please sign in again.';
  if (status === 403) return 'You do not have permission to do that.';
  if (status === 404) return 'That item could not be found.';
  if (status === 409) return 'That action conflicts with the current state of the record.';
  if (status === 429) return 'Too many requests. Please wait a moment and try again.';
  if (status >= 500) return 'The server had a problem completing that request.';
  return 'Something went wrong. Please try again.';
}

function fieldErrors(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const fields = {};
  Object.entries(payload).forEach(([key, value]) => {
    if (key === 'detail' || key === 'message' || key === 'code') return;
    fields[key] = Array.isArray(value) ? value[0] : String(value);
  });
  return Object.keys(fields).length ? fields : null;
}

/** Normalise a DRF list response (paginated or plain array). */
export function toPage(payload, fallbackPage = 1) {
  if (Array.isArray(payload)) {
    return { items: payload, count: payload.length, page: 1, pages: 1, pageSize: payload.length, next: null, previous: null };
  }
  const items = payload?.results ?? payload?.items ?? payload?.data ?? [];
  const count = payload?.count ?? items.length;
  const pageSize = payload?.page_size ?? payload?.pageSize ?? (items.length || CONFIG.PRODUCTS_PER_PAGE);
  const page = payload?.page ?? payload?.current_page ?? fallbackPage;
  return {
    items: Array.isArray(items) ? items : [],
    count,
    page,
    pages: payload?.num_pages ?? payload?.pages ?? Math.max(1, Math.ceil(count / (pageSize || 1))),
    pageSize,
    next: payload?.next ?? null,
    previous: payload?.previous ?? null
  };
}

/* --------------------------------------------------------------- transport */
async function rawRequest(method, path, options = {}) {
  const {
    params, body, headers = {}, auth = false, timeout = CONFIG.REQUEST_TIMEOUT_MS,
    signal, raw = false, form = false
  } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error('timeout')), timeout);
  if (signal) signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });

  const finalHeaders = { Accept: 'application/json', ...headers };
  if (body !== undefined && !form) finalHeaders['Content-Type'] = 'application/json';
  if (auth) {
    const token = getAccessToken();
    if (token) finalHeaders.Authorization = `Bearer ${token}`;
  }
  const cToken = cartToken();
  if (cToken) finalHeaders['X-Cart-Token'] = cToken;

  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : (form ? body : JSON.stringify(body)),
      credentials: 'include',
      signal: controller.signal,
      cache: 'no-store'
    });
  } catch (err) {
    clearTimeout(timer);
    if (err?.name === 'AbortError') {
      throw new ApiError('The request took too long. Please try again.', { status: 0, code: 'timeout' });
    }
    throw new ApiError(defaultMessageForStatus(0), { status: 0, code: 'network' });
  }
  clearTimeout(timer);

  /* Guest cart identity: the backend may hand one back on any cart response. */
  const returnedCartToken = response.headers.get('X-Cart-Token') || response.headers.get('X-Cart-Id');
  if (returnedCartToken) store(CONFIG.CART_TOKEN_KEY, returnedCartToken);

  if (response.status === 204) return { status: 204, data: null, headers: response.headers };
  const isJson = (response.headers.get('content-type') || '').includes('application/json');
  const payload = isJson ? await response.json().catch(() => null) : await response.text();

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(payload, response.status), {
      status: response.status,
      code: payload?.code || `http_${response.status}`,
      fields: fieldErrors(payload),
      payload
    });
  }
  return { status: response.status, data: raw ? payload : payload, headers: response.headers };
}

/** Refresh the access token once, sharing the in-flight promise. */
async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const { data } = await rawRequest('POST', '/auth/refresh/', { body: { refresh } });
        const access = data?.access || data?.access_token;
        if (!access) return false;
        saveTokens({ access, refresh: data?.refresh || refresh });
        return true;
      } catch {
        clearTokens();
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

async function request(method, path, options = {}) {
  if (IS_DEMO) {
    const { handleMockRequest } = await import('./mock/mock-api.js');
    return handleMockRequest(method, path, options);
  }
  try {
    const { data } = await rawRequest(method, path, options);
    return data;
  } catch (err) {
    const retriable = options.auth && err instanceof ApiError && err.status === 401 && options._retried !== true;
    if (retriable && await refreshAccessToken()) {
      return request(method, path, { ...options, _retried: true });
    }
    if (err instanceof ApiError && err.status === 401 && options.auth) {
      clearTokens();
      window.dispatchEvent(new CustomEvent('starmond:session-expired'));
    }
    throw err;
  }
}

export const http = {
  get: (path, opts) => request('GET', path, opts),
  post: (path, body, opts = {}) => request('POST', path, { ...opts, body }),
  patch: (path, body, opts = {}) => request('PATCH', path, { ...opts, body }),
  put: (path, body, opts = {}) => request('PUT', path, { ...opts, body }),
  delete: (path, opts) => request('DELETE', path, opts),
  upload: (path, formData, opts = {}) => request('POST', path, { ...opts, body: formData, form: true })
};

/* --------------------------------------------------------------- resources */
export const catalog = {
  async categories() {
    const data = await http.get('/catalog/categories/');
    return toPage(data).items;
  },
  async products(query = {}) {
    const data = await http.get('/catalog/products/', { params: query });
    return toPage(data, Number(query.page) || 1);
  },
  product(slug, opts) { return http.get(`/catalog/products/${encodeURIComponent(slug)}/`, opts); },
  related(slug) { return http.get(`/catalog/products/${encodeURIComponent(slug)}/related/`); },
  async reviews(slug, query = {}) {
    const data = await http.get(`/catalog/products/${encodeURIComponent(slug)}/reviews/`, { params: query });
    return toPage(data);
  },
  createReview(slug, payload) { return http.post(`/catalog/products/${encodeURIComponent(slug)}/reviews/`, payload, { auth: true }); },
  suggestions(term, signal) { return http.get('/catalog/search/suggest/', { params: { q: term }, signal }); },
  facets(query = {}) { return http.get('/catalog/facets/', { params: query }); }
};

export const cart = {
  get(opts) { return http.get('/cart/', opts); },
  add({ product_id, variant_id = null, quantity = 1 }) {
    return http.post('/cart/items/', { product_id, variant_id, quantity });
  },
  update(itemId, quantity) { return http.patch(`/cart/items/${itemId}/`, { quantity }); },
  remove(itemId) { return http.delete(`/cart/items/${itemId}/`); },
  clear() { return http.delete('/cart/'); },
  merge() { return http.post('/cart/merge/', {}, { auth: true }); }
};

export const wishlist = {
  async list() {
    const data = await http.get('/wishlist/', { auth: true });
    return toPage(data).items;
  },
  add(product_id) { return http.post('/wishlist/', { product_id }, { auth: true }); },
  remove(itemId) { return http.delete(`/wishlist/${itemId}/`, { auth: true }); },
  merge(productIds) { return http.post('/wishlist/merge/', { product_ids: productIds }, { auth: true }); }
};

export const checkout = {
  shippingMethods(state) { return http.get('/checkout/shipping-methods/', { params: { state } }); },
  buyNow({ product_id, variant_id = null, quantity = 1 }) {
    return http.post('/checkout/buy-now/', { product_id, variant_id, quantity });
  },
  createSession(payload) { return http.post('/checkout/session/', payload); },
  applyCoupon(payload) { return http.post('/checkout/coupon/', payload); }
};

export const payments = {
  initialize({ order_id }) { return http.post('/payments/initialize/', { order_id }); },
  verify(reference) { return http.get('/payments/verify/', { params: { reference } }); }
};

export const orders = {
  async list(query = {}) {
    const data = await http.get('/orders/', { params: query, auth: true });
    return toPage(data, Number(query.page) || 1);
  },
  get(orderNumber) { return http.get(`/orders/${encodeURIComponent(orderNumber)}/`, { auth: true }); },
  cancel(orderNumber, reason = '') { return http.post(`/orders/${encodeURIComponent(orderNumber)}/cancel/`, { reason }, { auth: true }); },
  track({ order_number, email }) {
    return http.get('/orders/track/', { params: { order_number, email } });
  }
};

export const auth = {
  login(payload) { return http.post('/auth/login/', payload); },
  register(payload) { return http.post('/auth/register/', payload); },
  logout() { return http.post('/auth/logout/', { refresh: getRefreshToken() }, { auth: true }).catch(() => null); },
  me() { return http.get('/auth/me/', { auth: true }); },
  requestPasswordReset(email) { return http.post('/auth/password/reset/', { email }); },
  confirmPasswordReset(payload) { return http.post('/auth/password/reset/confirm/', payload); },
  changePassword(payload) { return http.post('/auth/password/change/', payload, { auth: true }); }
};

export const account = {
  updateProfile(payload) { return http.patch('/account/profile/', payload, { auth: true }); },
  addresses() { return http.get('/account/addresses/', { auth: true }); },
  createAddress(payload) { return http.post('/account/addresses/', payload, { auth: true }); },
  updateAddress(id, payload) { return http.patch(`/account/addresses/${id}/`, payload, { auth: true }); },
  deleteAddress(id) { return http.delete(`/account/addresses/${id}/`, { auth: true }); },
  notifications() { return http.get('/account/notifications/', { auth: true }); },
  readNotification(id) { return http.post(`/account/notifications/${id}/read/`, {}, { auth: true }); },
  readAllNotifications() { return http.post('/account/notifications/read-all/', {}, { auth: true }); },
  preferences() { return http.get('/account/notifications/preferences/', { auth: true }); },
  updatePreferences(payload) { return http.patch('/account/notifications/preferences/', payload, { auth: true }); }
};

export const support = {
  sendMessage(payload) { return http.post('/support/messages/', payload); }
};

/* ------------------------------------------------------------- admin API */
const admin = {
  request: (method, path, body, opts = {}) => http[method](`/admin${path}`, body, { auth: true, ...opts }),
  dashboard() { return http.get('/admin/dashboard/summary/', { auth: true }); },
  list(resource, query = {}) {
    return http.get(`/admin/${resource}/`, { params: query, auth: true }).then((d) => toPage(d, Number(query.page) || 1));
  },
  get(resource, id) { return http.get(`/admin/${resource}/${id}/`, { auth: true }); },
  create(resource, body) { return http.post(`/admin/${resource}/`, body, { auth: true }); },
  update(resource, id, body) { return http.patch(`/admin/${resource}/${id}/`, body, { auth: true }); },
  remove(resource, id) { return http.delete(`/admin/${resource}/${id}/`, { auth: true }); },
  action(resource, id, action, body = {}) {
    return http.post(`/admin/${resource}/${id}/${action}/`, body, { auth: true });
  },
  upload(resource, id, formData) {
    const path = id ? `/admin/${resource}/${id}/` : `/admin/${resource}/`;
    return http.upload(path, formData, { auth: true });
  },
  reports(query = {}) { return http.get('/admin/reports/overview/', { params: query, auth: true }); },
  inventory(query = {}) { return http.get('/admin/inventory/', { params: query, auth: true }).then((d) => toPage(d, 1)); },
  adjustStock(id, payload) { return http.post(`/admin/inventory/${id}/adjust/`, payload, { auth: true }); },
  refunds(query = {}) { return http.get('/admin/refunds/', { params: query, auth: true }).then((d) => toPage(d, 1)); },
  settings() { return http.get('/admin/settings/', { auth: true }); },
  updateSettings(body) { return http.patch('/admin/settings/', body, { auth: true }); },
  seo() { return http.get('/admin/seo/', { auth: true }); },
  updateSeo(body) { return http.patch('/admin/seo/', body, { auth: true }); },
  staff() { return http.get('/admin/staff/', { auth: true }).then((d) => toPage(d, 1)); },
  customer(id) { return http.get(`/admin/customers/${id}/`, { auth: true }); },
  orderStatus(id, status, note = '') {
    return http.post(`/admin/orders/${id}/status/`, { status, note }, { auth: true });
  },
  verifyPayment(id) { return http.post(`/admin/payments/${id}/verify/`, {}, { auth: true }); },
  createRefund(body) { return http.post('/admin/refunds/', body, { auth: true }); },
  sendNotification(body) { return http.post('/admin/notifications/', body, { auth: true }); },
  inviteStaff(body) { return http.post('/admin/staff/', body, { auth: true }); },
  content(query = {}) { return http.get('/admin/content/', { params: query, auth: true }).then((d) => toPage(d, 1)); },
  updateContent(id, body) { return http.patch(`/admin/content/${id}/`, body, { auth: true }); }
};

export { admin };
export default { http, catalog, cart, wishlist, checkout, payments, orders, auth, account, support, admin, ApiError };
