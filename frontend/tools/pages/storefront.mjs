/**
 * storefront.mjs — page definitions for the public storefront.
 * Each entry produces one static HTML file with real initial content.
 */
import { baseJsonLd, BUSINESS_NAME, escapeHtml } from '../lib/shell.mjs';

const ORIGIN = process.env.SITE_URL || 'https://starmond.example';
const base = baseJsonLd(ORIGIN);

const sk = (cls) => `<span class="sk ${cls}" aria-hidden="true"></span>`;
const productSkeletons = (n = 8) => `<div class="product-grid" aria-hidden="true">${
  Array.from({ length: n }, () => `<div class="sk-product-card">
    ${sk('sk--media')}
    <div class="sk-product-card__body">${sk('sk--text-sm sk--w-40')}${sk('sk--text sk--w-90')}${sk('sk--text sk--w-60')}${sk('sk--text-lg sk--w-50')}</div>
    <div class="sk-product-card__actions">${sk('sk--btn-sm')}${sk('sk--btn-sm')}</div>
  </div>`).join('')}</div>`;
const categorySkeletons = (n = 4) => `<div class="category-grid" aria-hidden="true">${
  Array.from({ length: n }, () => `<div class="sk-category-card">${sk('sk--wide-media')}<div class="sk-category-card__body">${sk('sk--text-lg sk--w-70')}${sk('sk--text-sm sk--w-90')}${sk('sk--text-sm sk--w-40')}</div></div>`).join('')}</div>`;
const lineSkeletons = (n = 3) => `<div aria-hidden="true">${Array.from({ length: n }, () => `<div class="sk-line">${sk('sk-line__media')}<div class="sk-line__body">${sk('sk--text sk--w-70')}${sk('sk--text-sm sk--w-40')}${sk('sk--btn-sm sk--w-30')}</div><div class="sk-line__end">${sk('sk--text-lg sk--w-100')}${sk('sk--text-sm sk--w-60')}</div></div>`).join('')}</div>`;
const summarySkeleton = `<div class="stack" aria-hidden="true">${
  Array.from({ length: 4 }, () => `<div class="cluster cluster--between">${sk('sk--text sk--w-30')}${sk('sk--text sk--w-20')}</div>`).join('')
}${sk('sk--rule')}<div class="cluster cluster--between">${sk('sk--text-lg sk--w-30')}${sk('sk--text-lg sk--w-25')}</div>${sk('sk--btn')}</div>`;

/* ============================================================================
   Homepage
   ========================================================================== */

const homeBody = `
<section class="hero" aria-labelledby="hero-title">
  <div class="container">
    <div class="hero__grid" data-hero-region>
      <div class="hero__copy">
        <span class="hero__eyebrow" data-hero-eyebrow><i data-icon="zap" data-size="sm"></i> Multi-category store</span>
        <h1 class="hero__title" id="hero-title" data-hero-title>Electricals, fashion, electronics and home essentials — in one store.</h1>
        <p class="hero__text" data-hero-text>${BUSINESS_NAME} supplies electrical installation materials, clothing, gadgets, accessories and household products to customers across Nigeria.</p>
        <div class="hero__actions">
          <a class="btn btn--primary btn--lg" href="/shop.html" data-hero-primary>Shop now <i data-icon="arrow-right" data-size="sm"></i></a>
          <a class="btn btn--secondary btn--lg" href="#categories" data-hero-secondary>Explore categories</a>
        </div>
        <div class="hero__meta">
          <span class="hero__meta-item"><i data-icon="truck" data-size="sm"></i> Nationwide delivery</span>
          <span class="hero__meta-item"><i data-icon="shield" data-size="sm"></i> Secure Paystack checkout</span>
          <span class="hero__meta-item"><i data-icon="headphones" data-size="sm"></i> Customer support</span>
        </div>
      </div>
      <div class="hero__media hero__media--empty" data-hero-media>
        <span class="hero__placeholder">
          <i data-icon="image" data-size="xl"></i>
          <span class="t-meta">Featured imagery is managed in the admin console.</span>
        </span>
      </div>
    </div>
  </div>
</section>

<section class="section" id="categories" aria-labelledby="categories-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <span class="t-eyebrow">Departments</span>
        <h2 class="section-head__title" id="categories-title">Shop by category</h2>
        <p class="section-head__sub">Browse every department in the store. New categories appear here automatically.</p>
      </div>
      <a class="btn btn--ghost btn--sm" href="/shop.html">All categories <i data-icon="arrow-right" data-size="sm"></i></a>
    </div>
    <div data-home-categories data-loading-region aria-busy="true">${categorySkeletons(4)}</div>
  </div>
</section>

<section class="section section--alt" aria-labelledby="featured-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <span class="t-eyebrow">Hand-picked</span>
        <h2 class="section-head__title" id="featured-title">Featured products</h2>
        <p class="section-head__sub">Products selected by our team.</p>
      </div>
      <a class="btn btn--ghost btn--sm" href="/shop.html?featured=1">View all <i data-icon="arrow-right" data-size="sm"></i></a>
    </div>
    <div data-home-featured data-loading-region aria-busy="true">${productSkeletons(4)}</div>
  </div>
</section>

<section class="section" aria-labelledby="new-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <span class="t-eyebrow">Just landed</span>
        <h2 class="section-head__title" id="new-title">New arrivals</h2>
        <p class="section-head__sub">The most recently published products in the store.</p>
      </div>
      <a class="btn btn--ghost btn--sm" href="/shop.html?sort=newest">View all <i data-icon="arrow-right" data-size="sm"></i></a>
    </div>
    <div data-home-new data-loading-region aria-busy="true">${productSkeletons(4)}</div>
  </div>
</section>

<section class="section section--tight" data-home-promo-section hidden>
  <div class="container"><div data-home-promo></div></div>
</section>

<section class="section section--alt" aria-labelledby="best-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <span class="t-eyebrow">Customer favourites</span>
        <h2 class="section-head__title" id="best-title">Best sellers</h2>
        <p class="section-head__sub">Ranked by confirmed sales recorded in our order system.</p>
      </div>
    </div>
    <div data-home-best data-loading-region aria-busy="true">${productSkeletons(4)}</div>
  </div>
</section>

<section class="section" data-home-trust-section aria-labelledby="trust-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <h2 class="section-head__title" id="trust-title">Why shop with us</h2>
      </div>
    </div>
    <div class="trust-grid" data-home-trust>
      <div class="trust-item">
        <span class="trust-item__icon"><i data-icon="truck"></i></span>
        <span><span class="trust-item__title">Delivery across Nigeria</span><span class="trust-item__text">Delivery options and fees are shown at checkout before you pay.</span></span>
      </div>
      <div class="trust-item">
        <span class="trust-item__icon"><i data-icon="shield"></i></span>
        <span><span class="trust-item__title">Secure payment</span><span class="trust-item__text">Card and bank payments are processed by Paystack on their own secure page.</span></span>
      </div>
      <div class="trust-item">
        <span class="trust-item__icon"><i data-icon="receipt"></i></span>
        <span><span class="trust-item__title">Order tracking</span><span class="trust-item__text">Follow your order from confirmation through to delivery.</span></span>
      </div>
      <div class="trust-item">
        <span class="trust-item__icon"><i data-icon="headphones"></i></span>
        <span><span class="trust-item__title">Customer support</span><span class="trust-item__text">Reach our team through the contact page for help with any order.</span></span>
      </div>
    </div>
  </div>
</section>

<section class="section section--alt" data-home-reviews-section aria-labelledby="reviews-title">
  <div class="container">
    <div class="section-head">
      <div class="section-head__text">
        <span class="t-eyebrow">Verified feedback</span>
        <h2 class="section-head__title" id="reviews-title">What customers say</h2>
        <p class="section-head__sub">Approved reviews from customers who bought from this store.</p>
      </div>
    </div>
    <div data-home-reviews data-loading-region aria-busy="true">
      <div class="grid grid--3" aria-hidden="true">
        ${Array.from({ length: 3 }, () => `<div class="panel stack">${sk('sk--text sk--w-30')}${sk('sk--text sk--w-100')}${sk('sk--text sk--w-90')}${sk('sk--text sk--w-50')}</div>`).join('')}
      </div>
    </div>
  </div>
</section>

<section class="section section--tight">
  <div class="container">
    <div class="newsletter">
      <div class="stack stack--sm">
        <h2 class="section-head__title">Stay in the loop</h2>
        <p class="t-sm t-muted">Get product updates and offers from ${BUSINESS_NAME}. You can unsubscribe at any time.</p>
      </div>
      <form class="newsletter__form" data-newsletter-form novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="newsletter__row">
          <label class="sr-only" for="newsletter-email">Email address</label>
          <input class="input" id="newsletter-email" name="email" type="email" required placeholder="you@example.com" autocomplete="email">
          <button class="btn btn--primary" type="submit" data-pending-label="Subscribing">Subscribe</button>
        </div>
        <label class="checkbox">
          <input type="checkbox" name="consent" required>
          <span>I agree to receive marketing emails and accept the <a href="/policies/privacy.html">privacy policy</a>.</span>
        </label>
        <p class="field__error" data-error-for="email" id="newsletter-email-error"></p>
        <p class="field__error" data-error-for="consent" id="newsletter-consent-error"></p>
      </form>
    </div>
  </div>
</section>
`;

