/**
 * ui.js — shared interface primitives.
 *
 * Contains: live-region announcements, toasts, accessible dialogs and drawers,
 * skeleton builders, empty/error state rendering, and form error binding.
 *
 * There are NO spinners in this file or anywhere else in the application.
 * Loading is always expressed with dimension-matched skeletons.
 */

import { esc } from './utils.js';
import { icon, hydrateIcons } from './icons.js';

/* ============================================================================
   Live region — screen-reader status announcements
   ========================================================================== */

let liveRegion = null;
let assertiveRegion = null;

export function initLiveRegions() {
  if (liveRegion || typeof document === 'undefined') return;
  liveRegion = document.createElement('div');
  liveRegion.className = 'sr-only';
  liveRegion.setAttribute('role', 'status');
  liveRegion.setAttribute('aria-live', 'polite');
  liveRegion.setAttribute('aria-atomic', 'true');
  document.body.appendChild(liveRegion);

  assertiveRegion = document.createElement('div');
  assertiveRegion.className = 'sr-only';
  assertiveRegion.setAttribute('role', 'alert');
  assertiveRegion.setAttribute('aria-live', 'assertive');
  assertiveRegion.setAttribute('aria-atomic', 'true');
  document.body.appendChild(assertiveRegion);
}

export function announce(message, { assertive = false } = {}) {
  initLiveRegions();
  const region = assertive ? assertiveRegion : liveRegion;
  if (!region) return;
  region.textContent = '';
  // Two frames guarantees the AT registers the change.
  requestAnimationFrame(() => { requestAnimationFrame(() => { region.textContent = message; }); });
}

/* ============================================================================
   Toasts
   ========================================================================== */

let toastRegion = null;

function ensureToastRegion() {
  if (toastRegion) return toastRegion;
  toastRegion = document.createElement('div');
  toastRegion.className = 'toast-region';
  toastRegion.setAttribute('role', 'region');
  toastRegion.setAttribute('aria-label', 'Notifications');
  document.body.appendChild(toastRegion);
  return toastRegion;
}

const TOAST_ICONS = { success: 'check-circle', danger: 'alert-circle', warning: 'alert-triangle', info: 'info' };

/**
 * @param {string} message
 * @param {{type?:'success'|'danger'|'warning'|'info', title?:string, duration?:number,
 *          action?:{label:string, href?:string, onClick?:Function}}} [opts]
 */
export function toast(message, opts = {}) {
  const { type = 'info', title = '', duration = type === 'danger' ? 7000 : 4500, action } = opts;
  const region = ensureToastRegion();
  const node = document.createElement('div');
  node.className = `toast toast--${type}`;
  node.innerHTML = `
    <span class="toast__icon">${icon(TOAST_ICONS[type] || 'info')}</span>
    <div class="toast__body">
      ${title ? `<span class="toast__title">${esc(title)}</span>` : ''}
      <span class="toast__msg">${esc(message)}</span>
      ${action ? `<button type="button" class="toast__action" data-toast-action>${esc(action.label)}</button>` : ''}
    </div>
    <button type="button" class="toast__close" aria-label="Dismiss notification">${icon('x', { size: 'sm' })}</button>
  `;

  const remove = () => {
    node.classList.add('is-leaving');
    setTimeout(() => node.remove(), 200);
  };

  node.querySelector('.toast__close').addEventListener('click', remove);
  if (action) {
    node.querySelector('[data-toast-action]').addEventListener('click', () => {
      remove();
      if (action.href) window.location.assign(action.href);
      else action.onClick?.();
    });
  }

  region.appendChild(node);
  announce(`${title ? `${title}. ` : ''}${message}`, { assertive: type === 'danger' });
  if (duration > 0) setTimeout(remove, duration);
  return { dismiss: remove, element: node };
}

/* ============================================================================
   Focus management
   ========================================================================== */

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function getFocusable(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter((node) => {
    if (node.hasAttribute('hidden') || node.getAttribute('aria-hidden') === 'true') return false;
    return node.offsetParent !== null || node === document.activeElement || getComputedStyle(node).position === 'fixed';
  });
}

