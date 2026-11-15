/**
 * checkout-page.js — unified checkout for cart and Buy Now.
 *
 * Buy Now uses an isolated sessionStorage intent and posts mode="buy_now" with
 * explicit line items. The existing cart is never read, mutated or cleared by
 * that path. Both modes call the same backend preview and order services.
 */

import boot from '../boot.js';
import { isAuthenticated, getUser } from '../auth.js';
import { getCart, clearBuyNowIntent, applyCoupon, removeCoupon, getCouponCode, resetCartCache } from '../cart.js';
import {
  currentMode, checkoutLines, previewCheckout, createOrder, getDeliveryOptions,
  getDeliverableStates, buildOrderPayload, validateCheckoutForm, saveAddress, clearCheckoutIdempotency,
} from '../checkout.js';
import { redirectToPaystack } from '../payments.js';
import { productImage, PRODUCT_URL, variationLabel } from '../products.js';
import {
  skeletons, resolveRegion, emptyState, toast, announce, applyFormErrors, clearFormErrors, withSubmit, formData,
} from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, debounce, createStorage, normalizePhone } from '../utils.js';
import { BUSINESS_NAME } from '../site.js';

await boot();

const mode = currentMode(location.search);
const draftStore = createStorage('session');
const state = {
  preview: null,
  deliveryMethod: null,
  deliveryOptions: [],
  couponCode: mode === 'cart' ? (getCouponCode() || null) : null,
  lines: mode === 'buy_now' ? checkoutLines('buy_now') : null,
  submitting: false,
};

/* ============================================================================
   Mode banner
   ========================================================================== */

function renderModeNote() {
  const holder = $('[data-checkout-mode-note]');
  if (mode !== 'buy_now') { holder.innerHTML = ''; return; }
  holder.innerHTML = `<div class="alert alert--info" role="status">
    <span class="alert__icon">${icon('zap')}</span>
    <div class="alert__body">
      <span class="alert__title">Direct purchase</span>
      <span>You are buying only the item shown below. Your existing cart is untouched and will still be there afterwards.
        <a href="/cart.html">View your cart</a> · <a href="/checkout.html">Checkout the whole cart instead</a></span>
    </div>
  </div>`;
  hydrateIcons(holder);
}

function guardBuyNow() {
  if (mode !== 'buy_now') return true;
  if (state.lines?.length) return true;
  const form = $('[data-checkout-form]');
  form.innerHTML = emptyState({
    title: 'This direct purchase has expired',
    text: 'Direct purchase links are held for 30 minutes. Open the product again and choose Buy now, or check out your cart.',
    iconName: 'clock',
    actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse products</a><a class="btn btn--secondary btn--sm" href="/cart.html">View cart</a>',
  });
  hydrateIcons(form);
  return false;
}

/* ============================================================================
   Preview
   ========================================================================== */

function previewPayload() {
  const form = $('[data-checkout-form]');
  const values = form ? formData(form) : {};
  return {
    mode,
    lines: state.lines,
    state: values.state || '',
    deliveryMethod: state.deliveryMethod,
    couponCode: state.couponCode || '',
  };
}

function selectedOption() {
  return state.deliveryOptions.find((o) => String(o.code) === String(state.deliveryMethod)) || null;
}

async function loadPreview({ silent = false } = {}) {
  const itemsRegion = $('[data-checkout-items]');
  const totalsRegion = $('[data-checkout-totals]');
  if (!silent) {
    itemsRegion.setAttribute('aria-busy', 'true');
    itemsRegion.innerHTML = skeletons.lines(2);
    totalsRegion.setAttribute('aria-busy', 'true');
    totalsRegion.innerHTML = skeletons.summary();
  }
  try {
    const preview = await previewCheckout(previewPayload());
    state.preview = preview;
    if (preview.coupon?.code) state.couponCode = preview.coupon.code;
    else if (preview.couponError) { state.couponError = preview.couponError; state.couponCode = null; }
    renderItems();
    renderTotals();
    renderCoupon();
    renderChanges(preview.changes);
    return preview;
  } catch (error) {
    const message = error?.userMessage || 'We could not price this order.';
    resolveRegion(itemsRegion, `<div class="alert alert--danger">
      <span class="alert__icon">${icon('alert-triangle')}</span>
      <div class="alert__body"><span class="alert__title">Order summary unavailable</span><span>${esc(message)}</span></div>
    </div>`);
    resolveRegion(totalsRegion, `<button type="button" class="btn btn--secondary btn--block" data-retry-preview>${icon('refresh', { size: 'sm' })} Try again</button>`);
    $('[data-retry-preview]')?.addEventListener('click', () => loadPreview());
    $('[data-checkout-submit]').disabled = true;
    announce(message, { assertive: true });
    return null;
  }
}