/* ============================================================================
   Listing (shop + category)
   ========================================================================== */

function listingBody({ isCategory }) {
  return `
<div class="container">
  <div class="page-head">
    <div data-listing-breadcrumbs>
      <nav class="breadcrumbs" aria-label="Breadcrumb">
        <ol class="breadcrumbs__list">
          <li class="breadcrumbs__item"><a href="/">Home</a></li>
          <li class="breadcrumbs__item"><span aria-current="page">Shop</span></li>
        </ol>
      </nav>
    </div>
    <h1 class="page-head__title" data-listing-title>${isCategory ? 'Category' : 'All products'}</h1>
    <p class="page-head__sub" data-listing-description>${isCategory ? '' : 'Browse the full catalogue. Filter by category, price, brand, availability and product attributes.'}</p>
  </div>
  <div data-listing-banner></div>
  <div data-listing-subcategories></div>

  <div class="listing">
    <aside class="listing__sidebar" id="filters" data-filters aria-label="Product filters">
      <div class="cluster cluster--between">
        <h2 class="t-md t-semibold">Filters</h2>
        <button type="button" class="link-btn" data-filters-clear>Clear all</button>
      </div>
      <div data-filters-body>
        <div class="stack" aria-hidden="true">
          ${Array.from({ length: 3 }, () => `<div class="filter-group stack stack--sm">${sk('sk--text sk--w-40')}${sk('sk--input')}${sk('sk--text sk--w-70')}${sk('sk--text sk--w-60')}</div>`).join('')}
        </div>
      </div>
    </aside>

    <div class="listing__main">
      <div class="listing-toolbar">
        <p class="listing-toolbar__count" data-listing-count aria-live="polite"></p>
        <div class="listing-toolbar__controls">
          <button type="button" class="btn btn--secondary btn--sm mobile-filter-trigger" data-filters-toggle aria-expanded="false" aria-controls="filters">
            <i data-icon="filter" data-size="sm"></i> Filters
          </button>
          <label class="sr-only" for="listing-sort">Sort products</label>
          <select class="select" id="listing-sort" data-listing-sort>
            <option value="featured">Featured</option>
            <option value="newest">Newest</option>
            <option value="price_asc">Price: low to high</option>
            <option value="price_desc">Price: high to low</option>
            <option value="best_selling">Best selling</option>
            <option value="rating">Highest rated</option>
          </select>
        </div>
      </div>
      <div class="active-filters" data-active-filters></div>
      <div data-listing-results data-loading-region aria-busy="true">${productSkeletons(8)}</div>
      <nav class="pagination" data-listing-pagination aria-label="Product pagination"></nav>
    </div>
  </div>
</div>
`;
}

/* ============================================================================
   Product detail
   ========================================================================== */

const productBody = `
<div class="container">
  <div class="page-head" data-product-breadcrumbs>
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <ol class="breadcrumbs__list">
        <li class="breadcrumbs__item"><a href="/">Home</a></li>
        <li class="breadcrumbs__item"><a href="/shop.html">Shop</a></li>
        <li class="breadcrumbs__item"><span aria-current="page">Product</span></li>
      </ol>
    </nav>
  </div>

  <div data-product-region data-loading-region aria-busy="true">
    <h1 class="pdp__title pdp__title--pending">Product details</h1>
    <div class="sk-pdp" aria-hidden="true">
      <div class="sk-pdp__gallery">${sk('sk-pdp__main')}<div class="sk-pdp__thumbs">${sk('')}${sk('')}${sk('')}${sk('')}${sk('')}</div></div>
      <div class="sk-pdp__info">
        ${sk('sk--pill sk--w-25')}${sk('sk--title sk--w-90')}${sk('sk--title sk--w-60')}${sk('sk--text sk--w-40')}
        ${sk('sk--display sk--w-50')}${sk('sk--text sk--w-100')}${sk('sk--text sk--w-100')}${sk('sk--text sk--w-70')}
        ${sk('sk--input sk--w-60')}
        <div class="sk-pdp__buy">${sk('sk--btn sk--w-100')}${sk('sk--btn')}</div>
        ${sk('sk--btn')}
      </div>
    </div>
  </div>

  <section class="pdp-section" data-product-tabs hidden>
    <div class="tabs" role="tablist" aria-label="Product information">
      <button class="tabs__btn" role="tab" id="tab-desc" aria-controls="panel-desc" aria-selected="true">Description</button>
      <button class="tabs__btn" role="tab" id="tab-specs" aria-controls="panel-specs" aria-selected="false" tabindex="-1">Specifications</button>
      <button class="tabs__btn" role="tab" id="tab-delivery" aria-controls="panel-delivery" aria-selected="false" tabindex="-1">Delivery &amp; returns</button>
      <button class="tabs__btn" role="tab" id="tab-reviews" aria-controls="panel-reviews" aria-selected="false" tabindex="-1">Reviews</button>
    </div>
    <div class="tabpanel" role="tabpanel" id="panel-desc" aria-labelledby="tab-desc" tabindex="0"><div class="prose" data-product-description></div></div>
    <div class="tabpanel" role="tabpanel" id="panel-specs" aria-labelledby="tab-specs" tabindex="0" hidden><div data-product-specs></div></div>
    <div class="tabpanel" role="tabpanel" id="panel-delivery" aria-labelledby="tab-delivery" tabindex="0" hidden><div class="prose" data-product-delivery></div></div>
    <div class="tabpanel" role="tabpanel" id="panel-reviews" aria-labelledby="tab-reviews" tabindex="0" hidden><div data-product-reviews></div></div>
  </section>

  <section class="section" data-related-section hidden aria-labelledby="related-title">
    <div class="section-head"><div class="section-head__text"><h2 class="section-head__title" id="related-title">Related products</h2></div></div>
    <div data-related-products data-loading-region></div>
  </section>

  <section class="section section--tight" data-recent-section hidden aria-labelledby="recent-title">
    <div class="section-head"><div class="section-head__text"><h2 class="section-head__title" id="recent-title">Recently viewed</h2></div></div>
    <div data-recent-products></div>
  </section>
</div>
`;

/* ============================================================================
   Cart
   ========================================================================== */

