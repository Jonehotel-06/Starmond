/**
 * api.js — the single, centralized HTTP client.
 *
 * EVERY network call in this application goes through this module. No feature
 * module may call fetch() directly.
 *
 * Responsibilities
 *   • base URL from deployment config (never hardcoded)
 *   • authentication: DRF session + CSRF, or JWT bearer + refresh
 *   • guest cart token header
 *   • timeouts via AbortController, caller-supplied cancellation
 *   • JSON and FormData bodies
 *   • normalized errors (including DRF field errors)
 *   • safe retries: idempotent methods only, network/429/5xx only, backoff+jitter
 *   • in-flight request deduplication for GETs
 *   • short-TTL caching for PUBLIC catalogue reads only
 *   • offline / network-failure detection
 *
 * It deliberately contains NO business logic: no totals, no stock decisions,
 * no discount maths, no payment verification.
 */

import { buildQuery, randomToken, createStorage, sleep } from './utils.js';

const CONFIG = (typeof window !== 'undefined' && window.STARMOND_CONFIG) || {};
const storage = createStorage('local');

const IDEMPOTENT = new Set(['GET', 'HEAD', 'OPTIONS']);
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Paths whose responses must never be cached or deduplicated across mounts. */
const PRIVATE_PATH = /\/(auth|account|cart|checkout|orders|payments|wishlist|refunds|admin|notifications|me)\b/i;

/* ============================================================================
   Error model
   ========================================================================== */

export class ApiError extends Error {
  constructor(message, {
    status = 0, code = 'error', data = null, fieldErrors = null,
    kind = 'unknown', url = '', retryAfter = null,
  } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.data = data;
    this.fieldErrors = fieldErrors;
    this.kind = kind;      // network | timeout | aborted | http | parse
    this.url = url;
    this.retryAfter = retryAfter;
  }

  get isNetwork() { return this.kind === 'network'; }
  get isTimeout() { return this.kind === 'timeout'; }
  get isAborted() { return this.kind === 'aborted' || this.code === 'aborted'; }
  get isOffline() { return this.code === 'offline'; }
  get isAuth() { return this.status === 401; }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
  get isValidation() { return this.status === 400 || this.status === 422; }
  get isConflict() { return this.status === 409; }
  get isRateLimited() { return this.status === 429; }
  get isServer() { return this.status >= 500; }
  get isUnavailable() { return this.status === 503 || this.status === 0; }

  /** A message safe to show a shopper. */
  get userMessage() {
    if (this.isOffline) return 'You appear to be offline. Reconnect and try again.';
    if (this.isTimeout) return 'The store took too long to respond. Please try again.';
    if (this.isNetwork) return 'We could not reach the store. Check your connection and try again.';
    if (this.isRateLimited) return 'Too many requests. Please wait a moment and try again.';
    if (this.isForbidden) return 'You do not have permission to perform this action.';
    if (this.isNotFound) return 'We could not find what you were looking for.';
    if (this.isServer) return 'The store is having a problem right now. Please try again shortly.';
    return this.message || 'Something went wrong. Please try again.';
  }
}

/**
 * Normalize the many shapes a DRF backend can return into one object.
 * Supported: {detail}, {non_field_errors}, {field: [msgs]}, {message},
 * {error: {code, message, fields}}, plain strings, and HTML error pages.
 */
export function normalizeErrorBody(body, status) {
  const fallback = `Request failed (${status})`;
  if (!body) return { message: fallback, code: `http_${status}`, fieldErrors: null };

  if (typeof body === 'string') {
    const text = body.trim();
    if (text.startsWith('<')) return { message: fallback, code: `http_${status}`, fieldErrors: null };
    return { message: text.slice(0, 400), code: `http_${status}`, fieldErrors: null };
  }

  if (Array.isArray(body)) {
    return { message: body.map(String).join(' '), code: `http_${status}`, fieldErrors: null };
  }

  const fieldErrors = {};
  let message = '';
  let code = body.code || `http_${status}`;

  if (body.error && typeof body.error === 'object') {
    message = body.error.message || body.error.detail || '';
    code = body.error.code || code;
    if (body.error.fields && typeof body.error.fields === 'object') {
      Object.assign(fieldErrors, flattenFields(body.error.fields));
    }
  }

  if (!message) {
    message = body.detail || body.message || body.error_description || '';
    if (typeof message !== 'string') message = '';
  }

  Object.entries(body).forEach(([key, value]) => {
    if (['detail', 'message', 'code', 'error', 'status'].includes(key)) return;
    if (key === 'non_field_errors') {
      const text = asMessages(value).join(' ');
      message = message ? `${message} ${text}` : text;
      return;
    }
    fieldErrors[key] = asMessages(value);
  });

  if (!message) {
    const first = Object.values(fieldErrors).flat()[0];
    message = first || fallback;
  }

  return {
    message,
    code,
    fieldErrors: Object.keys(fieldErrors).length ? fieldErrors : null,
  };
}

