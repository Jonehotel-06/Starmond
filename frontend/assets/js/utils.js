/** Small, dependency-free helpers shared across the storefront. */

const nf = new Intl.NumberFormat('en-NG', {
  style: 'currency',
  currency: 'NGN',
  currencyDisplay: 'narrowSymbol',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2
});

/** Format a backend money value. Backend values are authoritative; this only displays them. */
export function money(value, currency = 'NGN') {
  const n = typeof value === 'string' ? Number(value.replace(/[^\d.-]/g, '')) : Number(value);
  if (!Number.isFinite(n)) return '—';
  if (currency !== 'NGN') {
    try {
      return new Intl.NumberFormat('en-NG', { style: 'currency', currency, maximumFractionDigits: 2 }).format(n);
    } catch { return `${currency} ${n.toFixed(2)}`; }
  }
  return nf.format(n);
}

export function formatDate(value, opts = {}) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric', ...opts });
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-NG', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function relativeTime(value) {
  if (!value) return '';
  const d = new Date(value).getTime();
  if (Number.isNaN(d)) return '';
  const diff = Math.round((d - Date.now()) / 1000);
  const units = [['year', 31536000], ['month', 2592000], ['week', 604800], ['day', 86400], ['hour', 3600], ['minute', 60]];
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  for (const [unit, secs] of units) {
    if (Math.abs(diff) >= secs) return rtf.format(Math.round(diff / secs), unit);
  }
  return rtf.format(diff, 'second');
}

/** Escape untrusted strings before inserting into HTML. */
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

export function qs(sel, root = document) { return root.querySelector(sel); }
export function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

export function debounce(fn, wait = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

export function throttle(fn, wait = 150) {
  let last = 0, timer;
  return (...args) => {
    const now = Date.now();
    if (now - last >= wait) { last = now; fn(...args); }
    else { clearTimeout(timer); timer = setTimeout(() => { last = Date.now(); fn(...args); }, wait - (now - last)); }
  };
}

export function params(overrides = {}) {
  const url = new URL(window.location.href);
  const out = {};
  for (const [k, v] of url.searchParams.entries()) out[k] = v;
  return { ...out, ...overrides };
}

export function setParams(next = {}, { replace = true } = {}) {
  const url = new URL(window.location.href);
  Object.entries(next).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || v === false) url.searchParams.delete(k);
    else url.searchParams.set(k, String(v));
  });
  const target = url.pathname + (url.search ? url.search : '') + url.hash;
  if (replace) window.history.replaceState({}, '', target);
  else window.history.pushState({}, '', target);
}

export function stored(key, fallback = null) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
  catch { return fallback; }
}
export function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage disabled */ }
}
export function forget(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } }

/** Session-scoped storage (cleared when the tab closes). */
export function sessionStored(key, fallback = null) {
  try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
  catch { return fallback; }
}
export function sessionStore(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* storage disabled */ }
}
export function sessionForget(key) { try { sessionStorage.removeItem(key); } catch { /* ignore */ } }

/** Prefix to the site root from the current page (category pages live 2 levels down). */
export function rootPrefix() {
  return document.documentElement.dataset.root || '';
}

/** Build a storefront URL that works from any page depth. */
export function sitePath(path = '') {
  return `${rootPrefix()}${String(path).replace(/^\//, '')}`;
}

export function slugToTitle(slug = '') {
  return slug.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Validators return an error string, or '' when valid. */
export const validate = {
  email(v) {
    if (!v) return 'Enter your email address.';
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) ? '' : 'Enter a valid email address.';
  },
  phone(v) {
    const digits = (v || '').replace(/[^\d]/g, '');
    if (!digits) return 'Enter your phone number.';
    if (digits.length < 10 || digits.length > 15) return 'Enter a valid Nigerian phone number.';
    return '';
  },
  required(v, label = 'This field') {
    return (v || '').trim() ? '' : `${label} is required.`;
  },
  minLen(v, n, label = 'This field') {
    return (v || '').trim().length >= n ? '' : `${label} must be at least ${n} characters.`;
  },
  number(v, { min = 0, max = Infinity, label = 'This field' } = {}) {
    if (v === '' || v === null) return '';
    const n = Number(v);
    if (!Number.isFinite(n)) return `${label} must be a number.`;
    if (n < min) return `${label} cannot be less than ${min}.`;
    if (n > max) return `${label} cannot be more than ${max}.`;
    return '';
  }
};

/** Set or clear an inline field error and its aria-invalid state. */
export function fieldError(form, name, message) {
  const input = form.querySelector(`[name="${name}"]`);
  const slot = form.querySelector(`[data-error-for="${name}"]`);
  if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false');
  if (!slot) return;
  slot.textContent = message || '';
  slot.hidden = !message;
}

export function clearErrors(form) {
  qsa('[data-error-for]', form).forEach((n) => { n.textContent = ''; n.hidden = true; });
  qsa('[aria-invalid]', form).forEach((n) => n.setAttribute('aria-invalid', 'false'));
}

export function starRow(rating = 0, max = 5) {
  const rounded = Math.round(Number(rating) || 0);
  let out = '';
  for (let i = 1; i <= max; i += 1) {
    out += `<svg class="icon${i > rounded ? ' icon--off' : ''}" aria-hidden="true"><use href="#i-star"></use></svg>`;
  }
  return out;
}

export const NIGERIAN_STATES = [
  'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno',
  'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'FCT - Abuja', 'Gombe',
  'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos',
  'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto',
  'Taraba', 'Yobe', 'Zamfara'
];

export function fillStates(select, selected = '') {
  if (!select) return;
  const options = NIGERIAN_STATES.map(
    (s) => `<option value="${esc(s)}"${s === selected ? ' selected' : ''}>${esc(s)}</option>`
  ).join('');
  select.insertAdjacentHTML('beforeend', options);
}

export function setBusy(el, busy, label) {
  if (!el) return;
  if (busy) {
    el.dataset.originalText = el.innerHTML;
    el.classList.add('is-loading');
    el.setAttribute('aria-busy', 'true');
    el.disabled = true;
    if (label) el.innerHTML = label;
  } else {
    el.classList.remove('is-loading');
    el.removeAttribute('aria-busy');
    el.disabled = false;
    if (el.dataset.originalText) { el.innerHTML = el.dataset.originalText; delete el.dataset.originalText; }
  }
}
