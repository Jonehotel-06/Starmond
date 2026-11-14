/**
 * home.js — homepage sections.
 *
 * Every section loads independently. A slow or failing secondary request never
 * blocks the hero, the navigation or another section. Sections the backend has
 * no content for are hidden rather than filled with invented data.
 */

import boot from '../boot.js';
import api, { normalizeList } from '../api.js';
import { getSettings } from '../site.js';
import { getCategories, renderCategoryCards } from '../categories.js';
import { listProducts, renderProductGrid, renderStars, productImage, PRODUCT_URL } from '../products.js';
import { skeletons, resolveRegion, renderRegionError, emptyState, toast, withSubmit, formData, applyFormErrors } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, sanitizeHtml, isEmail, truncate, stripTags } from '../utils.js';
import { syncWishlistButtons } from '../shop-actions.js';

await boot();

/* ------------------------------------------------------------------ hero -- */

async function loadHero() {
  const settings = await getSettings();
  const hero = settings?.homepage?.hero;
  if (!hero) return; // keep the crawlable static fallback

  const title = $('[data-hero-title]');
  const text = $('[data-hero-text]');
  const eyebrow = $('[data-hero-eyebrow]');
  const media = $('[data-hero-media]');

  if (hero.title && title) title.textContent = hero.title;
  if (hero.subtitle && text) text.textContent = hero.subtitle;
  if (hero.eyebrow && eyebrow) eyebrow.innerHTML = `${icon('zap', { size: 'sm' })} ${esc(hero.eyebrow)}`;

  if (hero.image_url && media) {
    media.classList.remove('hero__media--empty');
    media.innerHTML = `<img src="${esc(hero.image_url)}" alt="${esc(hero.image_alt || hero.title || 'Starmond featured range')}"
      width="960" height="720" fetchpriority="high" decoding="async"
      ${hero.image_srcset ? `srcset="${esc(hero.image_srcset)}" sizes="(max-width:1023px) 100vw, 48vw"` : ''}>`;
  }

  const primary = $('[data-hero-primary]');
  const secondary = $('[data-hero-secondary]');
  if (hero.primary_cta?.url && primary) {
    primary.href = hero.primary_cta.url;
    primary.innerHTML = `${esc(hero.primary_cta.label || 'Shop now')} ${icon('arrow-right', { size: 'sm' })}`;
  }
  if (hero.secondary_cta?.url && secondary) {
    secondary.href = hero.secondary_cta.url;
    secondary.textContent = hero.secondary_cta.label || 'Explore categories';
  } else if (hero.secondary_cta && !hero.secondary_cta.url && secondary) {
    secondary.hidden = true;
  }
  hydrateIcons(document.querySelector('.hero'));
}

/* ------------------------------------------------------------ categories -- */

async function loadCategories() {
  const region = $('[data-home-categories]');
  try {
    const tree = await getCategories();
    if (!tree.length) {
      resolveRegion(region, emptyState({
        title: 'No categories published yet',
        text: 'Departments will appear here as soon as they are published in the store.',
        iconName: 'folder',
        actionHtml: '<a class="btn btn--secondary btn--sm" href="/shop.html">Browse all products</a>',
      }));
      return;
    }
    resolveRegion(region, `<div class="category-grid">${renderCategoryCards(tree.slice(0, 8))}</div>`, { label: `${tree.length} categories loaded` });
  } catch (error) {
    renderRegionError(region, error, loadCategories, { title: 'Categories could not be loaded' });
  }
}

/* -------------------------------------------------------------- products -- */