function renderChanges(changes = []) {
  if (!changes.length) return;
  const holder = $('[data-checkout-mode-note]');
  const list = changes.map((change) => `<li>${esc(typeof change === 'string' ? change : change.message || change.detail || '')}</li>`).join('');
  holder.insertAdjacentHTML('beforeend', `<div class="alert alert--warning" role="alert">
    <span class="alert__icon">${icon('alert-triangle')}</span>
    <div class="alert__body">
      <span class="alert__title">Prices or availability changed</span>
      <ul style="padding-left:1rem;margin-top:.25rem">${list}</ul>
      <span>The amounts below are the current, authoritative totals. Please review them before paying.</span>
    </div>
  </div>`);
  hydrateIcons(holder);
  announce('Prices or availability changed. Please review the updated totals.', { assertive: true });
}

function renderItems() {
  const region = $('[data-checkout-items]');
  const items = state.preview?.items || [];
  const currency = state.preview?.currency || 'NGN';
  if (!items.length) {
    resolveRegion(region, emptyState({
      title: 'Nothing to check out', text: 'Your cart is empty.', iconName: 'cart', inline: true,
      actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse products</a>',
    }));
    $('[data-checkout-submit]').disabled = true;
    return;
  }
  resolveRegion(region, `<div>${items.map((item) => {
    const product = item.product || {};
    const image = productImage(product);
    const lineTotal = item.line_total ?? null;
    return `<div class="order-line">
      <span class="order-line__media">
        ${image ? `<img src="${esc(image.url)}" alt="${esc(image.alt || product.name)}" width="72" height="72" loading="lazy" decoding="async">` : ''}
        <span class="order-line__qty" aria-hidden="true">${esc(item.quantity)}</span>
      </span>
      <div class="order-line__body">
        <span class="order-line__name">${esc(product.name || 'Product')}</span>
        ${item.variation ? `<span class="t-meta">${esc(variationLabel(item.variation))}</span>` : ''}
        <span class="t-meta">Qty ${esc(item.quantity)}${item.unit_price != null ? ` · ${esc(formatMoney(item.unit_price, currency))} each` : ''}</span>
      </div>
      <span class="order-line__total price">${lineTotal != null ? esc(formatMoney(lineTotal, currency)) : '—'}</span>
    </div>`;
  }).join('')}</div>`);
  $('[data-checkout-submit]').disabled = false;
}

function renderTotals() {
  const region = $('[data-checkout-totals]');
  const totals = state.preview?.totals || {};
  const currency = state.preview?.currency || 'NGN';
  const row = (label, value, cls = '') => `<div class="summary-row ${cls}"><span class="summary-row__label">${esc(label)}</span><span class="summary-row__value">${value}</span></div>`;
  const money = (value) => (value != null ? esc(formatMoney(value, currency)) : '—');

  const fees = Array.isArray(totals.fees) ? totals.fees : [];
  resolveRegion(region, `
    <div class="summary-rows">
      ${row('Subtotal', money(totals.subtotal))}
      ${Number(totals.discount_total) > 0 ? row('Discount', `−${money(totals.discount_total)}`, 'summary-row--discount') : ''}
      ${row('Delivery', state.deliveryMethod ? money(totals.shipping_total) : '<span class="t-meta">Select a method</span>')}
      ${Number(totals.tax_total) > 0 ? row('Tax', money(totals.tax_total)) : ''}
      ${fees.map((fee) => row(fee.label || fee.name || 'Fee', money(fee.amount))).join('')}
      ${row('Total payable', money(totals.total), 'summary-row--total')}
    </div>
    <p class="summary-note">Amounts are calculated by ${esc(BUSINESS_NAME)} and confirmed again when your order is created. Currency: NGN.</p>
  `);
  const totalNode = $('[data-checkout-total]');
  if (totalNode) totalNode.textContent = totals.total != null ? formatMoney(totals.total, currency) : '—';
  const label = $('[data-submit-label]');
  if (label && totals.total != null) label.textContent = `Pay ${formatMoney(totals.total, currency)} securely`;
}

