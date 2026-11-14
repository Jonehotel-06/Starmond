/**
 * cart-page.js — the shopping cart.
 *
 * Every mutation round-trips to the backend and re-renders from the response.
 * Totals shown here are the backend's estimate; checkout re-validates before
 * payment and any change is surfaced explicitly.
 */

import boot from '../boot.js';
import {
  getCart, updateItem, removeItem, clearCart, applyCoupon, removeCoupon, onCartChange,
} from '../cart.js';
import { productImage, productPrice, PRODUCT_URL, variationLabel, productStock } from '../products.js';
import { skeletons, resolveRegion, renderRegionError, emptyState, toast, confirmDialog, announce } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, debounce } from '../utils.js';
import { BUSINESS_NAME } from '../site.js';

await boot();

let cart = null;

/* ============================================================================
   Render
   ========================================================================== */

function renderChanges() {
  const holder = $('[data-cart-changes]');
  const changes = cart?.changes || [];
  const warnings = cart?.warnings || [];
  const messages = [...changes, ...warnings];
  if (!messages.length) { holder.innerHTML = ''; return; }
  holder.innerHTML = `<div class="alert alert--warning" role="status">
    <span class="alert__icon">${icon('alert-triangle')}</span>
    <div class="alert__body">
      <span class="alert__title">Your cart was updated by the store</span>
      <ul style="padding-left:1rem;margin-top:.25rem">${messages.map((change) => `<li>${esc(typeof change === 'string' ? change : change.message || change.detail || JSON.stringify(change))}</li>`).join('')}</ul>
      <span>Please review the new amounts before you continue to checkout.</span>
    </div>
  </div>`;
  hydrateIcons(holder);
  announce('Your cart was updated by the store. Please review the changes.', { assertive: true });
}

function renderItems() {
  const region = $('[data-cart-items]');
  const items = cart?.items || [];
  $('[data-cart-clear]').hidden = items.length === 0;

  if (!items.length) {
    resolveRegion(region, emptyState({
      title: 'Your cart is empty',
      text: 'Browse the store and add the products you need. Your cart is saved for this browser even before you sign in.',
      iconName: 'cart',
      actionHtml: '<a class="btn btn--primary" href="/shop.html">Start shopping</a>',
    }));
    return;
  }

  const currency = cart.currency || 'NGN';
  resolveRegion(region, `<div class="cart-items">${items.map((item) => {
    const product = item.product || {};
    const image = productImage(product);
    const stock = productStock(product);
    const unit = item.unit_price ?? productPrice(product).current;
    const lineTotal = item.line_total ?? (unit != null ? Number(unit) * Number(item.quantity) : null);
    const max = item.max_quantity ?? product.available_quantity ?? null;
    const unavailable = item.available === false || stock.status === 'out_of_stock';
    return `<article class="cart-item" data-cart-item="${esc(item.id)}">
      <a class="cart-item__media" href="${esc(PRODUCT_URL(product))}" tabindex="-1" aria-hidden="true">
        ${image ? `<img src="${esc(image.url)}" alt="" width="104" height="104" loading="lazy" decoding="async">` : ''}
      </a>
      <div class="cart-item__body">
        <a class="cart-item__name" href="${esc(PRODUCT_URL(product))}">${esc(product.name || 'Product')}</a>
        ${item.variation ? `<span class="t-meta">${esc(variationLabel(item.variation))}</span>` : ''}
        ${product.sku ? `<span class="t-meta">SKU: ${esc(item.variation?.sku || product.sku)}</span>` : ''}
        ${unavailable ? `<span class="badge badge--danger">Currently unavailable</span>` : ''}
        ${item.notice ? `<span class="t-xs t-warning">${esc(item.notice)}</span>` : ''}
        <div class="cart-item__controls">
          <div class="qty qty--sm">
            <button type="button" class="qty__btn" data-cart-decrease="${esc(item.id)}" aria-label="Decrease quantity of ${esc(product.name)}" ${Number(item.quantity) <= 1 ? 'disabled' : ''}>${icon('minus', { size: 'sm' })}</button>
            <label class="sr-only" for="qty-${esc(item.id)}">Quantity of ${esc(product.name)}</label>
            <input class="qty__input" id="qty-${esc(item.id)}" type="number" min="1" ${max ? `max="${esc(max)}"` : ''} value="${esc(item.quantity)}" inputmode="numeric" data-cart-quantity="${esc(item.id)}">
            <button type="button" class="qty__btn" data-cart-increase="${esc(item.id)}" aria-label="Increase quantity of ${esc(product.name)}" ${max && Number(item.quantity) >= Number(max) ? 'disabled' : ''}>${icon('plus', { size: 'sm' })}</button>
          </div>
          <button type="button" class="cart-item__remove" data-cart-remove="${esc(item.id)}">${icon('trash', { size: 'sm' })} Remove</button>
        </div>
      </div>
      <div class="cart-item__end">
        <span class="price price--md">${lineTotal != null ? esc(formatMoney(lineTotal, currency)) : '—'}</span>
        ${unit != null ? `<span class="t-meta">${esc(formatMoney(unit, currency))} each</span>` : ''}
      </div>
    </article>`;
  }).join('')}</div>`);
}