const cartBody = `
<div class="container">
  <div class="page-head">
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <ol class="breadcrumbs__list">
        <li class="breadcrumbs__item"><a href="/">Home</a></li>
        <li class="breadcrumbs__item"><span aria-current="page">Cart</span></li>
      </ol>
    </nav>
    <h1 class="page-head__title">Your cart</h1>
    <p class="page-head__sub">Prices and availability are confirmed by the store before payment.</p>
  </div>

  <div class="cart-layout">
    <div class="stack stack--lg">
      <div data-cart-changes></div>
      <div class="panel">
        <div data-cart-items data-loading-region aria-busy="true">${lineSkeletons(3)}</div>
      </div>
      <div class="cluster cluster--between">
        <a class="btn btn--ghost" href="/shop.html"><i data-icon="arrow-left" data-size="sm"></i> Continue shopping</a>
        <button type="button" class="btn btn--ghost btn--sm" data-cart-clear hidden><i data-icon="trash" data-size="sm"></i> Empty cart</button>
      </div>
    </div>

    <aside class="panel summary-card" aria-labelledby="cart-summary-title">
      <h2 class="t-md t-semibold" id="cart-summary-title">Order summary</h2>
      <div data-cart-summary data-loading-region aria-busy="true">${summarySkeleton}</div>
    </aside>
  </div>
</div>
`;

/* ============================================================================
   Checkout
   ========================================================================== */

const checkoutBody = `
<div class="container">
  <div class="page-head">
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <ol class="breadcrumbs__list">
        <li class="breadcrumbs__item"><a href="/">Home</a></li>
        <li class="breadcrumbs__item"><a href="/cart.html">Cart</a></li>
        <li class="breadcrumbs__item"><span aria-current="page">Checkout</span></li>
      </ol>
    </nav>
    <h1 class="page-head__title">Checkout</h1>
    <div class="checkout-steps" aria-label="Checkout progress">
      <span class="checkout-step is-active"><span class="checkout-step__num">1</span> Your details</span>
      <i data-icon="chevron-right" data-size="sm"></i>
      <span class="checkout-step"><span class="checkout-step__num">2</span> Delivery</span>
      <i data-icon="chevron-right" data-size="sm"></i>
      <span class="checkout-step"><span class="checkout-step__num">3</span> Payment</span>
    </div>
  </div>

  <div data-checkout-mode-note></div>

  <form class="checkout-layout" data-checkout-form novalidate>
    <div class="checkout-main">
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>

      <section class="panel form-section" aria-labelledby="checkout-contact-title">
        <h2 class="form-section__title" id="checkout-contact-title"><span class="form-section__num">1</span> Contact details</h2>
        <p class="t-sm t-muted" data-auth-guest>Checking out as a guest. <a href="/login.html?next=%2Fcheckout.html">Sign in</a> to use your saved details.</p>
        <div class="form-grid">
          <div class="field form-grid__full">
            <label class="field__label" for="co-fullname">Full name <span class="field__req" aria-hidden="true">*</span></label>
            <input class="input" id="co-fullname" name="full_name" type="text" required autocomplete="name" aria-describedby="err-fullname">
            <p class="field__error" data-error-for="full_name" id="err-fullname"></p>
          </div>
          <div class="field">
            <label class="field__label" for="co-email">Email address <span class="field__req" aria-hidden="true">*</span></label>
            <input class="input" id="co-email" name="email" type="email" required autocomplete="email" inputmode="email" aria-describedby="err-email hint-email">
            <p class="field__hint" id="hint-email">Your receipt and order updates are sent here.</p>
            <p class="field__error" data-error-for="email" id="err-email"></p>
          </div>
          <div class="field">
            <label class="field__label" for="co-phone">Phone number <span class="field__req" aria-hidden="true">*</span></label>
            <input class="input" id="co-phone" name="phone" type="tel" required autocomplete="tel" inputmode="tel" placeholder="08012345678" aria-describedby="err-phone">
            <p class="field__error" data-error-for="phone" id="err-phone"></p>
          </div>
        </div>
      </section>

      <section class="panel form-section" aria-labelledby="checkout-delivery-title">
        <h2 class="form-section__title" id="checkout-delivery-title"><span class="form-section__num">2</span> Delivery address</h2>
        <div class="form-grid">
          <div class="field">
            <label class="field__label" for="co-state">State <span class="field__req" aria-hidden="true">*</span></label>
            <select class="select" id="co-state" name="state" required aria-describedby="err-state">
              <option value="">Select your state</option>
            </select>
            <p class="field__error" data-error-for="state" id="err-state"></p>
          </div>
          <div class="field">
            <label class="field__label" for="co-city">City / town <span class="field__req" aria-hidden="true">*</span></label>
            <input class="input" id="co-city" name="city" type="text" required autocomplete="address-level2" aria-describedby="err-city">
            <p class="field__error" data-error-for="city" id="err-city"></p>
          </div>
          <div class="field form-grid__full">
            <label class="field__label" for="co-address">Delivery address <span class="field__req" aria-hidden="true">*</span></label>
            <input class="input" id="co-address" name="address_line1" type="text" required autocomplete="address-line1" placeholder="Street number and name" aria-describedby="err-address">
            <p class="field__error" data-error-for="address_line1" id="err-address"></p>
          </div>
          <div class="field form-grid__full">
            <label class="field__label" for="co-address2">Additional address details <span class="t-muted t-xs">(optional)</span></label>
            <input class="input" id="co-address2" name="address_line2" type="text" autocomplete="address-line2" placeholder="Apartment, estate, landmark">
          </div>
          <div class="field form-grid__full">
            <label class="field__label" for="co-instructions">Delivery instructions <span class="t-muted t-xs">(optional)</span></label>
            <textarea class="textarea" id="co-instructions" name="delivery_instructions" rows="2" maxlength="500" placeholder="Anything the delivery rider should know"></textarea>
          </div>
        </div>
        <label class="checkbox" data-save-address-row hidden>
          <input type="checkbox" name="save_address" value="true">
          <span>Save this address to my account</span>
        </label>
      </section>

      <section class="panel form-section" aria-labelledby="checkout-method-title">
        <h2 class="form-section__title" id="checkout-method-title"><span class="form-section__num">3</span> Delivery method</h2>
        <div class="delivery-options" data-delivery-options data-loading-region aria-busy="true">
          <div class="stack" aria-hidden="true">${Array.from({ length: 2 }, () => sk('sk--input')).join('')}</div>
        </div>
        <p class="field__error" data-error-for="delivery_method" id="err-delivery"></p>
      </section>

      <section class="panel form-section" aria-labelledby="checkout-payment-title">
        <h2 class="form-section__title" id="checkout-payment-title"><span class="form-section__num">4</span> Payment</h2>
        <div class="paystack-note">
          <i data-icon="lock" data-size="sm"></i>
          <span>You will be redirected to Paystack to complete payment securely. ${BUSINESS_NAME} never sees or stores your card details. Your order is only confirmed after Paystack payment is verified by our system.</span>
        </div>
        <label class="checkbox">
          <input type="checkbox" name="accept_terms" required aria-describedby="err-terms">
          <span>I have read and accept the <a href="/policies/terms.html" target="_blank" rel="noopener">terms and conditions</a> and the <a href="/policies/returns.html" target="_blank" rel="noopener">returns policy</a>. <span class="field__req" aria-hidden="true">*</span></span>
        </label>
        <p class="field__error" data-error-for="accept_terms" id="err-terms"></p>
        <button class="btn btn--primary btn--lg btn--block" type="submit" data-checkout-submit data-pending-label="Preparing secure payment">
          <i data-icon="lock" data-size="sm"></i> <span data-submit-label>Continue to payment</span>
        </button>
        <p class="summary-note t-center">Total payable: <strong class="price" data-checkout-total>—</strong></p>
      </section>
    </div>

    <aside class="panel checkout-summary" aria-labelledby="checkout-summary-title">
      <h2 class="t-md t-semibold" id="checkout-summary-title">Order summary</h2>
      <div data-checkout-items data-loading-region aria-busy="true">${lineSkeletons(2)}</div>
      <div class="coupon-form" data-checkout-coupon></div>
      <div data-checkout-totals data-loading-region aria-busy="true">${summarySkeleton}</div>
    </aside>
  </form>
</div>
`;

/* ============================================================================
   Payment result pages
   ========================================================================== */

