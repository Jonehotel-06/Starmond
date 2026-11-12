/** Accessible, non-blocking status toasts. */
import { esc } from '../utils.js';

const ICONS = { success: 'i-check', error: 'i-close', info: 'i-bell', warn: 'i-bell' };

export function toast(message, { type = 'info', timeout = 5000 } = {}) {
  const stack = document.querySelector('[data-toast-stack]');
  if (!stack) return null;
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  el.innerHTML = `<svg class="icon icon--sm" aria-hidden="true"><use href="#${ICONS[type] || 'i-bell'}"></use></svg>
    <span>${esc(message)}</span>
    <button class="toast__close" type="button" aria-label="Dismiss notification">
      <svg class="icon icon--sm" aria-hidden="true"><use href="#i-close"></use></svg>
    </button>`;
  const remove = () => el.remove();
  el.querySelector('.toast__close').addEventListener('click', remove);
  stack.appendChild(el);
  if (timeout) setTimeout(remove, timeout);
  return el;
}

export const notifyError = (err) => toast(err?.message || 'Something went wrong.', { type: 'error', timeout: 7000 });
export const notifySuccess = (msg) => toast(msg, { type: 'success' });