function renderCoupon() {
  const holder = $('[data-checkout-coupon]');
  if (!holder) return;
  const coupon = state.preview?.coupon;
  if (coupon?.code) {
    holder.innerHTML = `<div class="coupon-applied">
      <span>${icon('tag', { size: 'sm' })} <strong>${esc(coupon.code)}</strong> applied</span>
      <button type="button" class="link-btn" data-coupon-remove>Remove</button>
    </div>`;
    hydrateIcons(holder);
    holder.querySelector('[data-coupon-remove]').addEventListener('click', async () => {
      try {
        if (mode === 'cart') await removeCoupon();
        state.couponCode = null;
        toast('Discount removed.', { type: 'success' });
        loadPreview();
      } catch (error) { toast(error.userMessage, { type: 'danger' }); }
    });
    return;
  }
  // NOTE: this holder lives INSIDE <form data-checkout-form>. A nested <form>
  // is invalid HTML — the parser silently drops it, which previously made
  // querySelector('[data-coupon-form]') null and crashed the whole preview.
  // Use a labelled group with an explicit button instead, and handle Enter.
  holder.innerHTML = `<div class="coupon-form" data-coupon-form>
    <label class="field__label" for="checkout-coupon">Discount code</label>
    <div class="input-group">
      <input class="input" id="checkout-coupon" name="coupon_code" type="text" placeholder="Enter code" autocomplete="off" aria-describedby="checkout-coupon-error">
      <button class="btn btn--secondary" type="button" data-coupon-apply>Apply</button>
    </div>
    <p class="field__error" id="checkout-coupon-error" data-coupon-error role="alert"></p>
  </div>`;

  const group = holder.querySelector('[data-coupon-form]');
  const input = group.querySelector('input[name="coupon_code"]');
  const errorNode = group.querySelector('[data-coupon-error]');
  const applyButton = group.querySelector('[data-coupon-apply]');

  const submitCoupon = async () => {
    const code = input.value.trim();
    errorNode.textContent = '';
    if (!code) { errorNode.textContent = 'Enter a discount code.'; input.focus(); return; }
    applyButton.disabled = true;
    const original = applyButton.textContent;
    applyButton.textContent = 'Applying';
    try {
      if (mode === 'cart') await applyCoupon(code);
      state.couponCode = code;
      await loadPreview();
      if (state.preview?.coupon?.code) toast('Discount applied.', { type: 'success' });
      else {
        const message = state.couponError || 'That code is not eligible for this order.';
        state.couponCode = null; state.couponError = null;
        const node = $('[data-coupon-error]');
        if (node) node.textContent = message;
      }
    } catch (error) {
      errorNode.textContent = error?.fieldErrors?.code?.[0] || error?.userMessage || 'That code could not be applied.';
      state.couponCode = null;
    } finally {
      applyButton.disabled = false;
      applyButton.textContent = original;
    }
  };

  applyButton.addEventListener('click', submitCoupon);
  input.addEventListener('keydown', (event) => {
    // Enter applies the code instead of submitting the outer checkout form.
    if (event.key === 'Enter') { event.preventDefault(); submitCoupon(); }
  });
}

/* ============================================================================
   Delivery
   ========================================================================== */

async function initStates() {
  const select = $('[data-checkout-form] [name="state"]');
  const states = await getDeliverableStates();
  if (!states.length) {
    resolveRegion($('[data-delivery-options]'), `<div class="alert alert--warning">
      <span class="alert__icon">${icon('alert-triangle')}</span>
      <div class="alert__body"><span class="alert__title">Delivery is not configured yet</span>
      <span>The store has not published any delivery areas. Please contact us to place this order.</span></div></div>`);
    $('[data-checkout-submit]').disabled = true;
  }
  select.insertAdjacentHTML('beforeend', states.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join(''));
}