function paymentBody(kind) {
  const config = {
    success: { icon: 'check-circle', tone: 'success', title: 'Payment confirmed', text: 'Thank you. Your payment has been verified and your order is confirmed.' },
    failed: { icon: 'alert-circle', tone: 'danger', title: 'Payment not completed', text: 'We could not confirm your payment. No successful charge has been recorded for this order.' },
    pending: { icon: 'clock', tone: 'pending', title: 'Payment pending', text: 'Your payment is still being processed. We will confirm your order as soon as verification completes.' },
  }[kind];

  return `
<div class="container result-page">
  <div class="result-card">
    <div data-payment-region data-loading-region aria-busy="true">
      <h1 class="result-card__title">${escapeHtml(config.title)}</h1>
      <p class="result-card__text">${escapeHtml(config.text)}</p>
      <div class="stack" aria-hidden="true" style="justify-items:center">
        ${sk('sk--avatar')}
        ${sk('sk--title sk--w-60')}
        ${sk('sk--text sk--w-90')}
        ${sk('sk--text sk--w-70')}
        ${sk('sk--btn sk--w-50')}
      </div>
      <p class="sr-only" role="status">Verifying your payment with the store. Please wait.</p>
    </div>
    <noscript>
      <div class="alert alert--warning">
        <span class="alert__icon"><i data-icon="alert-triangle"></i></span>
        <div class="alert__body">
          <span class="alert__title">JavaScript is required to verify payment</span>
          <span>Your payment reference is in the page address. Please contact customer care with that reference so we can confirm your order status. A browser redirect alone is never treated as proof of payment.</span>
        </div>
      </div>
    </noscript>
    <div hidden data-payment-template data-icon="${config.icon}" data-tone="${config.tone}" data-title="${escapeHtml(config.title)}" data-text="${escapeHtml(config.text)}"></div>
  </div>
</div>
`;
}

/* ============================================================================
   Auth pages
   ========================================================================== */

const loginBody = `
<div class="container auth-page">
  <div class="auth-card">
    <div class="auth-card__head">
      <h1 class="auth-card__title">Welcome back</h1>
      <p class="auth-card__sub">Sign in to view orders, track deliveries and check out faster.</p>
    </div>
    <form class="panel stack" data-login-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="field">
        <label class="field__label" for="login-email">Email address</label>
        <input class="input" id="login-email" name="email" type="email" required autocomplete="email" inputmode="email">
        <p class="field__error" data-error-for="email" id="login-email-error"></p>
      </div>
      <div class="field">
        <label class="field__label" for="login-password">Password</label>
        <div class="password-wrap">
          <input class="input" id="login-password" name="password" type="password" required autocomplete="current-password">
          <button type="button" class="password-toggle" data-password-toggle aria-label="Show password" aria-pressed="false"><i data-icon="eye" data-size="sm"></i></button>
        </div>
        <p class="field__error" data-error-for="password" id="login-password-error"></p>
      </div>
      <div class="cluster cluster--between">
        <label class="checkbox"><input type="checkbox" name="remember" value="true"><span>Keep me signed in</span></label>
        <a class="t-sm" href="/forgot-password.html">Forgot password?</a>
      </div>
      <button class="btn btn--primary btn--block" type="submit" data-pending-label="Signing in">Sign in</button>
    </form>
    <p class="auth-card__foot">New to Starmond? <a href="/register.html">Create an account</a></p>
    <div class="auth-divider">or</div>
    <a class="btn btn--secondary btn--block" href="/track-order.html"><i data-icon="truck" data-size="sm"></i> Track a guest order</a>
  </div>
</div>
`;

const registerBody = `
<div class="container auth-page">
  <div class="auth-card">
    <div class="auth-card__head">
      <h1 class="auth-card__title">Create your account</h1>
      <p class="auth-card__sub">Save addresses, track orders and keep a wishlist.</p>
    </div>
    <form class="panel stack" data-register-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="form-grid">
        <div class="field">
          <label class="field__label" for="reg-first">First name</label>
          <input class="input" id="reg-first" name="first_name" type="text" required autocomplete="given-name">
          <p class="field__error" data-error-for="first_name"></p>
        </div>
        <div class="field">
          <label class="field__label" for="reg-last">Last name</label>
          <input class="input" id="reg-last" name="last_name" type="text" required autocomplete="family-name">
          <p class="field__error" data-error-for="last_name"></p>
        </div>
      </div>
      <div class="field">
        <label class="field__label" for="reg-email">Email address</label>
        <input class="input" id="reg-email" name="email" type="email" required autocomplete="email" inputmode="email">
        <p class="field__error" data-error-for="email"></p>
      </div>
      <div class="field">
        <label class="field__label" for="reg-phone">Phone number</label>
        <input class="input" id="reg-phone" name="phone" type="tel" required autocomplete="tel" inputmode="tel" placeholder="08012345678">
        <p class="field__error" data-error-for="phone"></p>
      </div>
      <div class="field">
        <label class="field__label" for="reg-password">Password</label>
        <div class="password-wrap">
          <input class="input" id="reg-password" name="password" type="password" required autocomplete="new-password" minlength="8" aria-describedby="reg-password-hint">
          <button type="button" class="password-toggle" data-password-toggle aria-label="Show password" aria-pressed="false"><i data-icon="eye" data-size="sm"></i></button>
        </div>
        <div class="password-strength" data-password-strength hidden>
          <div class="password-strength__track"><div class="password-strength__fill" data-strength-fill></div></div>
          <span class="t-xs t-muted" data-strength-label></span>
        </div>
        <p class="field__hint" id="reg-password-hint">At least 8 characters. Avoid common or reused passwords.</p>
        <p class="field__error" data-error-for="password"></p>
      </div>
      <div class="field">
        <label class="field__label" for="reg-password2">Confirm password</label>
        <input class="input" id="reg-password2" name="password_confirm" type="password" required autocomplete="new-password">
        <p class="field__error" data-error-for="password_confirm"></p>
      </div>
      <label class="checkbox">
        <input type="checkbox" name="accept_terms" required>
        <span>I accept the <a href="/policies/terms.html" target="_blank" rel="noopener">terms and conditions</a> and <a href="/policies/privacy.html" target="_blank" rel="noopener">privacy policy</a>.</span>
      </label>
      <p class="field__error" data-error-for="accept_terms"></p>
      <label class="checkbox">
        <input type="checkbox" name="newsletter_opt_in" value="true">
        <span>Send me product updates and offers (optional).</span>
      </label>
      <button class="btn btn--primary btn--block" type="submit" data-pending-label="Creating account">Create account</button>
    </form>
    <p class="auth-card__foot">Already have an account? <a href="/login.html">Sign in</a></p>
  </div>
</div>
`;

function simpleAuthBody({ id, title, sub, fields, submit, foot, formAttr }) {
  return `
<div class="container auth-page">
  <div class="auth-card">
    <div class="auth-card__head">
      <h1 class="auth-card__title">${title}</h1>
      <p class="auth-card__sub">${sub}</p>
    </div>
    <form class="panel stack" ${formAttr} novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="alert alert--success" data-form-success hidden role="status"></div>
      ${fields}
      <button class="btn btn--primary btn--block" type="submit" data-pending-label="${submit.pending}">${submit.label}</button>
    </form>
    <p class="auth-card__foot">${foot}</p>
  </div>
</div>`;
}

/* ============================================================================
   Account pages
   ========================================================================== */

const accountNav = (active) => `
<nav class="account-nav" aria-label="Account sections">
  ${[
    ['overview', '/account.html', 'user', 'Overview'],
    ['orders', '/orders.html', 'package', 'Orders'],
    ['addresses', '/account.html#addresses', 'map-pin', 'Addresses'],
    ['wishlist', '/wishlist.html', 'heart', 'Wishlist'],
    ['reviews', '/account.html#reviews', 'star', 'My reviews'],
    ['payments', '/account.html#payments', 'credit-card', 'Payments'],
    ['settings', '/account.html#settings', 'settings', 'Settings'],
  ].map(([id, href, iconName, label]) => `<a class="account-nav__link" href="${href}"${id === active ? ' aria-current="page"' : ''}><i data-icon="${iconName}" data-size="sm"></i>${label}</a>`).join('')}
  <button type="button" class="account-nav__link" data-logout-page><i data-icon="log-out" data-size="sm"></i>Sign out</button>
</nav>`;

