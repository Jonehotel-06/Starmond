/**
 * wishlist.js — authenticated wishlist, backed entirely by the API.
 * A local Set is kept only to render button state without a request per card.
 */

import api, { normalizeList } from './api.js';

const saved = new Set();
let primed = false;
let priming = null;

export async function primeWishlist({ force = false } = {}) {
  if (primed && !force) return saved;
  if (priming && !force) return priming;
  priming = api.privateGet('/wishlist/', { params: { page_size: 200 } })
    .then((data) => {
      saved.clear();
      normalizeList(data).results.forEach((item) => {
        const id = item.product?.id ?? item.product ?? item.product_id;
        if (id !== undefined && id !== null) saved.add(String(id));
      });
      primed = true;
      return saved;
    })
    .finally(() => { priming = null; });
  return priming;
}

export function isWishlisted(productId) { return saved.has(String(productId)); }

export async function toggleWishlist(productId) {
  const id = String(productId);
  if (saved.has(id)) {
    await api.delete(`/wishlist/items/${encodeURIComponent(id)}/`);
    saved.delete(id);
    return false;
  }
  await api.post('/wishlist/items/', { product: productId });
  saved.add(id);
  return true;
}

export async function listWishlist(params = {}) {
  const data = await api.privateGet('/wishlist/', { params });
  const list = normalizeList(data);
  list.results.forEach((item) => {
    const id = item.product?.id ?? item.product ?? item.product_id;
    if (id !== undefined && id !== null) saved.add(String(id));
  });
  primed = true;
  return list;
}

export async function removeFromWishlist(productId) {
  await api.delete(`/wishlist/items/${encodeURIComponent(productId)}/`);
  saved.delete(String(productId));
}

export function resetWishlist() { saved.clear(); primed = false; }

if (typeof window !== 'undefined') {
  window.addEventListener('starmond:auth-changed', (event) => {
    if (event.detail?.status === 'guest') resetWishlist();
  });
}

export default { primeWishlist, toggleWishlist, listWishlist, isWishlisted };
