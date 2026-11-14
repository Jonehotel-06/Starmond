/**
 * utils.js — pure, dependency-free helpers.
 *
 * Everything here is side-effect free and safe to import in Node for unit
 * testing. Nothing in this module makes business decisions: money formatting
 * only renders values the backend already computed.
 */

/* ---------------------------------------------------------------- money -- */

/**
 * Render a monetary amount supplied by the backend.
 * NEVER computes, converts or rounds an authoritative total — it only formats.
 * @param {number|string|null|undefined} amount
 * @param {string} currency ISO 4217 code supplied by the API (default NGN).
 * @param {{decimals?:number}} [opts]
 * @returns {string}
 */
export function formatMoney(amount, currency = 'NGN', opts = {}) {
  if (amount === null || amount === undefined || amount === '') return '—';
  const value = typeof amount === 'string' ? Number(amount) : amount;
  if (!Number.isFinite(value)) return '—';
  const decimals = opts.decimals ?? (Number.isInteger(value) ? 0 : 2);
  try {
    return new Intl.NumberFormat('en-NG', {
      style: 'currency',
      currency,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      currencyDisplay: 'narrowSymbol',
    }).format(value);
  } catch {
    return `${currency} ${value.toFixed(decimals)}`;
  }
}

/** Compact number for dashboard counters (1.2k, 3.4M). Never used for money. */
export function formatCount(n) {
  if (n === null || n === undefined) return '—';
  const value = Number(n);
  if (!Number.isFinite(value)) return '—';
  if (Math.abs(value) < 1000) return String(value);
  return new Intl.NumberFormat('en-NG', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function formatNumber(n) {
  const value = Number(n);
  return Number.isFinite(value) ? new Intl.NumberFormat('en-NG').format(value) : '—';
}

/* ----------------------------------------------------------------- dates -- */

export function formatDate(input, opts = {}) {
  if (!input) return '—';
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-NG', {
    day: 'numeric', month: 'short', year: 'numeric', ...opts,
  }).format(d);
}

export function formatDateTime(input) {
  if (!input) return '—';
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-NG', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(d);
}

export function timeAgo(input) {
  if (!input) return '';
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return '';
  const diff = (Date.now() - d.getTime()) / 1000;
  const units = [
    ['year', 31536000], ['month', 2592000], ['week', 604800],
    ['day', 86400], ['hour', 3600], ['minute', 60],
  ];
  for (const [unit, secs] of units) {
    const v = Math.floor(diff / secs);
    if (v >= 1) return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-v, unit);
  }
  return 'just now';
}

/* ----------------------------------------------------------------- text -- */

/** Escape a string for safe interpolation into innerHTML. */
export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Escape for use inside a URL query component. */
export function enc(value) {
  return encodeURIComponent(String(value ?? ''));
}

/**
 * Strip every tag from backend-supplied rich text. Used wherever we render
 * admin/CMS HTML into a text-only context (meta descriptions, cards).
 */
export function stripTags(html) {
  return String(html ?? '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * Sanitise backend/CMS rich text before injecting as HTML.
 * Allow-list based; removes scripts, event handlers, and unsafe URL schemes.
 * Rich text is authored by trusted admins, but we still defence-in-depth it.
 */
const ALLOWED_TAGS = new Set([
  'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'ul', 'ol', 'li', 'blockquote',
  'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th',
  'td', 'hr', 'code', 'pre', 'span', 'figure', 'figcaption',
]);
const ALLOWED_ATTRS = {
  a: ['href', 'title', 'target', 'rel'],
  img: ['src', 'alt', 'width', 'height', 'loading'],
  th: ['colspan', 'rowspan', 'scope'],
  td: ['colspan', 'rowspan'],
};

export function sanitizeHtml(html) {
  if (!html) return '';
  if (typeof DOMParser === 'undefined') return esc(stripTags(html));
  const doc = new DOMParser().parseFromString(String(html), 'text/html');
  const walk = (node) => {
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === 3) return;
      if (child.nodeType !== 1) { child.remove(); return; }
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED_TAGS.has(tag)) {
        // Unwrap unknown-but-harmless containers, drop dangerous ones entirely.
        if (['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'link', 'meta'].includes(tag)) {
          child.remove();
        } else {
          const parent = child.parentNode;
          while (child.firstChild) parent.insertBefore(child.firstChild, child);
          child.remove();
        }
        return;
      }
      const allowed = ALLOWED_ATTRS[tag] || [];
      [...child.attributes].forEach((attr) => {
        const name = attr.name.toLowerCase();
        if (!allowed.includes(name) || name.startsWith('on')) {
          child.removeAttribute(attr.name);
          return;
        }
        if ((name === 'href' || name === 'src') && !isSafeUrl(attr.value)) {
          child.removeAttribute(attr.name);
        }
      });
      if (tag === 'a' && child.getAttribute('target') === '_blank') {
        child.setAttribute('rel', 'noopener noreferrer');
      }
      walk(child);
    });
  };
  walk(doc.body);
  return doc.body.innerHTML;
}

