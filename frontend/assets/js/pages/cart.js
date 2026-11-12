/** Cart page: server-backed cart with quantity updates and removal. */
import { ready } from '../app.js';
import { cart, bus } from '../store.js';
import { toast, notifyError } from '../ui/toast.js';
import { confirmDialog } from '../ui/modal.js';
import { esc, money, qs, sitePath, setBusy } from '../utils.js';

const listEl = qs('[data-cart-list]');
const emptyEl = qs('[data-cart-empty]');
const checkoutLink = qs('[data-checkout-link]');
const subtotalEl = qs('[data-summary-subtotal]');
const totalEl = qs('[data-summary-total]');
const discountRow = qs('[data-summary-discount-row]');
const discountEl = qs('[data-summary-discount]');
const expiryEl = qs('[data-cart-expiry]');

function itemImage(item) {
  const p = item.product || {};
  const img = item.image || p.primary_image;
  return typeof img === 'string' ? img : (img?.url || '');
}

function itemName(item) { return item.product?.name || item.name || 'Product'; }
function itemUrl(item) {
  const slug = item.product?.slug || item.slug;
  return slug ? `${sitePath('product.html')}?slug=${encodeURIComponent(slug)}` : sitePath('shop.html');
}
function variantLabel(item) {
  const v = item.variant || item.variation;
  if (!v) return '';
  if (v.name) return v.name;
  const attrs = v.attributes || {};
  return Object.entries(attrs).map(([k, val]) => `${k}: ${val}`).join(' · ');
}

function renderRow(item) {
  const stock = Number(item.available_stock ?? item.product?.stock_quantity ?? Infinity);
  const overStock = Number.isFinite(stock) && stock > 0 && item.quantity > stock;
  const unavailable = item.is_available === false || (Number.isFinite(stock) && stock <= 0);
  const unit = item.unit_price ?? item.price;
  const line = item.line_total ?? item.total;

  return `<article class="cart-row" data-item-id="${esc(item.id)}">
    <div class="cart-row__media">
      ${itemImage(item)
        ? `<img src="${esc(itemImage(item))}" alt="${esc(itemName(item))}" width="96" height="96" loading="lazy">`
        : '<div class="media-placeholder" aria-hidden="true"></div>'}
    </div>
    <div class="cart-row__body">
      <h2 class="cart-row__name"><a href="${itemUrl(item)}">${esc(itemName(item))}</a></h2>
      ${variantLabel(item) ? `<p class="cart-row__variant">${esc(variantLabel(item))}</p>` : ''}
      ${unit !== undefined ? `<p class="cart-row__variant">${money(unit)} each</p>` : ''}
      ${unavailable ? '<p class="cart-row__warn">No longer available — remove to continue.</p>' : ''}
      ${overStock ? `<p class="cart-row__warn">Only ${stock} available. Reduce the quantity to continue.</p>` : ''}
      <div class="cart-row__foot">
        <div class="qty">
          <button class="qty__btn" type="button" data-qty-down aria-label="Decrease quantity of ${esc(itemName(item))}">
            <svg class="icon icon--sm" aria-hidden="true"><use href="#i-minus"></use></svg>
          </button>
          <input class="qty__input" type="number" value="${esc(item.quantity)}" min="1" max="${Number.isFinite(stock) ? Math.max(1, stock) : 99}"
                 inputmode="numeric" aria-label="Quantity of ${esc(itemName(item))}" data-qty-input>
          <button class="qty__btn" type="button" data-qty-up aria-label="Increase quantity of ${esc(itemName(item))}">
            <svg class="icon icon--sm" aria-hidden="true"><use href="#i-plus"></use></svg>
          </button>
        </div>
        <button class="cart-row__remove" type="button" data-remove>
          <svg class="icon icon--sm" aria-hidden="true"><use href="#i-trash"></use></svg>Remove
        </button>
      </div>
    </div>
    <div class="cart-row__prices">
      <span class="price">${line !== undefined ? money(line) : '—'}</span>
    </div>
  </article>`;
}