const accountBody = `
<div class="container">
  <div class="page-head">
    <h1 class="page-head__title">My account</h1>
    <p class="page-head__sub" data-account-greeting>Manage your profile, addresses, orders and preferences.</p>
  </div>
  <div class="account-layout">
    ${accountNav('overview')}
    <div class="account-main">
      <section class="account-section" id="overview" aria-labelledby="overview-title">
        <h2 class="t-lg t-semibold" id="overview-title">Overview</h2>
        <div class="admin-stats admin-stats--3" data-account-stats data-loading-region aria-busy="true">
          ${Array.from({ length: 3 }, () => `<div class="sk-stat" aria-hidden="true"><div class="sk-stat__head">${sk('sk--text-sm sk--w-50')}${sk('sk--icon')}</div>${sk('sk--title sk--w-60')}</div>`).join('')}
        </div>
      </section>

      <section class="account-section" id="profile" aria-labelledby="profile-title">
        <div class="card">
          <div class="card__head"><h2 class="card__title" id="profile-title">Profile</h2></div>
          <div class="card__body">
            <form class="stack" data-profile-form novalidate>
              <div class="alert alert--danger" data-form-error hidden role="alert"></div>
              <div class="form-grid">
                <div class="field"><label class="field__label" for="acc-first">First name</label><input class="input" id="acc-first" name="first_name" autocomplete="given-name"><p class="field__error" data-error-for="first_name"></p></div>
                <div class="field"><label class="field__label" for="acc-last">Last name</label><input class="input" id="acc-last" name="last_name" autocomplete="family-name"><p class="field__error" data-error-for="last_name"></p></div>
                <div class="field"><label class="field__label" for="acc-email">Email address</label><input class="input" id="acc-email" name="email" type="email" autocomplete="email"><p class="field__error" data-error-for="email"></p></div>
                <div class="field"><label class="field__label" for="acc-phone">Phone number</label><input class="input" id="acc-phone" name="phone" type="tel" autocomplete="tel"><p class="field__error" data-error-for="phone"></p></div>
              </div>
              <div><button class="btn btn--primary" type="submit" data-pending-label="Saving">Save changes</button></div>
            </form>
          </div>
        </div>
      </section>

      <section class="account-section" id="addresses" aria-labelledby="addresses-title">
        <div class="cluster cluster--between">
          <h2 class="t-lg t-semibold" id="addresses-title">Saved addresses</h2>
          <button type="button" class="btn btn--secondary btn--sm" data-address-add><i data-icon="plus" data-size="sm"></i> Add address</button>
        </div>
        <div data-addresses data-loading-region aria-busy="true">
          <div class="address-grid" aria-hidden="true">${Array.from({ length: 2 }, () => `<div class="address-card">${sk('sk--text sk--w-40')}${sk('sk--text sk--w-90')}${sk('sk--text sk--w-70')}${sk('sk--text sk--w-50')}</div>`).join('')}</div>
        </div>
      </section>

      <section class="account-section" id="payments" aria-labelledby="payments-title">
        <h2 class="t-lg t-semibold" id="payments-title">Payment history</h2>
        <div class="card card__body--flush"><div data-account-payments data-loading-region aria-busy="true"><div class="sk-table" aria-hidden="true">${Array.from({ length: 4 }, () => `<div class="sk-table__row" style="grid-template-columns:2fr 1fr 1fr 1fr">${sk('')}${sk('')}${sk('')}${sk('')}</div>`).join('')}</div></div></div>
      </section>

      <section class="account-section" id="reviews" aria-labelledby="my-reviews-title">
        <h2 class="t-lg t-semibold" id="my-reviews-title">My reviews</h2>
        <div data-account-reviews data-loading-region aria-busy="true">
          <div class="sk-list" aria-hidden="true">${Array.from({ length: 2 }, () => `<div class="sk-list__item">${sk('sk--thumb')}<div class="sk-list__body">${sk('sk--text sk--w-60')}${sk('sk--text-sm sk--w-30')}</div></div>`).join('')}</div>
        </div>
      </section>

      <section class="account-section" id="settings" aria-labelledby="settings-title">
        <div class="card">
          <div class="card__head"><h2 class="card__title" id="settings-title">Notifications &amp; security</h2></div>
          <div class="card__body stack stack--lg">
            <form class="stack" data-preferences-form novalidate>
              <h3 class="t-sm t-semibold">Email notifications</h3>
              <label class="switch"><input type="checkbox" name="order_updates"><span class="switch__track"></span><span>Order and delivery updates</span></label>
              <label class="switch"><input type="checkbox" name="payment_receipts"><span class="switch__track"></span><span>Payment receipts</span></label>
              <label class="switch"><input type="checkbox" name="marketing_emails"><span class="switch__track"></span><span>Product updates and offers</span></label>
              <div><button class="btn btn--secondary" type="submit" data-pending-label="Saving">Save preferences</button></div>
            </form>
            <hr class="divider">
            <form class="stack" data-password-form novalidate>
              <h3 class="t-sm t-semibold">Change password</h3>
              <div class="alert alert--danger" data-form-error hidden role="alert"></div>
              <div class="form-grid">
                <div class="field form-grid__full"><label class="field__label" for="pw-current">Current password</label><input class="input" id="pw-current" name="current_password" type="password" autocomplete="current-password" required><p class="field__error" data-error-for="current_password"></p></div>
                <div class="field"><label class="field__label" for="pw-new">New password</label><input class="input" id="pw-new" name="new_password" type="password" autocomplete="new-password" minlength="8" required><p class="field__error" data-error-for="new_password"></p></div>
                <div class="field"><label class="field__label" for="pw-confirm">Confirm new password</label><input class="input" id="pw-confirm" name="new_password_confirm" type="password" autocomplete="new-password" required><p class="field__error" data-error-for="new_password_confirm"></p></div>
              </div>
              <div><button class="btn btn--secondary" type="submit" data-pending-label="Updating">Update password</button></div>
            </form>
          </div>
        </div>
      </section>
    </div>
  </div>
</div>
`;

const ordersBody = `
<div class="container">
  <div class="page-head">
    <h1 class="page-head__title">My orders</h1>
    <p class="page-head__sub">Track current orders and review past purchases.</p>
  </div>
  <div class="account-layout">
    ${accountNav('orders')}
    <div class="account-main">
      <div class="cluster" data-order-filters>
        <label class="sr-only" for="order-status-filter">Filter by status</label>
        <select class="select" id="order-status-filter" data-order-status style="width:auto;min-width:180px">
          <option value="">All orders</option>
          <option value="pending_payment">Pending payment</option>
          <option value="paid">Paid</option>
          <option value="processing">Processing</option>
          <option value="shipped">Shipped</option>
          <option value="delivered">Delivered</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>
      <div class="stack stack--lg" data-orders-list data-loading-region aria-busy="true">
        ${Array.from({ length: 2 }, () => `<div class="order-card" aria-hidden="true"><div class="order-card__head">${sk('sk--text sk--w-25')}${sk('sk--pill sk--w-20')}</div><div class="order-card__body">${sk('sk--text sk--w-70')}${sk('sk--text sk--w-50')}</div></div>`).join('')}
      </div>
      <nav class="pagination" data-orders-pagination aria-label="Order pagination"></nav>
    </div>
  </div>
</div>
`;

const orderDetailBody = `
<div class="container">
  <div class="page-head">
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <ol class="breadcrumbs__list">
        <li class="breadcrumbs__item"><a href="/">Home</a></li>
        <li class="breadcrumbs__item"><a href="/orders.html">Orders</a></li>
        <li class="breadcrumbs__item"><span aria-current="page">Order detail</span></li>
      </ol>
    </nav>
    <h1 class="page-head__title" data-order-title>Order detail</h1>
  </div>
  <div data-order-detail data-loading-region aria-busy="true">
    <div class="stack stack--lg" aria-hidden="true">
      <div class="panel">${sk('sk--title sk--w-40')}${sk('sk--text sk--w-70')}</div>
      <div class="panel">${sk('sk--text sk--w-30')}${sk('sk--text sk--w-100')}${sk('sk--text sk--w-90')}</div>
    </div>
  </div>
</div>
`;