/** Trap Tab within a container. Returns a disposer. */
export function trapFocus(container, { initialFocus, onEscape, returnFocusTo } = {}) {
  const previouslyFocused = returnFocusTo || document.activeElement;
  const focusFirst = () => {
    const target = (typeof initialFocus === 'string' ? container.querySelector(initialFocus) : initialFocus)
      || getFocusable(container)[0]
      || container;
    target?.focus?.();
  };
  requestAnimationFrame(focusFirst);

  const onKeydown = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onEscape?.(event);
      return;
    }
    if (event.key !== 'Tab') return;
    const items = getFocusable(container);
    if (!items.length) { event.preventDefault(); return; }
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || !container.contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  };

  document.addEventListener('keydown', onKeydown, true);
  return () => {
    document.removeEventListener('keydown', onKeydown, true);
    if (previouslyFocused && document.contains(previouslyFocused)) previouslyFocused.focus?.();
  };
}

let scrollLockCount = 0;
export function lockScroll() {
  scrollLockCount += 1;
  if (scrollLockCount === 1) {
    const width = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.paddingRight = width > 0 ? `${width}px` : '';
    document.body.classList.add('no-scroll');
  }
}
export function unlockScroll() {
  scrollLockCount = Math.max(0, scrollLockCount - 1);
  if (scrollLockCount === 0) {
    document.body.classList.remove('no-scroll');
    document.body.style.paddingRight = '';
  }
}

/* ============================================================================
   Dialog
   ========================================================================== */

let dialogSeq = 0;

/**
 * Open an accessible modal dialog.
 * @param {{title:string, sub?:string, body:string|HTMLElement, footer?:string,
 *          size?:'narrow'|'wide'|'', onMount?:Function, dismissible?:boolean}} config
 * @returns {{close:Function, element:HTMLElement, body:HTMLElement, setBusy:Function}}
 */
export function openDialog(config) {
  const { title, sub = '', body, footer = '', size = '', onMount, dismissible = true } = config;
  const id = `dialog-${++dialogSeq}`;
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  backdrop.innerHTML = `
    <div class="dialog ${size ? `dialog--${size}` : ''}" role="dialog" aria-modal="true" aria-labelledby="${id}-title" ${sub ? `aria-describedby="${id}-sub"` : ''}>
      <div class="dialog__head">
        <div>
          <h2 class="dialog__title" id="${id}-title">${esc(title)}</h2>
          ${sub ? `<p class="dialog__sub" id="${id}-sub">${esc(sub)}</p>` : ''}
        </div>
        ${dismissible ? `<button type="button" class="icon-btn" data-dialog-close aria-label="Close dialog">${icon('x')}</button>` : ''}
      </div>
      <div class="dialog__body" data-dialog-body></div>
      ${footer ? `<div class="dialog__foot">${footer}</div>` : ''}
    </div>
  `;

  const dialog = backdrop.querySelector('.dialog');
  const bodyEl = backdrop.querySelector('[data-dialog-body]');
  if (typeof body === 'string') bodyEl.innerHTML = body;
  else if (body instanceof HTMLElement) bodyEl.appendChild(body);

  document.body.appendChild(backdrop);
  hydrateIcons(backdrop);
  lockScroll();

  let releaseFocus = null;
  const close = (result) => {
    releaseFocus?.();
    unlockScroll();
    backdrop.remove();
    config.onClose?.(result);
  };

  releaseFocus = trapFocus(dialog, { onEscape: () => dismissible && close(null) });

  backdrop.addEventListener('mousedown', (event) => {
    if (event.target === backdrop && dismissible) close(null);
  });
  backdrop.querySelectorAll('[data-dialog-close]').forEach((btn) => {
    btn.addEventListener('click', () => close(null));
  });

  onMount?.({ element: dialog, body: bodyEl, close });

  return {
    close,
    element: dialog,
    body: bodyEl,
    setBusy(busy) {
      dialog.setAttribute('aria-busy', busy ? 'true' : 'false');
      dialog.querySelectorAll('button, input, select, textarea').forEach((n) => { n.disabled = busy; });
    },
  };
}