export function isSafeUrl(url) {
  const value = String(url ?? '').trim();
  if (!value) return false;
  if (/^(\/|#|\?)/.test(value)) return true;
  try {
    const parsed = new URL(value, typeof location !== 'undefined' ? location.href : 'https://example.invalid');
    return ['http:', 'https:', 'mailto:', 'tel:'].includes(parsed.protocol);
  } catch {
    return false;
  }
}

export function slugify(text) {
  return String(text ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 96);
}

export function truncate(text, max = 160) {
  const s = String(text ?? '');
  return s.length <= max ? s : `${s.slice(0, max - 1).trimEnd()}…`;
}

export function initials(name) {
  const parts = String(name ?? '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

export function titleCase(value) {
  return String(value ?? '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------ functions -- */

/** Trailing-edge debounce with a cancel handle. Used by search inputs. */
export function debounce(fn, wait = 300) {
  let timer = null;
  const wrapped = (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(...args); }, wait);
  };
  wrapped.cancel = () => { if (timer) clearTimeout(timer); timer = null; };
  return wrapped;
}

/** Leading-edge throttle for scroll/resize handlers. */
export function throttle(fn, wait = 150) {
  let last = 0;
  let timer = null;
  return (...args) => {
    const now = Date.now();
    const remaining = wait - (now - last);
    if (remaining <= 0) {
      if (timer) { clearTimeout(timer); timer = null; }
      last = now;
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => { last = Date.now(); timer = null; fn(...args); }, remaining);
    }
  };
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ------------------------------------------------------------------ urls -- */

/** Build a query string, dropping empty/null/undefined values. */
export function buildQuery(params = {}) {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '' || value === false) return;
    if (Array.isArray(value)) {
      value.forEach((v) => { if (v !== null && v !== undefined && v !== '') usp.append(key, String(v)); });
    } else {
      usp.set(key, String(value));
    }
  });
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export function readQuery(search = (typeof location !== 'undefined' ? location.search : '')) {
  return Object.fromEntries(new URLSearchParams(search).entries());
}

/** Merge params into the current URL and push/replace history state. */
export function syncQuery(params, { replace = true } = {}) {
  if (typeof history === 'undefined' || typeof location === 'undefined') return;
  const url = new URL(location.href);
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '' || value === false) url.searchParams.delete(key);
    else url.searchParams.set(key, String(value));
  });
  history[replace ? 'replaceState' : 'pushState']({}, '', url);
}

/* ------------------------------------------------------------------- dom -- */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function on(root, type, selector, handler, options) {
  root.addEventListener(type, (event) => {
    const target = event.target.closest?.(selector);
    if (target && root.contains(target)) handler(event, target);
  }, options);
}

/** Create an element from an HTML string (first element only). */
export function el(html) {
  const template = document.createElement('template');
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

/* --------------------------------------------------------------- storage -- */

/** Namespaced, failure-tolerant storage wrapper (private mode, quota, etc). */
export function createStorage(area = 'local', namespace = 'starmond') {
  const getArea = () => {
    try {
      if (typeof window === 'undefined') return null;
      return area === 'session' ? window.sessionStorage : window.localStorage;
    } catch { return null; }
  };
  const key = (k) => `${namespace}:${k}`;
  return {
    get(k, fallback = null) {
      try {
        const raw = getArea()?.getItem(key(k));
        return raw === null || raw === undefined ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(k, value) {
      try { getArea()?.setItem(key(k), JSON.stringify(value)); return true; } catch { return false; }
    },
    remove(k) {
      try { getArea()?.removeItem(key(k)); } catch { /* ignore */ }
    },
  };
}

/* ------------------------------------------------------------- validation -- */

export const isEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(value ?? '').trim());

/** Nigerian and international phone numbers, permissive but not empty. */
export const isPhone = (value) => /^\+?[0-9][0-9\s()-]{6,19}$/.test(String(value ?? '').trim());

export function normalizePhone(value) {
  const raw = String(value ?? '').replace(/[^\d+]/g, '');
  if (raw.startsWith('+')) return raw;
  if (raw.startsWith('0') && raw.length === 11) return `+234${raw.slice(1)}`;
  if (raw.startsWith('234')) return `+${raw}`;
  return raw;
}

/** Deep-ish equality for plain JSON structures (cart comparison). */
export function jsonEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Stable id for client-side keys — not a security token. */
export function uid(prefix = 'id') {
  const rnd = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}_${rnd}`;
}

/** Cryptographically random opaque token for the guest cart header. */
export function randomToken(bytes = 24) {
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const arr = new Uint8Array(bytes);
    crypto.getRandomValues(arr);
    return [...arr].map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}
