/**
 * Checkout.
 *
 * Two entry modes:
 *   ?mode=cart     → the backend cart
 *   ?mode=buy_now  → a backend buy-now session created on the product page.
 *                    The cart is never read or modified in this mode.
 *
 * The frontend validates input, previews totals for the customer, then asks the
 * backend to create the order session and initialise payment. If the backend's
 * authoritative total differs from the preview, the customer is asked to confirm
 * before being sent to Paystack.
 */
import { ready } from '../app.js';
import { account, cart as cartApi, catalog, checkout, payments } from '../api.js';
import { CONFIG } from '../env.js';
import { session, cart } from '../store.js';
import { confirmDialog } from '../ui/modal.js';
import { toast, notifyError } from '../ui/toast.js';
import {
  clearErrors, esc, fieldError, fillStates, money, qs, qsa, sessionForget, sessionStored,
  setBusy, sitePath, store, stored, validate
} from '../utils.js';

const form = qs('[data-checkout-form]');
const itemsEl = qs('[data-checkout-items]');
const methodsEl = qs('[data-shipping-methods]');
const bannerEl = qs('[data-buynow-banner]');
const bannerSummary = qs('[data-buynow-summary]');
const blockedEl = qs('[data-checkout-blocked]');
const accountHint = qs('[data-account-hint]');
const couponStatus = qs('[data-coupon-status]');
const submitBtn = qs('[data-place-order]');
const submitLabel = qs('[data-place-order-label]');
const errorEl = qs('[data-checkout-error]');

const mode = new URLSearchParams(location.search).get('mode') === 'buy_now' ? 'buy_now' : 'cart';
const buyNow = mode === 'buy_now' ? sessionStored(CONFIG.BUY_NOW_KEY, null) : null;

let lineItems = [];
let subtotal = null;
let discount = 0;
let appliedCoupon = '';
let shippingFee = null;
let selectedMethodId = null;
let submitting = false;

/* ------------------------------------------------------------------ helpers */
function displayTotal() {
  if (subtotal === null) return null;
  return Number(subtotal) - Number(discount || 0) + Number(shippingFee || 0);
}

function renderSummary() {
  qs('[data-co-subtotal]').textContent = subtotal === null ? '—' : money(subtotal);
  const discountRow = qs('[data-co-discount-row]');
  if (discountRow) {
    discountRow.hidden = !(discount > 0);
    const dd = qs('[data-co-discount]');
    if (dd) dd.textContent = `−${money(discount)}`;
  }
  const ship = qs('[data-co-shipping]');
  if (ship) ship.textContent = shippingFee === null ? 'Select a delivery method' : money(shippingFee);
  const total = qs('[data-co-total]');
  if (total) total.textContent = displayTotal() === null ? '—' : money(displayTotal());
  if (submitLabel) {
    const amount = displayTotal();
    submitLabel.textContent = amount === null ? 'Pay securely' : `Pay ${money(amount)} securely`;
  }
}

function renderItems() {
  itemsEl.removeAttribute('aria-busy');
  if (!lineItems.length) {
    itemsEl.innerHTML = '<li class="mini-item">No items to check out.</li>';
    return;
  }
  itemsEl.innerHTML = lineItems.map((item) => {
    const product = item.product || {};
    const name = product.name || item.name || 'Product';
    const img = item.image || product.primary_image;
    const imgUrl = typeof img === 'string' ? img : (img?.url || '');
    const variant = item.variant?.name
      || Object.entries(item.variant?.attributes || {}).map(([k, v]) => `${k}: ${v}`).join(' · ');
    return `<li class="mini-item">
      <span class="mini-item__media">${imgUrl ? `<img src="${esc(imgUrl)}" alt="" width="52" height="52" loading="lazy">` : ''}</span>
      <span>
        <span class="mini-item__name">${esc(name)}</span>
        <span class="mini-item__meta">${variant ? `${esc(variant)} · ` : ''}Qty ${esc(item.quantity)}</span>
      </span>
      <span class="mini-item__price">${item.line_total !== undefined ? money(item.line_total) : money(item.unit_price ?? item.price)}</span>
    </li>`;
  }).join('');
}

