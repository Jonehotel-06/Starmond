/**
 * orders-page.js — customer order history.
 * Access is enforced by the backend; the guard here is UX only.
 */
import boot from '../boot.js';
import { requireAuth } from '../auth.js';
import { listOrders, renderOrderCard } from '../orders.js';
import { resolveRegion, renderRegionError, emptyState, skeletons } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { esc, $, readQuery, buildQuery } from '../utils.js';

await boot();
// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await requireAuth()) {
  const PAGE_SIZE = 10;
  const state = { page: Number(readQuery().page) || 1, status: readQuery().status || '' };

  function renderPagination(count) {
    const nav = $('[data-orders-pagination]');
    const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
    if (pages <= 1) { nav.innerHTML = ''; return; }
    const items = [];
    for (let page = 1; page <= pages; page += 1) {
      const href = `/orders.html${buildQuery({ status: state.status, page: page > 1 ? page : '' })}`;
      items.push(`<a class="pagination__btn" href="${esc(href)}" data-page="${page}" ${page === state.page ? 'aria-current="page"' : ''}>${page}</a>`);
    }
    nav.innerHTML = items.join('');
  }

  async function load() {
    const region = $('[data-orders-list]');
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.list(3);
    try {
      const list = await listOrders({ page: state.page, page_size: PAGE_SIZE, status: state.status || undefined });
      if (!list.results.length) {
        resolveRegion(region, emptyState({
          title: state.status ? 'No orders with that status' : 'You have not placed an order yet',
          text: state.status ? 'Try a different filter.' : 'When you place an order it will appear here with its payment and delivery status.',
          iconName: 'package',
          actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Start shopping</a>',
        }));
        $('[data-orders-pagination]').innerHTML = '';
        return;
      }
      resolveRegion(region, list.results.map(renderOrderCard).join(''));
      renderPagination(list.count);
    } catch (error) {
      renderRegionError(region, error, load, { title: 'Your orders could not be loaded' });
    }
  }

  $('[data-order-status]')?.addEventListener('change', (event) => {
    state.status = event.target.value;
    state.page = 1;
    history.replaceState({}, '', `/orders.html${buildQuery({ status: state.status })}`);
    load();
  });
  if ($('[data-order-status]')) $('[data-order-status]').value = state.status;

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-page]');
    if (!link) return;
    event.preventDefault();
    state.page = Number(link.dataset.page);
    load();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  load();
}
