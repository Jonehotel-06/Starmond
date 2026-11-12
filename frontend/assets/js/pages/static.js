/**
 * Content pages (about, FAQ, policies, 404, offline) need no page-specific
 * behaviour beyond the shared shell. This module exists so those pages import
 * the same shell pipeline and stay consistent if page-level behaviour is added.
 */
import '../app.js';

document.querySelectorAll('.faq__item').forEach((item) => {
  item.addEventListener('toggle', () => {
    if (!item.open) return;
    /* Only one FAQ answer open at a time keeps the list scannable. */
    item.parentElement?.querySelectorAll('.faq__item[open]').forEach((other) => {
      if (other !== item) other.open = false;
    });
  });
});
