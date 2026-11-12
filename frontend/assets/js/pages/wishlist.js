/** Wishlist page. Signed-in lists come from the backend; guest lists are local. */
import { ready } from '../app.js';
import { session, wishlist, cart } from '../store.js';
import { renderProducts, productCard } from '../ui/cards.js';
import { toast, notifyError } from '../ui/toast.js';
import { qs, sitePath } from '../utils.js';

const grid = qs('[data-wishlist-grid]');
const emptyEl = qs('[data-wishlist-empty]');
const actionsEl = qs('[data-wish-actions]');
const guestNote = qs('[data-wish-guest]');

function asProduct(entry) {
  if (entry.product) return entry.product;
  return {
    id: entry.id ?? entry.product_id,
    name: entry.name,
    slug: entry.slug,
    price: entry.price,
    compare_at_price: entry.compare_at_price,
    primary_image: entry.primary_image,
    in_stock: entry.in_stock,
    stock_quantity: entry.stock_quantity,
    brand: entry.brand
  };
}

function render() {
  const items = (wishlist.items || []).map(asProduct).filter((p) => p && p.id);
  grid.removeAttribute('aria-busy');
  if (!items.length) {
    grid.innerHTML = '';
    emptyEl.hidden = false;
    actionsEl.hidden = true;
    return;
  }
  emptyEl.hidden = true;
  actionsEl.hidden = false;
  renderProducts(grid, items);
  bindRemoveButtons();
}

function bindRemoveButtons() {
  grid.querySelectorAll('[data-wishlist-toggle]').forEach((button) => {
    button.addEventListener('click', async () => {
      const card = button.closest('.p-card');
      const id = card?.dataset.productId;
      const product = { id: Number(id) };
      try {
        await wishlist.toggle(product);
        toast('Removed from your wishlist.', { type: 'info' });
        render();
      } catch (err) { notifyError(err); }
    });
  });
}

qs('[data-wish-add-all]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  const items = (wishlist.items || []).map(asProduct).filter((p) => p && p.in_stock !== false);
  let added = 0;
  for (const product of items) {
    try {
      await cart.add({ product_id: product.id, quantity: 1 });
      added += 1;
    } catch {
      /* keep going; the toast below reports how many made it in */
    }
  }
  button.disabled = false;
  toast(added ? `${added} item${added === 1 ? '' : 's'} added to your cart.` : 'No in-stock items could be added.',
    { type: added ? 'success' : 'warn' });
});

async function init() {
  await ready;
  if (guestNote) guestNote.hidden = session.isAuthenticated;
  await wishlist.refresh();
  render();
}

init();