function asMessages(value) {
  if (Array.isArray(value)) return value.map((v) => (typeof v === 'string' ? v : v?.message || JSON.stringify(v)));
  if (value && typeof value === 'object') return Object.values(value).flat().map(String);
  return [String(value)];
}

function flattenFields(fields, prefix = '') {
  const out = {};
  Object.entries(fields).forEach(([key, value]) => {
    const name = prefix ? `${prefix}.${key}` : key;
    if (Array.isArray(value) || typeof value === 'string') out[name] = asMessages(value);
    else if (value && typeof value === 'object') Object.assign(out, flattenFields(value, name));
  });
  return out;
}

/* ============================================================================
   Client
   ========================================================================== */

class ApiClient {
  constructor() {
    this.baseUrl = CONFIG.API_BASE_URL ?? '/api/v1';
    this.timeout = CONFIG.REQUEST_TIMEOUT_MS ?? 20000;
    this.retryAttempts = CONFIG.RETRY_ATTEMPTS ?? 2;
    this.retryBaseDelay = CONFIG.RETRY_BASE_DELAY_MS ?? 400;
    this.cacheTtl = CONFIG.PUBLIC_CACHE_TTL_MS ?? 60000;
    this.authMode = CONFIG.AUTH_MODE || 'session';

    /** @type {Map<string, Promise<any>>} in-flight GET deduplication */
    this.inflight = new Map();
    /** @type {Map<string, {expires:number, value:any}>} public read cache */
    this.cache = new Map();
    /** In-memory only. Never persisted to localStorage. */
    this.accessToken = null;
    this._refreshPromise = null;
    this._listeners = new Map();
    this._online = typeof navigator === 'undefined' ? true : navigator.onLine !== false;

    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => { this._online = true; this.emit('online'); });
      window.addEventListener('offline', () => { this._online = false; this.emit('offline'); });
    }
  }

  /* ------------------------------------------------------------- events -- */

  on(event, handler) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event).add(handler);
    return () => this._listeners.get(event)?.delete(handler);
  }

  emit(event, payload) {
    this._listeners.get(event)?.forEach((fn) => {
      try { fn(payload); } catch (err) { console.error('[api] listener error', err); }
    });
  }

  get isOnline() { return this._online; }

  /* --------------------------------------------------------------- auth -- */

  setAccessToken(token) { this.accessToken = token || null; }
  clearAccessToken() { this.accessToken = null; }

  getCartToken() {
    let token = storage.get('cart_token');
    if (!token) {
      token = randomToken(24);
      storage.set('cart_token', token);
    }
    return token;
  }

  rotateCartToken() {
    const token = randomToken(24);
    storage.set('cart_token', token);
    return token;
  }

  clearCartToken() { storage.remove('cart_token'); }

  readCookie(name) {
    if (typeof document === 'undefined') return null;
    const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  }

  /* ---------------------------------------------------------------- url -- */

  url(path, params) {
    const clean = String(path).startsWith('/') ? path : `/${path}`;
    const base = /^https?:\/\//i.test(clean) ? clean : `${this.baseUrl}${clean}`;
    return `${base}${params ? buildQuery(params) : ''}`;
  }

  /* -------------------------------------------------------------- cache -- */

  isCacheable(path) { return !PRIVATE_PATH.test(String(path)); }

  cacheKey(url, headers) {
    return `${url}|${headers['X-Cart-Token'] || ''}|${this.accessToken ? 'auth' : 'anon'}`;
  }

  /** Invalidate public caches. Call after any mutation that affects catalogue. */
  invalidate(prefix = '') {
    if (!prefix) { this.cache.clear(); return; }
    [...this.cache.keys()].forEach((key) => { if (key.startsWith(prefix)) this.cache.delete(key); });
  }

  /* ------------------------------------------------------------ request -- */

  /**
   * @param {string} path
   * @param {object} [options]
   * @param {string} [options.method='GET']
   * @param {object|FormData} [options.body]
   * @param {object} [options.params] query parameters
   * @param {AbortSignal} [options.signal]
   * @param {boolean} [options.cache=false] opt-in public caching
   * @param {boolean} [options.dedupe=true]
   * @param {number} [options.timeout]
   * @param {number} [options.retries]
   * @param {boolean} [options.auth=true] attach credentials
   * @param {boolean} [options.raw=false] resolve the Response instead of JSON
   */
  async request(path, options = {}) {
    const {
      method = 'GET', body, params, signal, cache = false, dedupe = true,
      timeout = this.timeout, retries, raw = false, auth = true, headers: extraHeaders = {},
    } = options;

    const verb = method.toUpperCase();
    const url = this.url(path, params);
    const canCache = cache && verb === 'GET' && this.isCacheable(path);
    const headers = this.buildHeaders(verb, body, auth, extraHeaders);
    const key = this.cacheKey(url, headers);

    if (canCache) {
      const hit = this.cache.get(key);
      if (hit && hit.expires > Date.now()) return hit.value;
    }

    if (verb === 'GET' && dedupe && this.inflight.has(key)) {
      return this.inflight.get(key);
    }

    const attemptLimit = retries ?? (IDEMPOTENT.has(verb) ? this.retryAttempts : 0);
    const promise = this.execute(url, { verb, body, headers, timeout, signal, attemptLimit, raw, path })
      .then((value) => {
        if (canCache) this.cache.set(key, { expires: Date.now() + this.cacheTtl, value });
        return value;
      })
      .finally(() => { this.inflight.delete(key); });

    if (verb === 'GET' && dedupe) this.inflight.set(key, promise);
    return promise;
  }

  buildHeaders(verb, body, auth, extra) {
    const headers = { Accept: 'application/json', ...extra };

    if (body !== undefined && body !== null && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    if (auth) {
      if (this.authMode === 'jwt' && this.accessToken) {
        headers.Authorization = `Bearer ${this.accessToken}`;
      }
      if (UNSAFE.has(verb)) {
        const csrf = this.readCookie(CONFIG.CSRF_COOKIE_NAME || 'csrftoken');
        if (csrf) headers[CONFIG.CSRF_HEADER_NAME || 'X-CSRFToken'] = csrf;
      }
      const cartToken = storage.get('cart_token');
      if (cartToken) headers['X-Cart-Token'] = cartToken;
    }

    return headers;
  }

  async execute(url, { verb, body, headers, timeout, signal, attemptLimit, raw, path }) {
    let attempt = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        throw new ApiError('You appear to be offline.', { code: 'offline', kind: 'network', url });
      }

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), timeout);
      const onAbort = () => controller.abort(signal.reason);
      if (signal) {
        if (signal.aborted) { clearTimeout(timer); throw new ApiError('Request cancelled.', { code: 'aborted', kind: 'aborted', url }); }
        signal.addEventListener('abort', onAbort, { once: true });
      }

      let response;
      try {
        response = await fetch(url, {
          method: verb,
          headers,
          body: body === undefined || body === null
            ? undefined
            : (body instanceof FormData ? body : JSON.stringify(body)),
          credentials: 'include',
          signal: controller.signal,
          redirect: 'follow',
          cache: 'no-store',
        });
      } catch (err) {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);

        const abortedByCaller = signal?.aborted;
        const isTimeout = err?.name === 'TimeoutError' || (!abortedByCaller && err?.name === 'AbortError');

        if (abortedByCaller) {
          throw new ApiError('Request cancelled.', { code: 'aborted', kind: 'aborted', url });
        }
        const error = isTimeout
          ? new ApiError('The request timed out.', { code: 'timeout', kind: 'timeout', url })
          : new ApiError('Network request failed.', { code: 'network_error', kind: 'network', url });

        if (attempt < attemptLimit && IDEMPOTENT.has(verb)) {
          attempt += 1;
          await sleep(this.backoff(attempt));
          continue;
        }
        this.emit('network-error', error);
        throw error;
      }

      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);

      // 401 on a JWT deployment: try one silent refresh, then replay once.
      if (response.status === 401 && this.authMode === 'jwt' && !url.includes('/auth/refresh') && !headers['X-Retried-Auth']) {
        const refreshed = await this.tryRefresh();
        if (refreshed) {
          const retryHeaders = { ...this.buildHeaders(verb, body, true, {}), 'X-Retried-Auth': '1' };
          return this.execute(url, { verb, body, headers: retryHeaders, timeout, signal, attemptLimit: 0, raw, path });
        }
      }

      if (response.ok) {
        if (raw) return response;
        if (response.status === 204) return null;
        const type = response.headers.get('content-type') || '';
        if (type.includes('application/json')) {
          try { return await response.json(); }
          catch {
            throw new ApiError('The store returned an unreadable response.', {
              status: response.status, code: 'parse_error', kind: 'parse', url,
            });
          }
        }
        if (type.includes('text/')) return await response.text();
        return await response.blob();
      }

      // Retryable server / throttling failures on idempotent verbs only.
      const retryable = (response.status >= 500 || response.status === 429) && IDEMPOTENT.has(verb);
      if (retryable && attempt < attemptLimit) {
        attempt += 1;
        const retryAfter = Number(response.headers.get('Retry-After'));
        const wait = Number.isFinite(retryAfter) && retryAfter > 0
          ? Math.min(retryAfter * 1000, 10000)
          : this.backoff(attempt);
        await sleep(wait);
        continue;
      }

      let parsed = null;
      try {
        const type = response.headers.get('content-type') || '';
        parsed = type.includes('application/json') ? await response.json() : await response.text();
      } catch { /* body may be empty */ }

      const { message, code, fieldErrors } = normalizeErrorBody(parsed, response.status);
      const error = new ApiError(message, {
        status: response.status,
        code,
        data: parsed,
        fieldErrors,
        kind: 'http',
        url,
        retryAfter: response.headers.get('Retry-After'),
      });

      if (response.status === 401) this.emit('unauthorized', error);
      if (response.status === 403) this.emit('forbidden', error);
      if (response.status >= 500) this.emit('server-error', error);

      // Any successful-path mutation clears stale public caches.
      throw error;
    }
  }

  backoff(attempt) {
    const base = this.retryBaseDelay * (2 ** (attempt - 1));
    return Math.min(base + Math.random() * 150, 5000);
  }

  async tryRefresh() {
    if (this._refreshPromise) return this._refreshPromise;
    this._refreshPromise = (async () => {
      try {
        const res = await fetch(this.url('/auth/refresh/'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: '{}',
        });
        if (!res.ok) return false;
        const data = await res.json();
        const token = data.access || data.access_token || data.token;
        if (!token) return false;
        this.setAccessToken(token);
        this.emit('token-refreshed', token);
        return true;
      } catch {
        return false;
      } finally {
        this._refreshPromise = null;
      }
    })();
    return this._refreshPromise;
  }

  /* ------------------------------------------------------------ verbs ---- */

  get(path, options = {}) { return this.request(path, { ...options, method: 'GET' }); }
  post(path, body, options = {}) { return this.request(path, { ...options, method: 'POST', body }); }
  put(path, body, options = {}) { return this.request(path, { ...options, method: 'PUT', body }); }
  patch(path, body, options = {}) { return this.request(path, { ...options, method: 'PATCH', body }); }
  delete(path, options = {}) { return this.request(path, { ...options, method: 'DELETE' }); }

  /** Public catalogue read: cached + deduplicated. */
  publicGet(path, options = {}) {
    return this.request(path, { ...options, method: 'GET', cache: true, dedupe: true });
  }

  /** Private read: never cached, never deduplicated across navigations. */
  privateGet(path, options = {}) {
    return this.request(path, { ...options, method: 'GET', cache: false, dedupe: false });
  }

  /** Multipart upload (images, media library, CSV import). */
  upload(path, formData, options = {}) {
    return this.request(path, { ...options, method: options.method || 'POST', body: formData });
  }

  /** Fetch a backend-generated export (CSV/XLSX/PDF) as a Blob. */
  async download(path, options = {}) {
    const response = await this.request(path, { ...options, method: 'GET', raw: true, cache: false, dedupe: false });
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    return { blob, filename: match ? decodeURIComponent(match[1]) : null };
  }
}

