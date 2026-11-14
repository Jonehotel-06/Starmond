/**
 * shop-actions.js — delegated commerce actions used on every page.
 *
 * One document-level listener handles Add to cart, Buy now and Wishlist toggles
 * for every product card, however it was rendered. Event delegation keeps the
 * DOM cheap and avoids re-binding after each render.
 */

import { addItem, startBuyNow, getCartCount } from './cart.js';
import { toggleWishlist, isWishlisted, primeWishlist } from './wishlist.js';
import { isAuthenticated } from './auth.js';
import { toast, confirmDialog } from './ui.js';
import { hydrateIcons } from './icons.js';
import { esc } from './utils.js';
import api from './api.js';

const busy = new WeakSet();

function cardName(button) {
  return button.closest('[data-product-card]')?.querySelector('.product-card__name')?.textContent?.trim()
    || button.dataset.productName
    || 'Product';
}

async function handleAddToCart(button) {
  if (busy.has(button)) return;
  const productId = button.dataset.productId;
  const variation = button.dataset.variationId || null;
  const quantity = Number(button.dataset.quantity) || 1;
  if (!productId) return;

  busy.add(button);
  const original = button.innerHTML;
  button.disabled = true;
  button.innerHTML = '<span class="btn__pending">Adding</span>';

  try {
    const cart = await addItem({ product: productId, variation, quantity });
    toast(`${cardName(button)} added to your cart.`, {
      type: 'success',
      title: 'Added to cart',
      action: { label: `View cart (${getCartCount(cart)})`, href: '/cart.html' },
    });
    button.innerHTML = original;
    hydrateIcons(button);
  } catch (error) {
    button.innerHTML = original;
    hydrateIcons(button);
    const message = error?.fieldErrors?.quantity?.[0]
      || error?.fieldErrors?.variation?.[0]
      || error?.userMessage
      || 'Could not add this product to your cart.';
    toast(message, { type: 'danger', title: 'Not added' });
  } finally {
    button.disabled = false;
    busy.delete(button);
  }
}

async function handleBuyNow(button) {
  const productId = button.dataset.productId;
  const variation = button.dataset.variationId || null;
  const quantity = Number(button.dataset.quantity) || 1;
  if (!productId) return;

  // Products with options must be configured on the product page first.
  if (button.dataset.requiresVariation === 'true' && !variation) {
    const slug = button.dataset.productSlug || button.closest('[data-product-card]')?.dataset.productSlug;
    if (slug) {
      window.location.assign(`/products/${encodeURIComponent(slug)}/?select=1`);
      return;
    }
    toast('Please choose your options on the product page first.', { type: 'info' });
    return;
  }

  // Buy Now never touches the cart — it opens an isolated checkout intent.
  startBuyNow({ product: productId, variation, quantity });
}

async function handleWishlist(button) {
  if (busy.has(button)) return;
  const productId = button.dataset.productId;
  if (!productId) return;

  if (!isAuthenticated()) {
    const proceed = await confirmDialog({
      title: 'Sign in to save products',
      message: 'Wishlists are kept on your account so you can find them on any device. Sign in or create an account to continue.',
      confirmLabel: 'Sign in',
    });
    if (proceed) {
      window.location.assign(`/login.html?next=${encodeURIComponent(location.pathname + location.search)}`);
    }
    return;
  }

  busy.add(button);
  try {
    const saved = await toggleWishlist(productId);
    document.querySelectorAll(`[data-wishlist-toggle][data-product-id="${CSS.escape(productId)}"]`).forEach((node) => {
      node.setAttribute('aria-pressed', String(saved));
      node.setAttribute('aria-label', `${saved ? 'Remove' : 'Save'} ${cardName(node)} ${saved ? 'from' : 'to'} wishlist`);
    });
    toast(saved ? 'Saved to your wishlist.' : 'Removed from your wishlist.', {
      type: 'success',
      action: saved ? { label: 'View wishlist', href: '/wishlist.html' } : undefined,
    });
    window.dispatchEvent(new CustomEvent('starmond:wishlist-changed', { detail: { productId, saved } }));
  } catch (error) {
    toast(error?.userMessage || 'Could not update your wishlist.', { type: 'danger' });
  } finally {
    busy.delete(button);
  }
}

/** Reflect saved state on any wishlist buttons currently in the DOM. */
export function syncWishlistButtons() {
  document.querySelectorAll('[data-wishlist-toggle][data-product-id]').forEach((node) => {
    const saved = isWishlisted(node.dataset.productId);
    node.setAttribute('aria-pressed', String(saved));
  });
}

export function initCommerceActions() {
  document.addEventListener('click', (event) => {
    const add = event.target.closest('[data-add-to-cart]');
    if (add) { event.preventDefault(); handleAddToCart(add); return; }

    const buy = event.target.closest('[data-buy-now]');
    if (buy) { event.preventDefault(); handleBuyNow(buy); return; }

    const wish = event.target.closest('[data-wishlist-toggle]');
    if (wish) { event.preventDefault(); handleWishlist(wish); return; }
  });

  if (isAuthenticated()) {
    primeWishlist().then(syncWishlistButtons).catch(() => {});
  }
  window.addEventListener('starmond:auth-changed', () => {
    if (isAuthenticated()) primeWishlist().then(syncWishlistButtons).catch(() => {});
  });
  window.addEventListener('starmond:wishlist-changed', syncWishlistButtons);

  // Observe newly rendered cards so their wishlist state is correct.
  if (typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(() => syncWishlistButtons());
    observer.observe(document.body, { childList: true, subtree: true });
  }
}

export { esc, api };
export default initCommerceActions;