const wishlistBody = `
<div class="container">
  <div class="page-head">
    <h1 class="page-head__title">Wishlist</h1>
    <p class="page-head__sub">Products you have saved. Move them to your cart whenever you are ready.</p>
  </div>
  <div class="account-layout">
    ${accountNav('wishlist')}
    <div class="account-main">
      <div data-wishlist data-loading-region aria-busy="true">${productSkeletons(4)}</div>
    </div>
  </div>
</div>
`;

const trackOrderBody = `
<div class="container auth-page">
  <div class="auth-card">
    <div class="auth-card__head">
      <h1 class="auth-card__title">Track an order</h1>
      <p class="auth-card__sub">Enter the order reference and email address used at checkout. For your security, guest order links expire.</p>
    </div>
    <form class="panel stack" data-track-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="field">
        <label class="field__label" for="track-ref">Order reference</label>
        <input class="input" id="track-ref" name="reference" type="text" required autocomplete="off" placeholder="STR-XXXXXXXX">
        <p class="field__error" data-error-for="reference"></p>
      </div>
      <div class="field">
        <label class="field__label" for="track-email">Email address</label>
        <input class="input" id="track-email" name="email" type="email" required autocomplete="email">
        <p class="field__error" data-error-for="email"></p>
      </div>
      <button class="btn btn--primary btn--block" type="submit" data-pending-label="Sending secure link">Send secure access link</button>
      <p class="summary-note">We email a signed, expiring link to the address on the order. Order details are never exposed through guessable IDs.</p>
    </form>
    <div data-track-result></div>
    <p class="auth-card__foot">Have an account? <a href="/orders.html">View your orders</a></p>
  </div>
</div>
`;

/* ============================================================================
   Informational pages
   ========================================================================== */

const aboutBody = `
<section class="info-hero">
  <div class="container">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list"><li class="breadcrumbs__item"><a href="/">Home</a></li><li class="breadcrumbs__item"><span aria-current="page">About us</span></li></ol></nav>
    <h1 class="page-head__title" style="margin-top:var(--space-4)">About ${BUSINESS_NAME}</h1>
    <p class="page-head__sub">A multi-category retail business serving customers across Nigeria.</p>
  </div>
</section>
<section class="section">
  <div class="container">
    <div class="prose" data-cms-page="about">
      <div class="stack" aria-hidden="true">${sk('sk--text sk--w-100')}${sk('sk--text sk--w-90')}${sk('sk--text sk--w-95')}${sk('sk--text sk--w-70')}</div>
    </div>
  </div>
</section>
<section class="section section--alt">
  <div class="container">
    <div class="section-head"><div class="section-head__text"><h2 class="section-head__title">What we supply</h2><p class="section-head__sub">Our departments are managed in the store and update automatically.</p></div></div>
    <div data-about-categories data-loading-region aria-busy="true">${categorySkeletons(4)}</div>
  </div>
</section>
`;

const contactBody = `
<section class="info-hero">
  <div class="container">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list"><li class="breadcrumbs__item"><a href="/">Home</a></li><li class="breadcrumbs__item"><span aria-current="page">Contact us</span></li></ol></nav>
    <h1 class="page-head__title" style="margin-top:var(--space-4)">Contact us</h1>
    <p class="page-head__sub">Questions about a product, an order or a delivery? Send us a message and our team will respond.</p>
  </div>
</section>
<section class="section">
  <div class="container contact-layout">
    <div class="panel">
      <h2 class="t-lg t-semibold" style="margin-bottom:var(--space-5)">Send a message</h2>
      <form class="stack" data-contact-form novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="alert alert--success" data-form-success hidden role="status"></div>
        <div class="form-grid">
          <div class="field"><label class="field__label" for="ct-name">Full name <span class="field__req">*</span></label><input class="input" id="ct-name" name="name" required autocomplete="name"><p class="field__error" data-error-for="name"></p></div>
          <div class="field"><label class="field__label" for="ct-email">Email address <span class="field__req">*</span></label><input class="input" id="ct-email" name="email" type="email" required autocomplete="email"><p class="field__error" data-error-for="email"></p></div>
          <div class="field"><label class="field__label" for="ct-phone">Phone number</label><input class="input" id="ct-phone" name="phone" type="tel" autocomplete="tel"><p class="field__error" data-error-for="phone"></p></div>
          <div class="field"><label class="field__label" for="ct-subject">Subject <span class="field__req">*</span></label>
            <select class="select" id="ct-subject" name="subject" required>
              <option value="">Choose a subject</option>
              <option value="product">Product enquiry</option>
              <option value="order">Existing order</option>
              <option value="delivery">Delivery question</option>
              <option value="returns">Return or refund</option>
              <option value="bulk">Bulk or corporate order</option>
              <option value="other">Something else</option>
            </select><p class="field__error" data-error-for="subject"></p></div>
          <div class="field form-grid__full"><label class="field__label" for="ct-order">Order reference <span class="t-muted t-xs">(optional)</span></label><input class="input" id="ct-order" name="order_reference" placeholder="STR-XXXXXXXX"></div>
          <div class="field form-grid__full"><label class="field__label" for="ct-message">Message <span class="field__req">*</span></label><textarea class="textarea" id="ct-message" name="message" rows="5" required maxlength="4000"></textarea><p class="field__error" data-error-for="message"></p></div>
        </div>
        <label class="checkbox"><input type="checkbox" name="consent" required><span>I consent to ${BUSINESS_NAME} contacting me about this enquiry, as described in the <a href="/policies/privacy.html">privacy policy</a>.</span></label>
        <p class="field__error" data-error-for="consent"></p>
        <div><button class="btn btn--primary" type="submit" data-pending-label="Sending">Send message</button></div>
      </form>
    </div>
    <aside class="stack stack--lg">
      <div class="panel contact-details">
        <h2 class="t-md t-semibold">Reach us directly</h2>
        <div class="contact-detail" data-contact-row hidden><span class="contact-detail__icon"><i data-icon="mail"></i></span><span><span class="contact-detail__label">Email</span><a class="contact-detail__value" data-business-email href="#"></a></span></div>
        <div class="contact-detail" data-contact-row hidden><span class="contact-detail__icon"><i data-icon="phone"></i></span><span><span class="contact-detail__label">Phone</span><a class="contact-detail__value" data-business-phone href="#"></a></span></div>
        <div class="contact-detail" data-contact-row hidden><span class="contact-detail__icon"><i data-icon="map-pin"></i></span><span><span class="contact-detail__label">Address</span><span class="contact-detail__value" data-business-address></span></div>
        <p class="t-sm t-muted" data-contact-fallback>Contact details are published here once configured in the store settings.</p>
      </div>
      <div class="panel stack">
        <h2 class="t-md t-semibold">Quick answers</h2>
        <p class="t-sm t-muted">Many questions are already answered in our FAQs and policies.</p>
        <a class="btn btn--secondary btn--sm" href="/faq.html">Read FAQs</a>
        <a class="btn btn--ghost btn--sm" href="/policies/shipping.html">Shipping policy</a>
        <a class="btn btn--ghost btn--sm" href="/policies/returns.html">Returns and refunds</a>
      </div>
    </aside>
  </div>
</section>
`;

const faqBody = `
<section class="info-hero">
  <div class="container">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list"><li class="breadcrumbs__item"><a href="/">Home</a></li><li class="breadcrumbs__item"><span aria-current="page">FAQs</span></li></ol></nav>
    <h1 class="page-head__title" style="margin-top:var(--space-4)">Frequently asked questions</h1>
    <p class="page-head__sub">Answers about ordering, payment, delivery and returns.</p>
  </div>
</section>
<section class="section">
  <div class="container container--narrow">
    <div data-faq-list data-loading-region aria-busy="true">
      <div class="stack" aria-hidden="true">${Array.from({ length: 5 }, () => sk('sk--input')).join('')}</div>
    </div>
  </div>
</section>
`;

