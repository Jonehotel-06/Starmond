/**
 * STARMOND — Wishlist
 * ----------------------------------------------------------------------------
 * Backend contract (apps/customers, authenticated customers only):
 *   GET  /customers/wishlist/                 → [{id, product, product_name, product_slug, main_image, price, in_stock}]
 *   POST /customers/wishlist/                 {product}
 *   POST /customers/wishlist/remove/          {product}
 *   POST /customers/wishlist/move-to-cart/    {product}
 */

import api, { normalizeList } from './api.js';

const saved = new Set();
let primed = false;
let priming = null;

/** Wishlist row → {id, product:{…card shape…}} so product renderers can be reused. */
function normalizeItem(item) {
  return {
    id: item.id,
    product_id: item.product,
    product: {
      id: item.product,
      name: item.product_name,
      slug: item.product_slug,
      url: `/products/${item.product_slug}/`,
      price: item.price,
      currency: 'NGN',
      images: item.main_image ? [{ url: item.main_image, alt: item.product_name }] : [],
      stock_status: item.in_stock === true ? 'in_stock' : item.in_stock === false ? 'out_of_stock' : null,
      in_stock: item.in_stock,
    },
  };
}

function remember(list) {
  saved.clear();
  list.forEach((item) => { if (item.product_id != null) saved.add(String(item.product_id)); });
  primed = true;
}

export async function primeWishlist({ force = false } = {}) {
  if (primed && !force) return saved;
  if (priming && !force) return priming;
  priming = api.privateGet('/customers/wishlist/')
    .then((data) => { remember(normalizeList(data).results.map(normalizeItem)); return saved; })
    .finally(() => { priming = null; });
  return priming;
}

export function isWishlisted(productId) { return saved.has(String(productId)); }

/** @returns {Promise<boolean>} true when the product is now saved */
export async function toggleWishlist(productId) {
  const id = String(productId);
  if (saved.has(id)) {
    await removeFromWishlist(id);
    return false;
  }
  await api.post('/customers/wishlist/', { product: Number(productId) });
  saved.add(id);
  return true;
}

export async function listWishlist() {
  const data = await api.privateGet('/customers/wishlist/');
  const results = normalizeList(data).results.map(normalizeItem);
  remember(results);
  return { results, count: results.length };
}

export async function removeFromWishlist(productId) {
  await api.post('/customers/wishlist/remove/', { product: Number(productId) });
  saved.delete(String(productId));
}

export function resetWishlist() { saved.clear(); primed = false; }

if (typeof window !== 'undefined') {
  window.addEventListener('starmond:auth-changed', (event) => {
    if (event.detail?.status === 'guest') resetWishlist();
  });
}

export default { primeWishlist, toggleWishlist, listWishlist, isWishlisted, removeFromWishlist };
