/** Minimal, accessible modal dialog with focus handling (admin + storefront). */
import { esc } from '../utils.js';

let lastFocused = null;

function root() { return document.querySelector('[data-modal]'); }

export function openModal({ title = 'Dialog', body = '', footer = '', size = '', onMount } = {}) {
  const modal = root();
  if (!modal) return null;
  const dialog = modal.querySelector('.modal__dialog');
  dialog.className = `modal__dialog${size ? ` modal__dialog--${size}` : ''}`;
  modal.querySelector('[data-modal-title]').textContent = title;
  const bodyEl = modal.querySelector('[data-modal-body]');
  bodyEl.innerHTML = body;
  const footEl = modal.querySelector('[data-modal-foot]');
  footEl.innerHTML = footer;
  lastFocused = document.activeElement;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  const focusTarget = dialog.querySelector('[autofocus], input, textarea, select, button');
  (focusTarget || dialog).focus?.();
  modal.addEventListener('keydown', onKeydown);
  if (onMount) onMount({ body: bodyEl, footer: footEl, modal, close: closeModal });
  return { body: bodyEl, footer: footEl, modal, close: closeModal };
}

function onKeydown(event) {
  const modal = root();
  if (!modal || modal.hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeModal(); return; }
  if (event.key !== 'Tab') return;
  const focusables = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

export function closeModal() {
  const modal = root();
  if (!modal) return;
  modal.hidden = true;
  document.body.style.overflow = '';
  modal.removeEventListener('keydown', onKeydown);
  modal.querySelector('[data-modal-body]').innerHTML = '';
  modal.querySelector('[data-modal-foot]').innerHTML = '';
  if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
  lastFocused = null;
}

export function confirmDialog({ title = 'Are you sure?', message = '', confirmLabel = 'Confirm', danger = false } = {}) {
  /* Graceful degradation: without a modal root (e.g. an embedded context),
     fall back to the native confirm so the flow can never dead-end. */
  if (!root()) return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => {
    openModal({
      title,
      size: 'narrow',
      body: `<p>${esc(message)}</p>`,
      footer: `<button class="btn btn--ghost" type="button" data-cancel>Cancel</button>
               <button class="btn ${danger ? 'btn--danger' : 'btn--primary'}" type="button" data-confirm autofocus>${esc(confirmLabel)}</button>`,
      onMount: ({ footer: foot, close }) => {
        foot.querySelector('[data-cancel]').addEventListener('click', () => { close(); resolve(false); });
        foot.querySelector('[data-confirm]').addEventListener('click', () => { close(); resolve(true); });
      }
    });
  });
}

document.addEventListener('click', (event) => {
  if (event.target.closest('[data-modal-close]')) closeModal();
});