function policyBody(key, heading, intro) {
  return `
<section class="info-hero">
  <div class="container">
    <nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list"><li class="breadcrumbs__item"><a href="/">Home</a></li><li class="breadcrumbs__item"><span aria-current="page">${heading}</span></li></ol></nav>
    <h1 class="page-head__title" style="margin-top:var(--space-4)">${heading}</h1>
    <p class="page-head__sub">${intro}</p>
  </div>
</section>
<section class="section">
  <div class="container">
    <div class="prose" data-cms-page="${key}">
      <div class="stack" aria-hidden="true">${sk('sk--text sk--w-100')}${sk('sk--text sk--w-95')}${sk('sk--text sk--w-90')}${sk('sk--text sk--w-80')}${sk('sk--text sk--w-60')}</div>
    </div>
  </div>
</section>
`;
}

/* ============================================================================
   Error / offline pages
   ========================================================================== */

function errorBody(code, title, text, actions) {
  return `<div class="container error-page">
  <div>
    <p class="error-page__code" aria-hidden="true">${code}</p>
    <h1 class="error-page__title">${title}</h1>
    <p class="error-page__text">${text}</p>
    <div class="error-page__actions">${actions}</div>
  </div>
</div>`;
}

/* ============================================================================
   Page registry
   ========================================================================== */

