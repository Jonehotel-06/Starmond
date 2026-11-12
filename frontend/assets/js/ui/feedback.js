/** Loading, empty and error states used by every data-driven view. */
import { esc } from '../utils.js';

export function skeletonGrid(container, count = 4) {
  if (!container) return;
  container.setAttribute('aria-busy', 'true');
  container.innerHTML = Array.from({ length: count })
    .map(() => '<div class="p-card p-card--skeleton" aria-hidden="true"></div>').join('');
}

export function skeletonRows(container, count = 3, cols = 5) {
  if (!container) return;
  container.innerHTML = Array.from({ length: count })
    .map(() => `<tr><td colspan="${cols}"><div class="skeleton" style="height:38px"></div></td></tr>`).join('');
}

export function emptyState(container, { title = 'Nothing here yet', message = '', action = '' } = {}) {
  if (!container) return;
  container.removeAttribute('aria-busy');
  container.innerHTML = `<div class="empty-state">
    <svg class="icon icon--lg" aria-hidden="true"><use href="#i-package"></use></svg>
    <h2 class="h2">${esc(title)}</h2>
    ${message ? `<p>${esc(message)}</p>` : ''}
    ${action}
  </div>`;
}

export function errorState(container, err, { retryLabel = 'Try again' } = {}) {
  if (!container) return;
  container.removeAttribute('aria-busy');
  const message = err?.message || 'We could not load this content.';
  const retry = err?.isNetwork || err?.status >= 500
    ? `<button class="btn btn--outline" type="button" data-retry>${esc(retryLabel)}</button>` : '';
  container.innerHTML = `<div class="alert alert--error" role="alert">
      <svg class="icon icon--sm" aria-hidden="true"><use href="#i-close"></use></svg>
      <div><p>${esc(message)}</p>${retry}</div>
    </div>`;
}

export function inlineLoading(container, message = 'Loading…') {
  if (!container) return;
  container.setAttribute('aria-busy', 'true');
  container.innerHTML = `<p class="muted small" role="status">${esc(message)}</p>`;
}