function productSection(selector, loader, { emptyTitle, emptyText, limit = 4 }) {
  const region = $(selector);
  if (!region) return () => {};
  const run = async () => {
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.productGrid(limit);
    try {
      const list = await loader();
      const results = list.results.slice(0, limit);
      if (!results.length) {
        resolveRegion(region, emptyState({ title: emptyTitle, text: emptyText, iconName: 'package', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="product-grid">${renderProductGrid(results)}</div>`);
      syncWishlistButtons();
    } catch (error) {
      renderRegionError(region, error, run, { title: emptyTitle });
    }
  };
  run();
  return run;
}

/* ------------------------------------------------------------------ promo -- */

async function loadPromo() {
  const section = $('[data-home-promo-section]');
  const region = $('[data-home-promo]');
  if (!section || !region) return;
  try {
    const data = await api.publicGet('/promotions/active/', { params: { placement: 'home_banner', limit: 1 } });
    const promo = normalizeList(data).results[0];
    if (!promo) { section.hidden = true; return; }
    section.hidden = false;
    region.innerHTML = `<div class="promo">
      <div class="promo__copy">
        ${promo.eyebrow ? `<span class="promo__eyebrow">${esc(promo.eyebrow)}</span>` : ''}
        <h2 class="promo__title">${esc(promo.title)}</h2>
        ${promo.description ? `<p class="promo__text">${esc(promo.description)}</p>` : ''}
        ${promo.cta_url ? `<div><a class="btn btn--primary" href="${esc(promo.cta_url)}">${esc(promo.cta_label || 'Shop the offer')} ${icon('arrow-right', { size: 'sm' })}</a></div>` : ''}
        ${promo.terms ? `<p class="t-xs" style="color:#9d99ab">${esc(promo.terms)}</p>` : ''}
      </div>
      ${promo.image_url ? `<div class="promo__media"><img src="${esc(promo.image_url)}" alt="${esc(promo.image_alt || promo.title)}" width="640" height="400" loading="lazy" decoding="async"></div>` : ''}
    </div>`;
    hydrateIcons(region);
  } catch {
    section.hidden = true; // A missing campaign is not an error worth showing.
  }
}

/* ------------------------------------------------------------------ trust -- */

async function loadTrust() {
  const settings = await getSettings();
  const items = settings?.homepage?.trust_items;
  const region = $('[data-home-trust]');
  const section = $('[data-home-trust-section]');
  if (!Array.isArray(items) || !items.length) return; // keep the neutral defaults
  if (!region) return;
  region.innerHTML = items.map((item) => `<div class="trust-item">
    <span class="trust-item__icon">${icon(item.icon || 'check-circle')}</span>
    <span><span class="trust-item__title">${esc(item.title)}</span>${item.text ? `<span class="trust-item__text">${esc(item.text)}</span>` : ''}</span>
  </div>`).join('');
  if (section) section.hidden = false;
}

/* ---------------------------------------------------------------- reviews -- */

async function loadReviews() {
  const region = $('[data-home-reviews]');
  const section = $('[data-home-reviews-section]');
  if (!region) return;
  try {
    const data = await api.publicGet('/reviews/', { params: { approved: 1, featured: 1, limit: 3 } });
    const reviews = normalizeList(data).results;
    if (!reviews.length) { section.hidden = true; return; }
    section.hidden = false;
    resolveRegion(region, `<div class="grid grid--3">${reviews.map((review) => {
      const product = review.product;
      return `<article class="panel stack">
        ${typeof review.rating === 'number' ? renderStars(review.rating) : ''}
        ${review.title ? `<h3 class="t-md t-semibold">${esc(review.title)}</h3>` : ''}
        <p class="t-sm t-body">${esc(truncate(stripTags(review.body || review.comment || ''), 220))}</p>
        <div class="cluster cluster--sm">
          <span class="t-sm t-medium">${esc(review.display_name || review.customer_name || 'Verified customer')}</span>
          ${review.verified_purchase ? `<span class="badge badge--success badge--dot">Verified purchase</span>` : ''}
        </div>
        ${product ? `<a class="t-xs" href="${esc(PRODUCT_URL(product))}">${esc(product.name || 'View product')}</a>` : ''}
      </article>`;
    }).join('')}</div>`);
  } catch {
    section.hidden = true;
  }
}

/* ------------------------------------------------------------- newsletter -- */

function initNewsletter() {
  const form = $('[data-newsletter-form]');
  if (!form) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = formData(form);
    const errors = {};
    if (!isEmail(data.email)) errors.email = 'Enter a valid email address.';
    if (!data.consent) errors.consent = 'Please confirm you agree to receive emails.';
    if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

    const button = form.querySelector('button[type="submit"]');
    try {
      await withSubmit(form, button, () => api.post('/newsletter/subscribe/', {
        email: String(data.email).trim(), consent: true, source: 'homepage',
      }));
      form.reset();
      toast('You are subscribed. Check your inbox to confirm.', { type: 'success', title: 'Thank you' });
      const success = document.createElement('p');
      success.className = 't-sm t-success t-semibold';
      success.setAttribute('role', 'status');
      success.textContent = 'Subscription received. Please check your email to confirm.';
      form.appendChild(success);
    } catch { /* withSubmit already rendered the error */ }
  });
}

/* ------------------------------------------------------------------- run -- */

loadHero();
loadCategories();
productSection('[data-home-featured]', () => listProducts({ featured: 1, page_size: 4 }), {
  emptyTitle: 'No featured products yet', emptyText: 'Featured products will appear here once selected by our team.',
});
productSection('[data-home-new]', () => listProducts({ ordering: '-published_at', page_size: 4 }), {
  emptyTitle: 'No new arrivals yet', emptyText: 'Recently published products will appear here.',
});
productSection('[data-home-best]', () => listProducts({ ordering: '-units_sold', page_size: 4 }), {
  emptyTitle: 'Best sellers are not available yet', emptyText: 'This list is ranked by confirmed sales and appears once orders are recorded.',
});
loadPromo();
loadTrust();
loadReviews();
initNewsletter();