async function loadDeliveryOptions() {
  const region = $('[data-delivery-options]');
  const form = $('[data-checkout-form]');
  const values = formData(form);
  if (!values.state) {
    resolveRegion(region, '<p class="t-sm t-muted">Select your state to see available delivery methods and fees.</p>');
    return;
  }
  region.setAttribute('aria-busy', 'true');
  region.innerHTML = `<div class="stack" aria-hidden="true"><span class="sk sk--input"></span><span class="sk sk--input"></span></div>`;
  try {
    const options = await getDeliveryOptions({
      state: values.state, subtotal: state.preview?.totals?.subtotal ?? null,
    });
    state.deliveryOptions = options;
    if (!options.length) {
      resolveRegion(region, `<div class="alert alert--warning">
        <span class="alert__icon">${icon('alert-triangle')}</span>
        <div class="alert__body"><span class="alert__title">No delivery method is available for this address</span>
        <span>Try a different state or city, or contact us to arrange delivery.</span></div>
      </div>`);
      state.deliveryMethod = null;
      return;
    }
    resolveRegion(region, options.map((option) => `
      <label class="delivery-option">
        <input type="radio" name="delivery_method" value="${esc(option.code)}" ${!option.available ? 'disabled' : ''} ${state.deliveryMethod === option.code ? 'checked' : ''} required>
        <span>
          <span class="delivery-option__name">${esc(option.name)}</span>
          <span class="delivery-option__desc">${esc(option.description || (option.eta ? `Estimated ${option.eta}` : ''))}${!option.available && option.unavailable_reason ? ` — ${esc(option.unavailable_reason)}` : ''}</span>
        </span>
        <span class="delivery-option__price">${option.fee != null ? esc(formatMoney(option.fee, option.currency)) : '—'}</span>
      </label>`).join(''));

    region.querySelectorAll('input[name="delivery_method"]').forEach((input) => {
      input.addEventListener('change', () => {
        state.deliveryMethod = input.value;
        const option = options.find((o) => String(o.code) === String(input.value));
        togglePickupFields(option?.is_pickup);
        loadPreview({ silent: true });
        announce(`${option?.name || 'Delivery method'} selected`);
      });
    });

    // Restore a previously chosen method if it is still offered.
    const previous = region.querySelector(`input[value="${CSS.escape(state.deliveryMethod || '')}"]`);
    if (previous && !previous.disabled) { previous.checked = true; }
    else {
      state.deliveryMethod = null;
      // One method only: select it so the shopper sees the full total at once.
      const inputs = region.querySelectorAll('input[name="delivery_method"]:not([disabled])');
      if (inputs.length === 1) { inputs[0].checked = true; inputs[0].dispatchEvent(new Event('change')); }
    }
    togglePickupFields(selectedOption()?.is_pickup);
  } catch (error) {
    resolveRegion(region, `<div class="alert alert--danger">
      <span class="alert__icon">${icon('alert-triangle')}</span>
      <div class="alert__body"><span class="alert__title">Delivery options unavailable</span>
      <span>${esc(error.userMessage || 'We could not load delivery fees for this address.')}</span>
      <button type="button" class="btn btn--secondary btn--sm" data-retry-delivery style="margin-top:.5rem">Try again</button></div>
    </div>`);
    hydrateIcons(region);
    region.querySelector('[data-retry-delivery]')?.addEventListener('click', loadDeliveryOptions);
  }
}

function togglePickupFields(isPickup) {
  const addressFields = ['address_line1', 'address_line2', 'delivery_instructions'];
  addressFields.forEach((name) => {
    const input = $(`[data-checkout-form] [name="${name}"]`);
    if (!input) return;
    const field = input.closest('.field');
    if (isPickup) {
      field.hidden = true;
      input.removeAttribute('required');
    } else {
      field.hidden = false;
      if (name === 'address_line1') input.setAttribute('required', '');
    }
  });
}

/* ============================================================================
   Prefill
   ========================================================================== */

async function prefill() {
  const form = $('[data-checkout-form]');
  const draft = draftStore.get('checkout_draft', {});
  Object.entries(draft).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input && !input.value && typeof value === 'string') input.value = value;
  });

  if (isAuthenticated()) {
    const user = getUser();
    const setIfEmpty = (name, value) => {
      const input = form.elements[name];
      if (input && !input.value && value) input.value = value;
    };
    setIfEmpty('full_name', user.full_name || [user.first_name, user.last_name].filter(Boolean).join(' '));
    setIfEmpty('email', user.email);
    setIfEmpty('phone', user.phone);
    $('[data-save-address-row]').hidden = false;
    try {
      const data = await import('../api.js').then((m) => m.default.privateGet('/customers/addresses/'));
      const addresses = Array.isArray(data) ? data : data?.results || [];
      const defaultAddress = addresses.find((a) => a.is_default) || addresses[0];
      if (defaultAddress) {
        setIfEmpty('full_name', defaultAddress.full_name);
        setIfEmpty('phone', defaultAddress.phone);
        const stateSelect = form.elements.state;
        if (stateSelect && !stateSelect.value && [...stateSelect.options].some((o) => o.value === defaultAddress.state)) {
          stateSelect.value = defaultAddress.state;
        }
        setIfEmpty('city', defaultAddress.city);
        setIfEmpty('address_line1', defaultAddress.street);
        setIfEmpty('address_line2', defaultAddress.details);
        setIfEmpty('delivery_instructions', defaultAddress.instructions);
      }
    } catch { /* addresses are optional */ }
  }
}