function renderSummary() {
  const region = $('[data-cart-summary]');
  const items = cart?.items || [];
  if (!items.length) {
    resolveRegion(region, '<p class="t-sm t-muted">Add a product to see your order summary.</p>');
    return;
  }
  const currency = cart.currency || 'NGN';
  const totals = cart.totals || {};
  const coupon = cart.coupon || cart.discount_code || null;

  const row = (label, value, cls = '') => `<div class="summary-row ${cls}">
    <span class="summary-row__label">${esc(label)}</span>
    <span class="summary-row__value">${value}</span>
  </div>`;

  resolveRegion(region, `
    <div class="summary-rows">
      ${row(`Subtotal (${cart.quantity_total} item${cart.quantity_total === 1 ? '' : 's'})`, totals.subtotal != null ? esc(formatMoney(totals.subtotal, currency)) : '—')}
      ${Number(totals.discount_total) > 0 ? row('Discount', `−${esc(formatMoney(totals.discount_total, currency))}`, 'summary-row--discount') : ''}
      ${row('Delivery', totals.shipping_estimate != null ? esc(formatMoney(totals.shipping_estimate, currency)) : '<span class="t-meta">Calculated at checkout</span>')}
      ${row('Estimated total', totals.total != null ? esc(formatMoney(totals.total, currency)) : '—', 'summary-row--total')}
    </div>

    ${coupon
      ? `<div class="coupon-applied"><span>${icon('tag', { size: 'sm' })} <strong>${esc(coupon.code || coupon)}</strong> applied</span>
          <button type="button" class="link-btn" data-coupon-remove>Remove</button></div>`
      : `<form class="coupon-form" data-coupon-form novalidate>
          <label class="field__label" for="coupon-code">Discount code</label>
          <div class="input-group">
            <input class="input" id="coupon-code" name="code" type="text" placeholder="Enter code" autocomplete="off">
            <button class="btn btn--secondary" type="submit" data-pending-label="Applying">Apply</button>
          </div>
          <p class="field__error" data-coupon-error role="alert"></p>
        </form>`}

    <a class="btn btn--primary btn--lg btn--block" href="/checkout.html" data-checkout-link>
      Proceed to checkout ${icon('arrow-right', { size: 'sm' })}
    </a>
    <p class="summary-note">Delivery fees and the final payable amount are confirmed by ${esc(BUSINESS_NAME)} at checkout, before you pay. Discounts are validated by the store.</p>
    <div class="cluster cluster--sm" style="justify-content:center">
      <span class="badge badge--neutral">${icon('lock', { size: 'sm' })} Secure Paystack checkout</span>
    </div>
  `);

  const hasUnavailable = items.some((item) => item.available === false);
  const link = region.querySelector('[data-checkout-link]');
  if (hasUnavailable && link) {
    link.classList.add('btn--secondary');
    link.setAttribute('aria-disabled', 'true');
    link.addEventListener('click', (event) => {
      event.preventDefault();
      toast('Remove unavailable items before continuing to checkout.', { type: 'warning' });
    });
  }

  region.querySelector('[data-coupon-form]')?.addEventListener('submit', handleCoupon);
  region.querySelector('[data-coupon-remove]')?.addEventListener('click', async () => {
    try { await removeCoupon(); toast('Discount code removed.', { type: 'success' }); }
    catch (error) { toast(error.userMessage, { type: 'danger' }); }
  });
}