/** Accessible confirmation dialog. Resolves true/false. */
export function confirmDialog({
  title = 'Are you sure?', message = '', confirmLabel = 'Confirm',
  cancelLabel = 'Cancel', tone = 'primary',
}) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value) => { if (!settled) { settled = true; resolve(value); } };
    const dlg = openDialog({
      title,
      size: 'narrow',
      body: `<p class="t-sm t-body">${esc(message)}</p>`,
      footer: `
        <button type="button" class="btn btn--secondary" data-cancel>${esc(cancelLabel)}</button>
        <button type="button" class="btn btn--${tone === 'danger' ? 'danger' : 'primary'}" data-confirm>${esc(confirmLabel)}</button>
      `,
      onMount({ element, close }) {
        element.querySelector('[data-cancel]').addEventListener('click', () => { done(false); close(); });
        element.querySelector('[data-confirm]').addEventListener('click', () => { done(true); close(); });
      },
      onClose: () => done(false),
    });
    requestAnimationFrame(() => dlg.element.querySelector('[data-confirm]')?.focus());
  });
}

/* ============================================================================
   Drawer
   ========================================================================== */

/**
 * Wire an existing drawer element + backdrop pair.
 * @param {{drawer:HTMLElement, backdrop:HTMLElement, triggers?:NodeList|Array}} config
 */
export function createDrawer({ drawer, backdrop, triggers = [] }) {
  let releaseFocus = null;
  let open = false;

  const setOpen = (next) => {
    if (next === open) return;
    open = next;
    drawer.classList.toggle('is-open', open);
    backdrop.classList.toggle('is-open', open);
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    triggers.forEach((t) => t.setAttribute('aria-expanded', open ? 'true' : 'false'));

    if (open) {
      lockScroll();
      drawer.removeAttribute('inert');
      releaseFocus = trapFocus(drawer, { onEscape: () => setOpen(false) });
    } else {
      releaseFocus?.();
      releaseFocus = null;
      unlockScroll();
      drawer.setAttribute('inert', '');
    }
  };

  drawer.setAttribute('aria-hidden', 'true');
  drawer.setAttribute('inert', '');
  triggers.forEach((t) => {
    t.setAttribute('aria-expanded', 'false');
    t.addEventListener('click', () => setOpen(!open));
  });
  backdrop.addEventListener('click', () => setOpen(false));
  drawer.querySelectorAll('[data-drawer-close]').forEach((btn) => btn.addEventListener('click', () => setOpen(false)));
  // Close when a navigation link inside the drawer is activated.
  drawer.addEventListener('click', (event) => {
    if (event.target.closest('a[href]')) setOpen(false);
  });

  return { open: () => setOpen(true), close: () => setOpen(false), toggle: () => setOpen(!open), get isOpen() { return open; } };
}

/* ============================================================================
   Skeletons — the only loading affordance
   ========================================================================== */

const sk = (cls = '') => `<span class="sk ${cls}" aria-hidden="true"></span>`;