/* ------------------------------------------------------------- shipping rate */
async function loadShippingMethods(state) {
  methodsEl.setAttribute('aria-busy', 'true');
  methodsEl.innerHTML = '<p class="muted small">Loading delivery options…</p>';
  try {
    const data = await checkout.shippingMethods(state || '');
    const methods = Array.isArray(data) ? data : (data?.methods || data?.results || []);
    if (!methods.length) {
      methodsEl.innerHTML = `<div class="alert alert--warn"><p>No delivery option is available for that state yet. Choose another state or <a href="${sitePath('contact.html')}">contact us</a> with your address so we can arrange delivery.</p></div>`;
      shippingFee = null;
      selectedMethodId = null;
      renderSummary();
      return;
    }
    methodsEl.innerHTML = methods.map((method) => {
      const id = method.id;
      const fee = method.fee ?? method.price ?? method.amount;
      const eta = method.eta || method.estimated_days || method.delivery_time || '';
      const checked = selectedMethodId !== null ? String(selectedMethodId) === String(id) : Boolean(method.is_default);
      return `<label class="radio-card">
        <input type="radio" name="shipping_method" value="${esc(id)}" data-fee="${esc(fee)}"
          ${checked ? 'checked' : ''}>
        <span class="radio-card__body">
          <span class="radio-card__title">${esc(method.name || method.label || 'Delivery')}</span>
          <span class="radio-card__meta">${esc(eta ? `${eta}` : '')}${method.description ? ` · ${esc(method.description)}` : ''}</span>
        </span>
        <span class="radio-card__price">${fee === 0 || fee === '0' || fee === '0.00' ? 'Free' : money(fee)}</span>
      </label>`;
    }).join('');

    qsa('input[name="shipping_method"]', methodsEl).forEach((input) => {
      input.addEventListener('change', () => {
        selectedMethodId = input.value;
        shippingFee = Number(input.dataset.fee);
        fieldError(form, 'shipping_method', '');
        renderSummary();
      });
    });
    const checked = qsa('input[name="shipping_method"]', methodsEl).find((i) => i.checked);
    if (checked) {
      selectedMethodId = checked.value;
      shippingFee = Number(checked.dataset.fee);
    } else {
      selectedMethodId = null;
      shippingFee = null;
    }
    renderSummary();
  } catch (err) {
    methodsEl.innerHTML = `<div class="alert alert--error" role="alert"><div>
      <p>Delivery options could not be loaded.</p><p class="small">${esc(err.message)}</p>
      <button class="btn btn--outline btn--sm" type="button" data-retry-shipping>Try again</button></div></div>`;
    methodsEl.querySelector('[data-retry-shipping]')?.addEventListener('click', () => loadShippingMethods(qs('#co-state').value));
    shippingFee = null;
    renderSummary();
  }
}

/* ---------------------------------------------------------------- validation */
function validateForm() {
  clearErrors(form);
  if (errorEl) errorEl.hidden = true;
  const data = new FormData(form);
  let valid = true;

  const checks = [
    ['email', validate.email(data.get('email'))],
    ['phone', validate.phone(data.get('phone'))],
    ['first_name', validate.required(data.get('first_name'), 'First name')],
    ['last_name', validate.required(data.get('last_name'), 'Last name')],
    ['line1', validate.required(data.get('line1'), 'Street address')],
    ['city', validate.required(data.get('city'), 'City')],
    ['state', validate.required(data.get('state'), 'State')]
  ];
  checks.forEach(([field, message]) => {
    if (message) { fieldError(form, field, message); valid = false; }
  });
  if (!selectedMethodId) { fieldError(form, 'shipping_method', 'Choose a delivery method.'); valid = false; }
  if (!data.get('accept_terms')) { fieldError(form, 'accept_terms', 'Please accept the terms before paying.'); valid = false; }

  if (!valid) {
    const firstInvalid = form.querySelector('[aria-invalid="true"]');
    firstInvalid?.focus();
    firstInvalid?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  return valid;
}

/* -------------------------------------------------------------- persistence */
function saveDraft() {
  if (!form) return;
  const data = new FormData(form);
  const draft = {};
  ['email', 'phone', 'first_name', 'last_name', 'line1', 'line2', 'city', 'state', 'area', 'postal_code', 'delivery_notes']
    .forEach((key) => { draft[key] = data.get(key) || ''; });
  store(CONFIG.CHECKOUT_DRAFT_KEY, draft);
}

function restoreDraft() {
  const draft = stored(CONFIG.CHECKOUT_DRAFT_KEY, null);
  if (!draft) return;
  Object.entries(draft).forEach(([key, value]) => {
    const input = form.querySelector(`[name="${key}"]`);
    if (input && value) input.value = value;
  });
}

/* ------------------------------------------------------------------- coupons */
qs('[data-apply-coupon]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const input = qs('#co-coupon');
  const code = (input.value || '').trim();
  if (!code) { couponStatus.textContent = 'Enter a discount code first.'; couponStatus.className = 'coupon__status small is-error'; return; }
  setBusy(button, true);
  try {
    const result = await checkout.applyCoupon({
      code,
      mode,
      buy_now_token: buyNow?.token || null,
      cart: mode === 'cart'
    });
    const ok = result?.valid !== false && result?.code !== 'invalid';
    if (ok) {
      appliedCoupon = code;
      discount = Number(result.discount_total ?? result.discount ?? 0);
      couponStatus.textContent = result.message || `Code ${code} applied.`;
      couponStatus.className = 'coupon__status small';
    } else {
      appliedCoupon = '';
      discount = 0;
      couponStatus.textContent = result?.message || 'That code is not valid for this order.';
      couponStatus.className = 'coupon__status small is-error';
    }
    renderSummary();
  } catch (err) {
    couponStatus.textContent = err.message;
    couponStatus.className = 'coupon__status small is-error';
    discount = 0;
    appliedCoupon = '';
    renderSummary();
  } finally {
    setBusy(button, false);
  }
});