export const storefrontPages = [
  {
    file: 'index.html', path: '/', title: `${BUSINESS_NAME} — Electricals, Fashion, Electronics & Home Essentials in Nigeria`,
    description: 'Shop electrical, fashion, electronics and home products at Starmond Technology Limited. Nationwide delivery and secure checkout.',
    module: '/assets/js/pages/home.js', jsonLd: base, body: homeBody,
  },
  {
    file: 'shop.html', path: '/shop.html', title: `Shop all products — ${BUSINESS_NAME}`,
    description: 'Browse the full Starmond Technology Limited catalogue. Filter by category, price, brand, availability and product attributes.',
    module: '/assets/js/pages/listing.js', jsonLd: base, body: listingBody({ isCategory: false }),
  },
  {
    file: 'category.html', path: '/category.html', title: `Shop by category — ${BUSINESS_NAME}`,
    description: 'Browse products by category at Starmond Technology Limited.',
    module: '/assets/js/pages/listing.js', jsonLd: base, robots: 'noindex, follow', body: listingBody({ isCategory: true }),
  },
  {
    file: 'product.html', path: '/product.html', title: `Product — ${BUSINESS_NAME}`,
    description: 'Product details, specifications, availability and delivery information.',
    module: '/assets/js/pages/product.js', jsonLd: base, robots: 'noindex, follow', body: productBody,
  },
  {
    file: 'search.html', path: '/search.html', title: `Search products — ${BUSINESS_NAME}`,
    description: 'Search the Starmond catalogue by product name, brand, SKU, category or attribute.',
    module: '/assets/js/pages/search-page.js', jsonLd: base, robots: 'noindex, follow',
    body: `<div class="container"><div class="page-head">
      <nav class="breadcrumbs" aria-label="Breadcrumb"><ol class="breadcrumbs__list"><li class="breadcrumbs__item"><a href="/">Home</a></li><li class="breadcrumbs__item"><span aria-current="page">Search</span></li></ol></nav>
      <h1 class="page-head__title" data-search-heading>Search the store</h1>
      <form class="search-hero" data-search-page-form role="search">
        <div class="search-hero__form">
          <label class="sr-only" for="search-page-input">Search products</label>
          <input class="input" id="search-page-input" data-search-page-input type="search" name="q" placeholder="Search products, brands, SKUs or categories" autocomplete="off">
          <button class="btn btn--primary" type="submit"><i data-icon="search" data-size="sm"></i> Search</button>
        </div>
      </form>
    </div>
    <div class="listing-toolbar">
      <p class="listing-toolbar__count" data-search-count aria-live="polite"></p>
      <div class="listing-toolbar__controls">
        <label class="sr-only" for="search-sort">Sort results</label>
        <select class="select" id="search-sort" data-search-sort>
          <option value="relevance">Most relevant</option>
          <option value="newest">Newest</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
          <option value="rating">Highest rated</option>
        </select>
      </div>
    </div>
    <div class="section--tight" data-search-results data-loading-region></div>
    <nav class="pagination" data-search-pagination aria-label="Search results pagination"></nav>
    </div>`,
  },
  {
    file: 'cart.html', path: '/cart.html', title: `Your cart — ${BUSINESS_NAME}`,
    description: 'Review the items in your shopping cart before checkout.',
    module: '/assets/js/pages/cart-page.js', jsonLd: [], robots: 'noindex, nofollow', body: cartBody,
  },
  {
    file: 'checkout.html', path: '/checkout.html', title: `Secure checkout — ${BUSINESS_NAME}`,
    description: 'Complete your order with secure Paystack payment.',
    module: '/assets/js/pages/checkout-page.js', jsonLd: [], robots: 'noindex, nofollow', body: checkoutBody,
  },
  {
    file: 'payment-success.html', path: '/payment-success.html', title: `Payment confirmed — ${BUSINESS_NAME}`,
    description: 'Your payment has been verified and your order confirmed.',
    module: '/assets/js/pages/payment-result.js', jsonLd: [], robots: 'noindex, nofollow', body: paymentBody('success'),
  },
  {
    file: 'payment-failed.html', path: '/payment-failed.html', title: `Payment not completed — ${BUSINESS_NAME}`,
    description: 'Your payment could not be completed.',
    module: '/assets/js/pages/payment-result.js', jsonLd: [], robots: 'noindex, nofollow', body: paymentBody('failed'),
  },
  {
    file: 'payment-pending.html', path: '/payment-pending.html', title: `Payment pending — ${BUSINESS_NAME}`,
    description: 'Your payment is being verified.',
    module: '/assets/js/pages/payment-result.js', jsonLd: [], robots: 'noindex, nofollow', body: paymentBody('pending'),
  },
  {
    file: 'login.html', path: '/login.html', title: `Sign in — ${BUSINESS_NAME}`,
    description: 'Sign in to your Starmond account.', module: '/assets/js/pages/auth-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: loginBody,
  },
  {
    file: 'register.html', path: '/register.html', title: `Create an account — ${BUSINESS_NAME}`,
    description: 'Create a Starmond account to track orders and check out faster.', module: '/assets/js/pages/auth-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: registerBody,
  },
  {
    file: 'forgot-password.html', path: '/forgot-password.html', title: `Reset your password — ${BUSINESS_NAME}`,
    description: 'Request a password reset link.', module: '/assets/js/pages/auth-page.js',
    jsonLd: [], robots: 'noindex, nofollow',
    body: simpleAuthBody({
      title: 'Reset your password', sub: 'Enter your email address and we will send you a reset link.',
      formAttr: 'data-forgot-form',
      fields: `<div class="field"><label class="field__label" for="fp-email">Email address</label><input class="input" id="fp-email" name="email" type="email" required autocomplete="email"><p class="field__error" data-error-for="email"></p></div>`,
      submit: { label: 'Send reset link', pending: 'Sending' },
      foot: '<a href="/login.html">Back to sign in</a>',
    }),
  },
  {
    file: 'reset-password.html', path: '/reset-password.html', title: `Choose a new password — ${BUSINESS_NAME}`,
    description: 'Set a new password for your account.', module: '/assets/js/pages/auth-page.js',
    jsonLd: [], robots: 'noindex, nofollow',
    body: simpleAuthBody({
      title: 'Choose a new password', sub: 'Your reset link is valid for a limited time.',
      formAttr: 'data-reset-form',
      fields: `<div class="field"><label class="field__label" for="rp-password">New password</label><div class="password-wrap"><input class="input" id="rp-password" name="new_password" type="password" required autocomplete="new-password" minlength="8"><button type="button" class="password-toggle" data-password-toggle aria-label="Show password" aria-pressed="false"><i data-icon="eye" data-size="sm"></i></button></div><p class="field__error" data-error-for="new_password"></p></div>
        <div class="field"><label class="field__label" for="rp-confirm">Confirm new password</label><input class="input" id="rp-confirm" name="new_password_confirm" type="password" required autocomplete="new-password"><p class="field__error" data-error-for="new_password_confirm"></p></div>`,
      submit: { label: 'Update password', pending: 'Updating' },
      foot: '<a href="/login.html">Back to sign in</a>',
    }),
  },
  {
    file: 'verify-email.html', path: '/verify-email.html', title: `Verify your email — ${BUSINESS_NAME}`,
    description: 'Confirm your email address.', module: '/assets/js/pages/auth-page.js',
    jsonLd: [], robots: 'noindex, nofollow',
    body: `<div class="container auth-page"><div class="auth-card">
      <div class="auth-card__head"><h1 class="auth-card__title">Email verification</h1><p class="auth-card__sub">Confirming your email address keeps your account secure.</p></div>
      <div class="panel" data-verify-region data-loading-region aria-busy="true"><div class="stack" aria-hidden="true">${sk('sk--text sk--w-70')}${sk('sk--text sk--w-50')}${sk('sk--btn sk--w-40')}</div></div>
      <form class="panel stack" data-resend-form hidden novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="alert alert--success" data-form-success hidden role="status"></div>
        <div class="field"><label class="field__label" for="ve-email">Email address</label><input class="input" id="ve-email" name="email" type="email" required autocomplete="email"></div>
        <button class="btn btn--secondary btn--block" type="submit" data-pending-label="Sending">Resend verification email</button>
      </form>
      <p class="auth-card__foot"><a href="/login.html">Back to sign in</a></p>
    </div></div>`,
  },
  {
    file: 'account.html', path: '/account.html', title: `My account — ${BUSINESS_NAME}`,
    description: 'Manage your profile, addresses and preferences.', module: '/assets/js/pages/account-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: accountBody,
  },
  {
    file: 'orders.html', path: '/orders.html', title: `My orders — ${BUSINESS_NAME}`,
    description: 'View and track your orders.', module: '/assets/js/pages/orders-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: ordersBody,
  },
  {
    file: 'order-detail.html', path: '/order-detail.html', title: `Order detail — ${BUSINESS_NAME}`,
    description: 'Order details and delivery tracking.', module: '/assets/js/pages/order-detail-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: orderDetailBody,
  },
  {
    file: 'wishlist.html', path: '/wishlist.html', title: `Wishlist — ${BUSINESS_NAME}`,
    description: 'Products you have saved.', module: '/assets/js/pages/wishlist-page.js',
    jsonLd: [], robots: 'noindex, nofollow', body: wishlistBody,
  },
  {
    file: 'track-order.html', path: '/track-order.html', title: `Track an order — ${BUSINESS_NAME}`,
    description: 'Securely access a guest order using your order reference.', module: '/assets/js/pages/track-order-page.js',
    jsonLd: [], robots: 'noindex, follow', body: trackOrderBody,
  },
  {
    file: 'about.html', path: '/about.html', title: `About us — ${BUSINESS_NAME}`,
    description: 'Learn about Starmond Technology Limited, a Nigerian multi-category retail business supplying electricals, fashion, electronics and household products.',
    module: '/assets/js/pages/content-page.js', jsonLd: base, body: aboutBody,
  },
  {
    file: 'contact.html', path: '/contact.html', title: `Contact us — ${BUSINESS_NAME}`,
    description: 'Contact Starmond Technology Limited about products, orders, delivery, returns or bulk enquiries.',
    module: '/assets/js/pages/contact-page.js', jsonLd: base, body: contactBody,
  },
  {
    file: 'faq.html', path: '/faq.html', title: `Frequently asked questions — ${BUSINESS_NAME}`,
    description: 'Answers about ordering, payment, delivery and returns at Starmond Technology Limited.',
    module: '/assets/js/pages/content-page.js', jsonLd: base, body: faqBody,
  },
  {
    file: 'policies/privacy.html', path: '/policies/privacy.html', title: `Privacy policy — ${BUSINESS_NAME}`,
    description: 'How Starmond Technology Limited collects, uses and protects your personal data.',
    module: '/assets/js/pages/content-page.js', jsonLd: base,
    body: policyBody('privacy', 'Privacy policy', 'How we collect, use and protect your personal information.'),
  },
  {
    file: 'policies/terms.html', path: '/policies/terms.html', title: `Terms and conditions — ${BUSINESS_NAME}`,
    description: 'The terms that govern purchases from Starmond Technology Limited.',
    module: '/assets/js/pages/content-page.js', jsonLd: base,
    body: policyBody('terms', 'Terms and conditions', 'The terms governing the use of this store and purchases made through it.'),
  },
  {
    file: 'policies/shipping.html', path: '/policies/shipping.html', title: `Shipping policy — ${BUSINESS_NAME}`,
    description: 'Delivery options, coverage, timelines and fees for Starmond Technology Limited orders.',
    module: '/assets/js/pages/content-page.js', jsonLd: base,
    body: policyBody('shipping', 'Shipping policy', 'Delivery coverage, options, timelines and how fees are calculated.'),
  },
  {
    file: 'policies/returns.html', path: '/policies/returns.html', title: `Returns and refund policy — ${BUSINESS_NAME}`,
    description: 'How to return a product and request a refund from Starmond Technology Limited.',
    module: '/assets/js/pages/content-page.js', jsonLd: base,
    body: policyBody('returns', 'Returns and refunds', 'Eligibility, timelines and the process for returns and refunds.'),
  },
  {
    file: '403.html', path: '/403.html', title: `Access denied — ${BUSINESS_NAME}`,
    description: 'You do not have permission to view this page.', robots: 'noindex, follow', jsonLd: [],
    module: '/assets/js/pages/static-page.js',
    body: errorBody('403', 'You do not have access to this page', 'This area requires different permissions. If you believe this is a mistake, contact customer support.',
      '<a class="btn btn--primary" href="/">Return home</a><a class="btn btn--secondary" href="/contact.html">Contact support</a>'),
  },
  {
    file: '404.html', path: '/404.html', title: `Page not found — ${BUSINESS_NAME}`,
    description: 'The page you requested could not be found.', robots: 'noindex, follow', jsonLd: [],
    module: '/assets/js/pages/static-page.js',
    body: errorBody('404', 'We could not find that page', 'The link may be out of date, or the product may no longer be available. Try searching the store instead.',
      '<a class="btn btn--primary" href="/shop.html">Browse the shop</a><a class="btn btn--secondary" href="/">Return home</a>'),
  },
  {
    file: '500.html', path: '/500.html', title: `Something went wrong — ${BUSINESS_NAME}`,
    description: 'The store encountered an unexpected problem.', robots: 'noindex, follow', jsonLd: [],
    module: '/assets/js/pages/static-page.js',
    body: errorBody('500', 'Something went wrong at our end', 'Our team has been notified. Please try again in a few moments. Your payment status is never changed by an error page.',
      '<a class="btn btn--primary" href="/">Return home</a><a class="btn btn--secondary" href="/contact.html">Contact support</a>'),
  },
  {
    file: 'offline.html', path: '/offline.html', title: `You are offline — ${BUSINESS_NAME}`,
    description: 'No internet connection is available.', robots: 'noindex, nofollow', jsonLd: [],
    module: '/assets/js/pages/static-page.js',
    module: '/assets/js/pages/offline-page.js',
    body: errorBody('', 'You are offline', 'This page is available without a connection, but browsing products, checkout and payment need the internet. No order or payment can be confirmed while offline.',
      '<button class="btn btn--primary" data-retry-connection type="button">Try again</button><a class="btn btn--secondary" href="/">Return home</a>'),
  },
];