export const skeletons = {
  productCard() {
    return `<div class="sk-product-card" aria-hidden="true">
      ${sk('sk--media')}
      <div class="sk-product-card__body">
        ${sk('sk--text-sm sk--w-40')}
        ${sk('sk--text sk--w-90')}
        ${sk('sk--text sk--w-60')}
        ${sk('sk--text-lg sk--w-50')}
      </div>
      <div class="sk-product-card__actions">${sk('sk--btn-sm')}${sk('sk--btn-sm')}</div>
    </div>`;
  },

  productGrid(count = 8, columns = 4) {
    return `<div class="product-grid${columns === 5 ? ' product-grid--5' : columns === 3 ? ' product-grid--3' : ''}" aria-hidden="true">
      ${Array.from({ length: count }, () => skeletons.productCard()).join('')}
    </div>`;
  },

  categoryCard() {
    return `<div class="sk-category-card" aria-hidden="true">
      ${sk('sk--wide-media')}
      <div class="sk-category-card__body">
        ${sk('sk--text-lg sk--w-70')}
        ${sk('sk--text-sm sk--w-90')}
        ${sk('sk--text-sm sk--w-40')}
      </div>
    </div>`;
  },

  categoryGrid(count = 4) {
    return `<div class="category-grid" aria-hidden="true">${Array.from({ length: count }, () => skeletons.categoryCard()).join('')}</div>`;
  },

  hero() {
    return `<div class="sk-hero" aria-hidden="true">
      <div class="sk-hero__copy">
        ${sk('sk--pill sk--w-30')}
        ${sk('sk--display sk--w-90')}
        ${sk('sk--display sk--w-70')}
        ${sk('sk--text sk--w-100')}
        ${sk('sk--text sk--w-80')}
        <div class="sk-hero__cta">${sk('sk--btn')}${sk('sk--btn')}</div>
      </div>
      ${sk('sk-hero__media')}
    </div>`;
  },

  productDetail() {
    return `<div class="sk-pdp" aria-hidden="true">
      <div class="sk-pdp__gallery">
        ${sk('sk-pdp__main')}
        <div class="sk-pdp__thumbs">${sk('')}${sk('')}${sk('')}${sk('')}${sk('')}</div>
      </div>
      <div class="sk-pdp__info">
        ${sk('sk--pill sk--w-25')}
        ${sk('sk--title sk--w-90')}
        ${sk('sk--title sk--w-60')}
        ${sk('sk--text sk--w-40')}
        ${sk('sk--display sk--w-50')}
        ${sk('sk--text sk--w-100')}
        ${sk('sk--text sk--w-100')}
        ${sk('sk--text sk--w-70')}
        ${sk('sk--input sk--w-60')}
        <div class="sk-pdp__buy">${sk('sk--btn sk--w-100')}${sk('sk--btn')}</div>
        ${sk('sk--btn')}
      </div>
    </div>`;
  },

  cartLine() {
    return `<div class="sk-line" aria-hidden="true">
      ${sk('sk-line__media')}
      <div class="sk-line__body">
        ${sk('sk--text sk--w-70')}
        ${sk('sk--text-sm sk--w-40')}
        ${sk('sk--btn-sm sk--w-30')}
      </div>
      <div class="sk-line__end">${sk('sk--text-lg sk--w-100')}${sk('sk--text-sm sk--w-60')}</div>
    </div>`;
  },

  lines(count = 3) {
    return `<div aria-hidden="true">${Array.from({ length: count }, () => skeletons.cartLine()).join('')}</div>`;
  },

  summary(rows = 4) {
    return `<div class="stack" aria-hidden="true">
      ${Array.from({ length: rows }, () => `<div class="cluster cluster--between">${sk('sk--text sk--w-30')}${sk('sk--text sk--w-20')}</div>`).join('')}
      ${sk('sk--rule')}
      <div class="cluster cluster--between">${sk('sk--text-lg sk--w-30')}${sk('sk--text-lg sk--w-25')}</div>
      ${sk('sk--btn')}
    </div>`;
  },

  statCard() {
    return `<div class="sk-stat" aria-hidden="true">
      <div class="sk-stat__head">${sk('sk--text-sm sk--w-50')}${sk('sk--icon')}</div>
      ${sk('sk--title sk--w-60')}
      ${sk('sk--text-sm sk--w-40')}
    </div>`;
  },

  statGrid(count = 4) {
    return `<div class="admin-stats" aria-hidden="true">${Array.from({ length: count }, () => skeletons.statCard()).join('')}</div>`;
  },

  table(rows = 6, columns = 5) {
    const template = `grid-template-columns: ${Array.from({ length: columns }, (_, i) => (i === 0 ? '2fr' : '1fr')).join(' ')};`;
    return `<div class="sk-table" aria-hidden="true">
      ${Array.from({ length: rows }, () => `<div class="sk-table__row" style="${template}">${Array.from({ length: columns }, () => sk('')).join('')}</div>`).join('')}
    </div>`;
  },

  list(count = 4) {
    return `<div class="sk-list" aria-hidden="true">
      ${Array.from({ length: count }, () => `<div class="sk-list__item">${sk('sk--thumb')}<div class="sk-list__body">${sk('sk--text sk--w-60')}${sk('sk--text-sm sk--w-30')}</div>${sk('sk--text sk--w-20')}</div>`).join('')}
    </div>`;
  },

  review(count = 2) {
    return `<div aria-hidden="true">${Array.from({ length: count }, () => `
      <div class="sk-review">
        <div class="sk-review__head">${sk('sk--avatar')}${sk('sk--text sk--w-25')}</div>
        ${sk('sk--text sk--w-40')}
        ${sk('sk--text sk--w-100')}
        ${sk('sk--text sk--w-80')}
      </div>`).join('')}</div>`;
  },

  text(lines = 3) {
    const widths = ['sk--w-100', 'sk--w-90', 'sk--w-70', 'sk--w-80', 'sk--w-60'];
    return `<div class="stack stack--sm" aria-hidden="true">${Array.from({ length: lines }, (_, i) => sk(`sk--text ${widths[i % widths.length]}`)).join('')}</div>`;
  },

  form(fields = 4) {
    return `<div class="stack" aria-hidden="true">${Array.from({ length: fields }, () => `<div class="stack stack--sm">${sk('sk--text-sm sk--w-25')}${sk('sk--input')}</div>`).join('')}</div>`;
  },

  chart() {
    return `<div class="stack" aria-hidden="true">${sk('sk--text-sm sk--w-25')}<span class="sk" style="height:220px;border-radius:var(--radius-md)"></span></div>`;
  },
};