/* -------------------------------------------------------------------- submit */
async function placeOrder(event) {
  event.preventDefault();
  if (submitting) return;
  if (!validateForm()) {
    if (errorEl) { errorEl.textContent = 'Please correct the highlighted fields.'; errorEl.hidden = false; }
    return;
  }
  saveDraft();
  submitting = true;
  setBusy(submitBtn, true, 'Creating your order…');
  if (errorEl) errorEl.hidden = true;

  const data = new FormData(form);
  const payload = {
    mode,
    buy_now_token: mode === 'buy_now' ? (buyNow?.token || null) : null,
    email: String(data.get('email')).trim(),
    phone: String(data.get('phone')).trim(),
    shipping_method: selectedMethodId,
    coupon_code: appliedCoupon || null,
    delivery_notes: String(data.get('delivery_notes') || '').trim(),
    shipping_address: {
      first_name: String(data.get('first_name')).trim(),
      last_name: String(data.get('last_name')).trim(),
      line1: String(data.get('line1')).trim(),
      line2: String(data.get('line2') || '').trim(),
      city: String(data.get('city')).trim(),
      state: String(data.get('state')).trim(),
      area: String(data.get('area') || '').trim(),
      postal_code: String(data.get('postal_code') || '').trim(),
      country: 'NG'
    }
  };

  try {
    const created = await checkout.createSession(payload);
    const orderId = created?.order_id ?? created?.id ?? created?.order?.id;
    const orderNumber = created?.order_number ?? created?.order?.number;
    const serverTotal = created?.totals?.total ?? created?.total;

    if (serverTotal !== undefined && serverTotal !== null && displayTotal() !== null
        && Math.abs(Number(serverTotal) - Number(displayTotal())) > 0.5) {
      const proceed = await confirmDialog({
        title: 'Your total has been updated',
        message: `The confirmed total for this order is ${money(serverTotal)} (our preview showed ${money(displayTotal())}). Continue to payment?`,
        confirmLabel: 'Continue to payment'
      });
      if (!proceed) {
        setBusy(submitBtn, false);
        submitting = false;
        return;
      }
    }

    const init = await payments.initialize({ order_id: orderId });
    const url = init?.authorization_url || init?.checkout_url || init?.data?.authorization_url;
    const reference = init?.reference || init?.data?.reference || '';
    if (!url) throw new Error('The payment provider did not return a payment link. Please try again.');

    if (reference) {
      sessionStorage.setItem('starmond_last_payment', JSON.stringify({ reference, orderNumber, created: Date.now() }));
    }
    sessionForget(CONFIG.BUY_NOW_KEY);
    window.location.assign(url);
  } catch (err) {
    submitting = false;
    setBusy(submitBtn, false);
    if (err.fields) {
      Object.entries(err.fields).forEach(([field, message]) => fieldError(form, field, message));
    }
    if (errorEl) {
      errorEl.textContent = err.message || 'We could not start the payment. Please try again.';
      errorEl.hidden = false;
      errorEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    if (err.status === 409) {
      /* Stock or price changed between preview and submit. */
      toast('Stock or pricing changed. Please review your order.', { type: 'warn', timeout: 9000 });
      await loadItems();
    }
  }
}

/* ---------------------------------------------------------------- page setup */
async function loadItems() {
  if (mode === 'buy_now') {
    if (!buyNow || !buyNow.token) {
      blockedEl.hidden = false;
      blockedEl.innerHTML = `Your Buy Now session has expired or was not created. 
        <a href="${sitePath('shop.html')}">Choose the product again</a> — your cart has not been changed.`;
      form.querySelectorAll('input, select, textarea, button').forEach((el) => { el.disabled = true; });
      itemsEl.innerHTML = '';
      return false;
    }
    const snapshot = buyNow.line_items || buyNow.items || [];
    lineItems = snapshot;
    subtotal = buyNow.subtotal ?? snapshot.reduce((n, i) => n + Number(i.line_total ?? 0), 0);
    if (bannerEl) {
      bannerEl.hidden = false;
      if (bannerSummary) {
        bannerSummary.textContent = snapshot.length
          ? `${snapshot[0]?.product?.name || 'the selected product'}${snapshot.length > 1 ? ` and ${snapshot.length - 1} more` : ''}`
          : 'the selected item';
      }
    }
    renderItems();
    renderSummary();
    return true;
  }

  try {
    const data = await cartApi.get();
    if (data?.items) cart.hydrate(data);
    lineItems = data?.items || [];
    subtotal = data?.subtotal ?? null;
    discount = Number(data?.discount_total || 0);
    appliedCoupon = data?.applied_discount?.code || '';
    if (!lineItems.length) {
      blockedEl.hidden = false;
      blockedEl.innerHTML = `Your cart is empty, so there is nothing to check out. 
        <a href="${sitePath('shop.html')}">Browse products</a> or 
        <a href="${sitePath('cart.html')}">return to your cart</a>.`;
      qsa('#checkout-title').forEach((n) => n.setAttribute('data-empty', 'true'));
      submitBtn.disabled = true;
      itemsEl.innerHTML = '';
      itemsEl.removeAttribute('aria-busy');
      return false;
    }
    renderItems();
    renderSummary();
    return true;
  } catch (err) {
    blockedEl.hidden = false;
    blockedEl.textContent = `Your cart could not be loaded: ${err.message}`;
    itemsEl.removeAttribute('aria-busy');
    return false;
  }
}

function prefillFromSession() {
  if (!session.isAuthenticated) {
    if (accountHint) accountHint.hidden = true;
    return;
  }
  const user = session.user || {};
  const set = (name, value) => {
    const input = form.querySelector(`[name="${name}"]`);
    if (input && !input.value) input.value = value || '';
  };
  set('email', user.email);
  set('first_name', user.first_name);
  set('last_name', user.last_name);
  set('phone', user.phone);
  if (accountHint) accountHint.hidden = false;

  account.addresses().then((data) => {
    const addresses = Array.isArray(data) ? data : (data?.results || []);
    const preferred = addresses.find((a) => a.is_default) || addresses[0];
    if (!preferred) return;
    set('line1', preferred.line1);
    set('line2', preferred.line2);
    set('city', preferred.city);
    set('state', preferred.state);
    set('area', preferred.area);
    set('postal_code', preferred.postal_code);
    set('phone', preferred.phone || user.phone);
    const stateSelect = qs('#co-state');
    if (stateSelect && preferred.state) stateSelect.value = preferred.state;
    loadShippingMethods(preferred.state);
  }).catch(() => { /* address prefill is a convenience only */ });
}

async function init() {
  await ready;
  fillStates(qs('#co-state'));
  fillStates(qs('#ad-state'));

  if (bannerEl) bannerEl.hidden = mode !== 'buy_now';
  qs('[data-switch-to-cart]')?.addEventListener('click', () => {
    sessionForget(CONFIG.BUY_NOW_KEY);
    window.location.href = `${sitePath('checkout.html')}?mode=cart`;
  });

  const loaded = await loadItems();
  if (!loaded) { renderSummary(); return; }

  restoreDraft();
  prefillFromSession();

  qs('#co-state')?.addEventListener('change', (event) => {
    loadShippingMethods(event.target.value);
    saveDraft();
  });

  form.addEventListener('submit', placeOrder);
  form.addEventListener('change', saveDraft);

  if (!qs('#co-state').value) {
    loadShippingMethods('');
  }

  /* Demo-mode transparency: nothing here pretends a payment succeeded. */
  if (!CONFIG.API_BASE_URL) {
    const note = document.createElement('p');
    note.className = 'small muted';
    note.textContent = 'Demo mode: no backend is connected, so orders and payments cannot be completed. This page shows the full flow with sample data only.';
    form.prepend(note);
  }
}

init();
