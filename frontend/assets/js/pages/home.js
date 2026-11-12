/** Homepage: featured and newest product rails. */
import '../app.js';
import { catalog } from '../api.js';
import { renderProducts } from '../ui/cards.js';
import { skeletonGrid, errorState } from '../ui/feedback.js';
import { qs } from '../utils.js';

const featuredGrid = qs('[data-featured-grid]');
const featuredStatus = qs('[data-featured-status]');
const newGrid = qs('[data-new-grid]');
const newStatus = qs('[data-new-status]');

async function loadRail({ grid, status, query, emptyTitle }) {
  if (!grid) return;
  skeletonGrid(grid, 4);
  try {
    const data = await catalog.products(query);
    renderProducts(grid, data.items.slice(0, 4), { emptyTitle, emptyMessage: 'New stock is added regularly — check the full catalogue.' });
    if (status) {
      status.textContent = data.items.length
        ? ''
        : 'No products are available right now. Please check back shortly.';
    }
  } catch (err) {
    errorState(grid, err);
    grid.querySelector('[data-retry]')?.addEventListener('click', () => loadRail({ grid, status, query, emptyTitle }));
    if (status) status.textContent = '';
  }
}

loadRail({
  grid: featuredGrid,
  status: featuredStatus,
  query: { featured: 1, page_size: 4, ordering: '-created_at' },
  emptyTitle: 'No featured products yet'
});

loadRail({
  grid: newGrid,
  status: newStatus,
  query: { ordering: '-created_at', page_size: 4 },
  emptyTitle: 'No new arrivals yet'
});