/**
 * Mount a skeleton into a region and mark it busy for assistive tech.
 * @param {HTMLElement} region
 * @param {string} html
 * @param {string} [label] announced to screen readers
 */
export function showSkeleton(region, html, label = 'Loading') {
  if (!region) return;
  region.setAttribute('aria-busy', 'true');
  region.dataset.loadingRegion = 'true';
  region.innerHTML = html;
  if (label) announce(label);
}

/** Replace a skeleton with real content. */
export function resolveRegion(region, html, { reveal = true, label = '' } = {}) {
  if (!region) return;
  region.setAttribute('aria-busy', 'false');
  region.innerHTML = html;
  if (reveal) {
    region.classList.add('reveal');
    setTimeout(() => region.classList.remove('reveal'), 300);
  }
  hydrateIcons(region);
  if (label) announce(label);
}

/* ============================================================================
   Empty / error states
   ========================================================================== */

export function emptyState({ title, text = '', iconName = 'inbox', actionHtml = '', inline = false }) {
  return `<div class="state${inline ? ' state--inline' : ''}">
    <span class="state__icon">${icon(iconName, { size: 'xl' })}</span>
    <p class="state__title">${esc(title)}</p>
    ${text ? `<p class="state__text">${esc(text)}</p>` : ''}
    ${actionHtml ? `<div class="state__actions">${actionHtml}</div>` : ''}
  </div>`;
}

export function errorState({ title = 'We could not load this', text = '', retryLabel = 'Try again', retryAttr = 'data-retry', extraHtml = '' }) {
  return `<div class="state state--error">
    <span class="state__icon">${icon('alert-triangle', { size: 'xl' })}</span>
    <p class="state__title">${esc(title)}</p>
    ${text ? `<p class="state__text">${esc(text)}</p>` : ''}
    <div class="state__actions">
      <button type="button" class="btn btn--secondary btn--sm" ${retryAttr}>${icon('refresh', { size: 'sm' })}${esc(retryLabel)}</button>
      ${extraHtml}
    </div>
  </div>`;
}

/**
 * Standard region error handler: renders a retryable error state and wires the
 * retry button to the supplied loader.
 */
export function renderRegionError(region, error, retryFn, { title } = {}) {
  if (!region) return;
  const message = error?.userMessage || error?.message || 'Please try again.';
  resolveRegion(region, errorState({ title: title || 'We could not load this section', text: message }), { reveal: false });
  announce(message, { assertive: true });
  region.querySelector('[data-retry]')?.addEventListener('click', () => retryFn?.(), { once: true });
}

/* ============================================================================
   Forms
   ========================================================================== */

/** Render {field: message} errors onto a form, focusing the first invalid one. */
export function applyFormErrors(form, errors = {}, { focus = true } = {}) {
  clearFormErrors(form);
  let first = null;
  Object.entries(errors).forEach(([name, message]) => {
    const input = form.elements?.[name] ?? form.querySelector(`[name="${CSS.escape(name)}"]`);
    const holder = form.querySelector(`[data-error-for="${CSS.escape(name)}"]`);
    if (input) {
      input.setAttribute('aria-invalid', 'true');
      if (holder) {
        holder.textContent = message;
        if (!input.getAttribute('aria-describedby')?.includes(holder.id)) {
          const described = [input.getAttribute('aria-describedby'), holder.id].filter(Boolean).join(' ');
          input.setAttribute('aria-describedby', described);
        }
      }
      if (!first) first = input;
    } else if (holder) {
      holder.textContent = message;
    }
  });
  const nonField = errors.non_field_errors || errors.detail || errors.__all__;
  const summary = form.querySelector('[data-form-error]');
  if (summary) {
    const text = nonField || (Object.keys(errors).length ? 'Please correct the highlighted fields.' : '');
    if (text) {
      summary.innerHTML = `<span class="alert__icon">${icon('alert-circle')}</span><div class="alert__body"><span class="alert__title">Check your details</span><span>${esc(text)}</span></div>`;
      summary.hidden = false;
      if (!first) first = summary;
    } else {
      summary.hidden = true;
    }
  }
  if (focus && first) {
    first.scrollIntoView({ block: 'center', behavior: 'smooth' });
    first.focus?.({ preventScroll: true });
  }
}