function render(state) {
  const items = state.items || [];
  listEl.removeAttribute('aria-busy');

  if (!items.length) {
    listEl.innerHTML = '';
    emptyEl.hidden = false;
    if (checkoutLink) {
      checkoutLink.setAttribute('aria-disabled', 'true');
      checkoutLink.setAttribute('tabindex', '-1');
    }
    if (subtotalEl) subtotalEl.textContent = '—';
    if (totalEl) totalEl.textContent = '—';
    if (discountRow) discountRow.hidden = true;
    if (expiryEl) expiryEl.hidden = true;
    return;
  }

  emptyEl.hidden = true;
  listEl.innerHTML = items.map(renderRow).join('');
  if (checkoutLink) {
    checkoutLink.removeAttribute('aria-disabled');
    checkoutLink.removeAttribute('tabindex');
  }

  if (subtotalEl) subtotalEl.textContent = state.subtotal !== null ? money(state.subtotal) : '—';
  if (totalEl) totalEl.textContent = money(state.total ?? state.subtotal);
  if (discountRow && discountEl) {
    const hasDiscount = state.discount_total && Number(state.discount_total) > 0;
    discountRow.hidden = !hasDiscount;
    if (hasDiscount) discountEl.textContent = `−${money(state.discount_total)}`;
  }

  /* Warn if any line is unavailable or over the available stock. */
  const problems = items.filter((item) => {
    const stock = Number(item.available_stock ?? item.product?.stock_quantity ?? Infinity);
    return item.is_available === false || (Number.isFinite(stock) && (stock <= 0 || item.quantity > stock));
  });
  if (expiryEl) {
    expiryEl.hidden = !problems.length;
    if (problems.length) {
      expiryEl.textContent = `${problems.length} item(s) in your cart need attention before checkout. Checkout will confirm availability with our inventory system.`;
    }
  }

  bindRowEvents();
}

function bindRowEvents() {
  listEl.querySelectorAll('[data-item-id]').forEach((row) => {
    const id = row.dataset.itemId;
    const input = row.querySelector('[data-qty-input]');
    const commit = debounceUpdate(id, row, input);

    row.querySelector('[data-qty-down]')?.addEventListener('click', () => {
      input.value = String(Math.max(1, (parseInt(input.value, 10) || 1) - 1));
      commit();
    });
    row.querySelector('[data-qty-up]')?.addEventListener('click', () => {
      const max = Number(input.max) || 99;
      input.value = String(Math.min(max, (parseInt(input.value, 10) || 1) + 1));
      commit();
    });
    input?.addEventListener('change', commit);
    row.querySelector('[data-remove]')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      setBusy(button, true);
      try {
        await cart.remove(id);
        toast('Item removed from your cart.', { type: 'info' });
      } catch (err) {
        notifyError(err);
        setBusy(button, false);
      }
    });
  });
}

function debounceUpdate(id, row, input) {
  let timer = null;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const max = Number(input.max) || 99;
      let qty = parseInt(input.value, 10);
      if (!Number.isFinite(qty) || qty < 1) qty = 1;
      if (qty > max) { qty = max; input.value = String(max); }
      row.style.opacity = '0.6';
      try {
        await cart.update(id, qty);
      } catch (err) {
        notifyError(err);
        await cart.refresh().catch(() => {});
      } finally {
        row.style.opacity = '';
      }
    }, 400);
  };
}

qs('[data-cart-clear]')?.addEventListener('click', async () => {
  const confirmed = await confirmDialog({
    title: 'Empty your cart?',
    message: 'This removes every item from your cart. Saved wishlist items are not affected.',
    confirmLabel: 'Empty cart',
    danger: true
  });
  if (!confirmed) return;
  try {
    await cart.clear();
    toast('Your cart is now empty.', { type: 'info' });
  } catch (err) { notifyError(err); }
});

async function init() {
  await ready;
  bus.on('cart', (state) => { if (listEl) render(state); });
  render(cart.state);
  if (cart.state.loading) {
    listEl.setAttribute('aria-busy', 'true');
  }
  cart.refresh().catch((err) => {
    listEl.removeAttribute('aria-busy');
    listEl.innerHTML = `<div class="alert alert--error" role="alert"><div>
      <p>Your cart could not be loaded.</p><p>${esc(err?.message || '')}</p>
      <button class="btn btn--outline" type="button" data-retry-cart>Try again</button></div></div>`;
    listEl.querySelector('[data-retry-cart]')?.addEventListener('click', () => init());
  });
}

init();