async function handleCoupon(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.querySelector('input[name="code"]');
  const errorNode = form.querySelector('[data-coupon-error]');
  const code = input.value.trim();
  errorNode.textContent = '';
  if (!code) { errorNode.textContent = 'Enter a discount code.'; input.focus(); return; }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  const original = button.innerHTML;
  button.innerHTML = '<span class="btn__pending">Applying</span>';
  try {
    const result = await applyCoupon(code);
    toast(result.message || 'Discount applied.', { type: 'success' });
  } catch (error) {
    errorNode.textContent = error?.fieldErrors?.code?.[0] || error?.userMessage || 'That code could not be applied.';
    announce(errorNode.textContent, { assertive: true });
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
}

/* ============================================================================
   Load + events
   ========================================================================== */

async function load({ force = true } = {}) {
  const itemsRegion = $('[data-cart-items]');
  const summaryRegion = $('[data-cart-summary]');
  itemsRegion.setAttribute('aria-busy', 'true');
  itemsRegion.innerHTML = skeletons.lines(3);
  summaryRegion.setAttribute('aria-busy', 'true');
  summaryRegion.innerHTML = skeletons.summary();
  try {
    cart = await getCart({ force });
    renderChanges();
    renderItems();
    renderSummary();
  } catch (error) {
    renderRegionError(itemsRegion, error, () => load(), { title: 'Your cart could not be loaded' });
    resolveRegion(summaryRegion, '<p class="t-sm t-muted">Summary unavailable.</p>');
  }
}

const debouncedUpdate = debounce(async (itemId, value) => {
  try {
    await updateItem(itemId, value);
  } catch (error) {
    toast(error?.fieldErrors?.quantity?.[0] || error.userMessage || 'Could not update the quantity.', { type: 'danger' });
    load();
  }
}, 450);

function initEvents() {
  document.addEventListener('click', async (event) => {
    const decrease = event.target.closest('[data-cart-decrease]');
    const increase = event.target.closest('[data-cart-increase]');
    const remove = event.target.closest('[data-cart-remove]');

    if (decrease || increase) {
      const id = (decrease || increase).dataset.cartDecrease || (decrease || increase).dataset.cartIncrease;
      const input = document.querySelector(`[data-cart-quantity="${CSS.escape(id)}"]`);
      const current = Number(input.value) || 1;
      const next = decrease ? current - 1 : current + 1;
      if (next < 1) return;
      input.value = String(next);
      debouncedUpdate(id, next);
      return;
    }

    if (remove) {
      const id = remove.dataset.cartRemove;
      const confirmed = await confirmDialog({
        title: 'Remove this item?', message: 'The product will be removed from your cart.',
        confirmLabel: 'Remove', tone: 'danger',
      });
      if (!confirmed) return;
      try { await removeItem(id); toast('Item removed from your cart.', { type: 'success' }); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
      return;
    }

    if (event.target.closest('[data-cart-clear]')) {
      const confirmed = await confirmDialog({
        title: 'Empty your cart?', message: 'All items will be removed. This cannot be undone.',
        confirmLabel: 'Empty cart', tone: 'danger',
      });
      if (!confirmed) return;
      try { await clearCart(); toast('Your cart is now empty.', { type: 'success' }); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }
  });

  document.addEventListener('change', (event) => {
    const input = event.target.closest('[data-cart-quantity]');
    if (!input) return;
    const value = Math.max(1, Math.floor(Number(input.value) || 1));
    const max = Number(input.max);
    if (max && value > max) {
      input.value = String(max);
      toast(`Only ${max} available for this item.`, { type: 'warning' });
      debouncedUpdate(input.dataset.cartQuantity, max);
      return;
    }
    input.value = String(value);
    debouncedUpdate(input.dataset.cartQuantity, value);
  });

  onCartChange((nextCart, reason) => {
    if (!nextCart || reason === 'fetch') return;
    cart = nextCart;
    renderChanges();
    renderItems();
    renderSummary();
  });
}

initEvents();
load();
