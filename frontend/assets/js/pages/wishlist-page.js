/**
 * wishlist-page.js — saved products for authenticated customers.
 */
import boot from '../boot.js';
import { requireAuth } from '../auth.js';
import { listWishlist, removeFromWishlist } from '../wishlist.js';
import { moveWishlistItemToCart } from '../cart.js';
import { renderProductCard, productImage, PRODUCT_URL, productPrice } from '../products.js';
import { resolveRegion, renderRegionError, emptyState, skeletons, toast, confirmDialog } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { esc, $, formatMoney } from '../utils.js';

await boot();
// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await requireAuth()) {
  async function load() {
    const region = $('[data-wishlist]');
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.productGrid(4);
    try {
      const list = await listWishlist({ page_size: 60 });
      if (!list.results.length) {
        resolveRegion(region, emptyState({
          title: 'Your wishlist is empty',
          text: 'Tap the heart on any product to save it here for later.',
          iconName: 'heart',
          actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse products</a>',
        }));
        return;
      }
      const products = list.results.map((item) => item.product || item).filter((p) => p && p.id);
      resolveRegion(region, `
        <div class="product-grid">${products.map((product) => renderProductCard(product, { showWishlist: true })).join('')}</div>
        <div class="cluster" style="margin-top:var(--space-6)">
          ${products.map((product) => `<button type="button" class="btn btn--ghost btn--sm" data-wishlist-remove="${esc(product.id)}">${icon('trash', { size: 'sm' })} Remove ${esc(product.name)}</button>`).join('')}
        </div>
      `);
      document.querySelectorAll('[data-wishlist-toggle]').forEach((node) => node.setAttribute('aria-pressed', 'true'));
    } catch (error) {
      renderRegionError(region, error, load, { title: 'Your wishlist could not be loaded' });
    }
  }

  document.addEventListener('click', async (event) => {
    const remove = event.target.closest('[data-wishlist-remove]');
    if (!remove) return;
    const confirmed = await confirmDialog({
      title: 'Remove from wishlist?', message: 'You can save it again at any time.', confirmLabel: 'Remove', tone: 'danger',
    });
    if (!confirmed) return;
    try {
      await removeFromWishlist(remove.dataset.wishlistRemove);
      toast('Removed from your wishlist.', { type: 'success' });
      load();
    } catch (error) { toast(error.userMessage, { type: 'danger' }); }
  });

  load();
}
