/**
 * search-page.js — full search results with backend pagination and sorting.
 */
import boot from '../boot.js';
import { initSearchPage } from '../search.js';
import { renderProductGrid } from '../products.js';
import { resolveRegion, emptyState, announce } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, buildQuery } from '../utils.js';
import { syncWishlistButtons } from '../shop-actions.js';

await boot();

const PAGE_SIZE = 20;

function renderPagination(list, state) {
  const nav = $('[data-search-pagination]');
  const pages = Math.max(1, Math.ceil(list.count / PAGE_SIZE));
  if (pages <= 1) { nav.innerHTML = ''; return; }
  const items = [];
  for (let page = 1; page <= Math.min(pages, 10); page += 1) {
    items.push(`<button type="button" class="pagination__btn" data-search-page="${page}" ${page === state.page ? 'aria-current="page"' : ''}>${page}</button>`);
  }
  nav.innerHTML = items.join('');
}

const controller = initSearchPage({
  renderGrid(region, list, state) {
    const countNode = $('[data-search-count]');
    if (countNode) countNode.textContent = `${list.count} result${list.count === 1 ? '' : 's'}`;
    if (!list.results.length) {
      resolveRegion(region, emptyState({
        title: `No products match “${state.q}”`,
        text: 'Check the spelling, try a broader term, or browse the catalogue by category.',
        iconName: 'search',
        actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse all products</a>',
      }));
      $('[data-search-pagination]').innerHTML = '';
      return;
    }
    resolveRegion(region, `<div class="product-grid">${renderProductGrid(list.results, { eagerFirst: true })}</div>`);
    syncWishlistButtons();
    renderPagination(list, state);
  },
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-search-page]');
  if (!button) return;
  controller.setPage(Number(button.dataset.searchPage));
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

controller.load();