export const api = new ApiClient();

/* ============================================================================
   Response helpers — DRF pagination comes in two common shapes.
   ========================================================================== */

/**
 * Normalize a list response to {results, count, next, previous}.
 * Accepts DRF PageNumberPagination, LimitOffsetPagination, or a bare array.
 */
export function normalizeList(data) {
  if (Array.isArray(data)) {
    return { results: data, count: data.length, next: null, previous: null };
  }
  if (data && Array.isArray(data.results)) {
    return {
      results: data.results,
      count: typeof data.count === 'number' ? data.count : data.results.length,
      next: data.next ?? null,
      previous: data.previous ?? null,
    };
  }
  if (data && Array.isArray(data.items)) {
    return {
      results: data.items,
      count: typeof data.total === 'number' ? data.total : data.items.length,
      next: data.next ?? null,
      previous: data.previous ?? null,
    };
  }
  return { results: [], count: 0, next: null, previous: null };
}

/** Turn an ApiError into a {field: message} map for form rendering. */
export function fieldErrorMap(error) {
  if (!(error instanceof ApiError) || !error.fieldErrors) return {};
  return Object.fromEntries(
    Object.entries(error.fieldErrors).map(([key, value]) => [key, Array.isArray(value) ? value[0] : String(value)]),
  );
}

export default api;