export function clearFormErrors(form) {
  form.querySelectorAll('[aria-invalid="true"]').forEach((n) => n.removeAttribute('aria-invalid'));
  form.querySelectorAll('[data-error-for]').forEach((n) => { n.textContent = ''; });
  const summary = form.querySelector('[data-form-error]');
  if (summary) { summary.hidden = true; summary.innerHTML = ''; }
}

/** Serialize a form to a plain object, honouring checkboxes and multi-selects. */
export function formData(form) {
  const data = {};
  const fd = new FormData(form);
  for (const [key, value] of fd.entries()) {
    if (key in data) {
      data[key] = Array.isArray(data[key]) ? [...data[key], value] : [data[key], value];
    } else {
      data[key] = value;
    }
  }
  // Unchecked checkboxes are absent from FormData; normalise them to false.
  form.querySelectorAll('input[type="checkbox"][name]').forEach((box) => {
    if (!(box.name in data)) data[box.name] = false;
    else if (data[box.name] === 'on') data[box.name] = true;
  });
  return data;
}

/**
 * Submit handler helper: disables the button, shows a text-only pending state
 * (never a spinner), normalizes errors onto the form.
 */
export async function withSubmit(form, button, handler) {
  const original = button?.innerHTML;
  const label = button?.dataset.pendingLabel || 'Working…';
  if (button) {
    button.disabled = true;
    button.innerHTML = `<span class="btn__pending">${esc(label)}</span>`;
  }
  form.setAttribute('aria-busy', 'true');
  try {
    return await handler();
  } catch (error) {
    // Show field messages next to their inputs; anything the form has no
    // input for (and every non-field error) goes into the summary alert so the
    // real reason is never hidden behind a generic message.
    const fieldErrors = error?.fieldErrors || {};
    const shown = {};
    const orphan = [];
    Object.entries(fieldErrors).forEach(([name, message]) => {
      const text = Array.isArray(message) ? message.join(' ') : String(message);
      const known = form.querySelector(`[data-error-for="${CSS.escape(name)}"]`) || form.elements?.[name];
      if (known && !['detail', 'non_field_errors', '__all__'].includes(name)) shown[name] = text;
      else orphan.push(text);
    });
    const general = orphan.join(' ') || (Object.keys(shown).length ? '' : (error?.userMessage || error?.message || 'Something went wrong.'));
    if (general) shown.detail = general;
    applyFormErrors(form, shown);
    throw error;
  } finally {
    if (button) { button.disabled = false; button.innerHTML = original; hydrateIcons(button); }
    form.setAttribute('aria-busy', 'false');
  }
}

/* ============================================================================
   Misc
   ========================================================================== */

/** Pause skeleton shimmer for offscreen regions and hidden tabs. */
export function initSkeletonVisibility() {
  if (typeof IntersectionObserver === 'undefined') return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      entry.target.querySelectorAll('.sk').forEach((node) => {
        node.classList.toggle('is-paused', !entry.isIntersecting);
      });
    });
  }, { rootMargin: '100px' });

  const watch = () => document.querySelectorAll('[data-loading-region]').forEach((r) => observer.observe(r));
  watch();
  document.addEventListener('visibilitychange', () => {
    document.querySelectorAll('.sk').forEach((n) => n.classList.toggle('is-paused', document.hidden));
  });
  return observer;
}

/** Copy text to the clipboard with a toast. */
export async function copyText(text, label = 'Copied to clipboard') {
  try {
    await navigator.clipboard.writeText(text);
    toast(label, { type: 'success' });
    return true;
  } catch {
    toast('Could not copy. Please copy manually.', { type: 'warning' });
    return false;
  }
}

/** Trigger a client-side file download from a Blob. */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'download';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export { icon, hydrateIcons };