function saveDraft() {
  const form = $('[data-checkout-form]');
  const values = formData(form);
  // Never persist card data (there is none) or the terms checkbox.
  const { full_name, email, phone, state: st, city, address_line1, address_line2 } = values;
  draftStore.set('checkout_draft', { full_name, email, phone, state: st, city, address_line1, address_line2 });
}

/* ============================================================================
   Submit
   ========================================================================== */

async function handleSubmit(event) {
  event.preventDefault();
  if (state.submitting) return;
  const form = event.currentTarget;
  clearFormErrors(form);
  const values = formData(form);
  values.phone = normalizePhone(values.phone);

  const option = selectedOption();
  const pickup = option?.is_pickup ? option : null;
  const errors = validateCheckoutForm(values, { deliveryMethod: state.deliveryMethod, pickup: !!pickup });
  if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

  state.submitting = true;
  const button = $('[data-checkout-submit]');
  try {
    await withSubmit(form, button, async () => {
      saveDraft();
      const payload = buildOrderPayload({
        mode, form: values, deliveryMethod: state.deliveryMethod,
        couponCode: state.couponCode, lines: state.lines, pickup,
      });
      let result;
      try {
        result = await createOrder(payload);
      } catch (error) {
        // Backend field keys ("delivery.street", "contact.email") → form field names.
        if (error?.fieldErrors) {
          const alias = { street: 'address_line1', details: 'address_line2', instructions: 'delivery_instructions', shipping_method_id: 'delivery_method' };
          error.fieldErrors = Object.fromEntries(Object.entries(error.fieldErrors).map(([key, value]) => {
            const name = String(key).split('.').pop();
            return [alias[name] || name, value];
          }));
        }
        throw error;
      }
      if (values.save_address && isAuthenticated() && !pickup) {
        try { await saveAddress(values); } catch { /* saving the address is optional */ }
      }
      if (!result.authorizationUrl) {
        throw new Error('The store created the order but did not return a payment link. Please contact support with your reference.');
      }
      // Only clear the direct-purchase intent, never the cart.
      if (mode === 'buy_now') clearBuyNowIntent();
      else resetCartCache(); // the backend empties the cart once the order exists
      clearCheckoutIdempotency();
      announce('Order created. Redirecting to Paystack for secure payment.');
      toast('Redirecting to Paystack…', { type: 'info', duration: 3000 });
      redirectToPaystack(result.authorizationUrl);
    });
  } catch (error) {
    if (!error?.fieldErrors) {
      toast(error?.message || error?.userMessage || 'We could not start payment. Please try again.', { type: 'danger', title: 'Checkout failed' });
    }
  } finally {
    state.submitting = false;
  }
}

/* ============================================================================
   Init
   ========================================================================== */

async function init() {
  renderModeNote();
  if (!guardBuyNow()) return;

  const form = $('[data-checkout-form]');
  try { await initStates(); } catch { /* the delivery section reports the failure */ }
  await prefill();

  // In cart mode, confirm there is something to buy before pricing.
  if (mode === 'cart') {
    try {
      const cart = await getCart({ force: true });
      if (!cart.items.length) {
        form.innerHTML = emptyState({
          title: 'Your cart is empty', text: 'Add a product before checking out.', iconName: 'cart',
          actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse products</a>',
        });
        hydrateIcons(form);
        return;
      }
    } catch { /* preview will surface the error */ }
  }

  await loadPreview();
  await loadDeliveryOptions();

  const debouncedDelivery = debounce(() => { saveDraft(); loadDeliveryOptions(); loadPreview({ silent: true }); }, 600);
  form.elements.state?.addEventListener('change', debouncedDelivery);
  form.elements.city?.addEventListener('input', debouncedDelivery);
  form.addEventListener('input', debounce(saveDraft, 800));
  form.addEventListener('submit', handleSubmit);
}

init();
