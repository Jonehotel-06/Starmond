/**
 * listing.js — shop, category and subcategory listing pages.
 *
 * Handles: category resolution from SEO paths, category-aware facets, sorting,
 * pagination, URL state, breadcrumbs and category JSON-LD. All result ordering
 * and filtering is performed by the backend.
 */

import boot from '../boot.js';
import api, { normalizeList } from '../api.js';
import {
  getCategories, resolveCategoryPath, categoryUrl, categoryTrail,
  renderCategoryBreadcrumbs, renderSubcategoryTiles, breadcrumbJsonLd,
} from '../categories.js';
import { listProducts, getFacets, renderProductGrid, PRODUCT_URL } from '../products.js';
import { skeletons, resolveRegion, renderRegionError, emptyState, announce } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { esc, enc, $, readQuery, buildQuery, formatMoney, debounce, truncate, stripTags } from '../utils.js';
import { syncWishlistButtons } from '../shop-actions.js';
import { BUSINESS_NAME } from '../site.js';

await boot();

const PAGE_SIZE = 20;
// UI sort key → backend `ordering` (ProductPublicViewSet.ordering_fields).
const SORT_MAP = {
  featured: '-is_featured,-created_at',
  newest: '-created_at',
  price_asc: 'price',
  price_desc: '-price',
  best_selling: '-is_best_seller,-created_at',
  rating: '-avg_rating',
};

const origin = (window.STARMOND_CONFIG?.SITE_URL || location.origin).replace(/\/$/, '');

/* ============================================================================
   Resolve which category this page represents
   ========================================================================== */

function categorySegmentsFromLocation() {
  const params = readQuery();
  if (params.category) return String(params.category).split('/').filter(Boolean);
  const match = location.pathname.match(/^\/shop\/(.+?)\/?$/);
  if (match) return match[1].split('/').filter(Boolean);
  return [];
}

const state = {
  segments: categorySegmentsFromLocation(),
  category: null,
  trail: [],
  page: Number(readQuery().page) || 1,
  sort: readQuery().sort || 'featured',
  filters: { ...readQuery() },
};
delete state.filters.page;
delete state.filters.sort;
delete state.filters.category;

let controller = null;
let facets = null;

/* ============================================================================
   Query building
   ========================================================================== */

function apiParams() {
  const params = {
    page: state.page,
    page_size: PAGE_SIZE,
    ordering: SORT_MAP[state.sort] || undefined,
  };
  if (state.category) params.category = state.category.slug ?? state.category.id;
  // Storefront filter keys → ProductPublicFilter query parameters.
  Object.entries(state.filters).forEach(([key, value]) => {
    if (value === '' || value === null || value === undefined) return;
    if (key === 'q') params.q = value;
    else if (key === 'min_price' || key === 'max_price') { if (Number(value) >= 0) params[key] = Number(value); }
    else if (key === 'availability') params.in_stock = value === 'in_stock';
    else if (key === 'brand') params.brand = value;
    else if (key === 'discounted') params.on_sale = true;
    else if (key === 'featured') params.featured = true;
    else if (key === 'new') params.new_arrivals = true;
    else if (key === 'best') params.best_sellers = true;
  });
  return params;
}

function currentUrl() {
  const basePath = state.category ? categoryUrl(state.category) : '/shop.html';
  const query = buildQuery({ ...state.filters, sort: state.sort === 'featured' ? '' : state.sort, page: state.page > 1 ? state.page : '' });
  return `${basePath}${query}`;
}

function pushUrl() {
  history.replaceState({}, '', currentUrl());
}

/* ============================================================================
   Rendering
   ========================================================================== */

function renderPagination(count) {
  const nav = $('[data-listing-pagination]');
  if (!nav) return;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  if (pages <= 1) { nav.innerHTML = ''; return; }

  const link = (page, label, { current = false, disabled = false, ariaLabel } = {}) => {
    if (disabled) return `<span class="pagination__btn" aria-disabled="true">${label}</span>`;
    const params = { ...state.filters, sort: state.sort === 'featured' ? '' : state.sort, page: page > 1 ? page : '' };
    const href = `${state.category ? categoryUrl(state.category) : '/shop.html'}${buildQuery(params)}`;
    return `<a class="pagination__btn" href="${esc(href)}" data-page="${page}" ${current ? 'aria-current="page"' : ''} ${ariaLabel ? `aria-label="${esc(ariaLabel)}"` : ''}>${label}</a>`;
  };

  const items = [];
  items.push(link(state.page - 1, icon('chevron-left', { size: 'sm' }), { disabled: state.page === 1, ariaLabel: 'Previous page' }));
  const window_ = new Set([1, pages, state.page, state.page - 1, state.page + 1]);
  let last = 0;
  [...window_].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b).forEach((page) => {
    if (last && page - last > 1) items.push('<span class="pagination__gap">…</span>');
    items.push(link(page, String(page), { current: page === state.page, ariaLabel: `Page ${page}` }));
    last = page;
  });
  items.push(link(state.page + 1, icon('chevron-right', { size: 'sm' }), { disabled: state.page === pages, ariaLabel: 'Next page' }));
  nav.innerHTML = items.join('');
  hydrateIcons(nav);

  // rel=prev/next hints for paginated crawling.
  document.querySelectorAll('link[data-pagination-rel]').forEach((n) => n.remove());
  [['prev', state.page - 1], ['next', state.page + 1]].forEach(([rel, page]) => {
    if (page < 1 || page > pages) return;
    const linkEl = document.createElement('link');
    linkEl.rel = rel;
    linkEl.dataset.paginationRel = rel;
    linkEl.href = `${origin}${state.category ? categoryUrl(state.category) : '/shop.html'}${buildQuery({ ...state.filters, page: page > 1 ? page : '' })}`;
    document.head.appendChild(linkEl);
  });
}

function renderActiveFilters() {
  const holder = $('[data-active-filters]');
  if (!holder) return;
  const chips = [];
  const labels = {
    q: 'Search', min_price: 'Min price', max_price: 'Max price', brand: 'Brand',
    availability: 'Availability', discounted: 'On sale', featured: 'Featured', new: 'New arrivals',
  };
  Object.entries(state.filters).forEach(([key, value]) => {
    if (!value) return;
    const label = labels[key] || key.replace(/^attr_/, '').replace(/_/g, ' ');
    const display = key === 'discounted' || key === 'featured' || key === 'new' ? '' : `: ${value}`;
    chips.push(`<span class="chip">${esc(label)}${esc(display)}
      <button type="button" class="chip__remove" data-remove-filter="${esc(key)}" aria-label="Remove ${esc(label)} filter">${icon('x', { size: 'sm' })}</button>
    </span>`);
  });
  holder.innerHTML = chips.length
    ? `${chips.join('')}<button type="button" class="link-btn" data-filters-clear>Clear all</button>`
    : '';
  hydrateIcons(holder);
}

function renderCount(count) {
  const node = $('[data-listing-count]');
  if (!node) return;
  const from = (state.page - 1) * PAGE_SIZE + 1;
  const to = Math.min(state.page * PAGE_SIZE, count);
  node.textContent = count === 0 ? 'No products found' : `Showing ${from}–${to} of ${count} product${count === 1 ? '' : 's'}`;
}

/* ============================================================================
   Facets — category aware
   ========================================================================== */

async function loadFacets() {
  const holder = $('[data-filters-body]');
  if (!holder) return;
  try {
    facets = await getFacets(state.category ? { category: state.category.slug ?? state.category.id } : {});
    renderFacets(holder, facets);
  } catch (error) {
    // Filters are an enhancement; the grid still works without them.
    holder.innerHTML = `<p class="t-sm t-muted">Filters are unavailable right now. You can still browse and sort products.</p>`;
  }
}

function renderFacets(holder, data) {
  const groups = [];

  // Keyword search within the current category.
  groups.push(`<div class="filter-group">
    <p class="filter-group__title">Search this ${state.category ? 'category' : 'store'}</p>
    <label class="sr-only" for="filter-q">Search within results</label>
    <input class="input input--sm" id="filter-q" type="search" data-filter="q" value="${esc(state.filters.q || '')}" placeholder="Keyword">
  </div>`);

  const price = data?.price_range;
  groups.push(`<div class="filter-group">
    <p class="filter-group__title">Price (${esc(data?.currency || 'NGN')})</p>
    <div class="filter-price">
      <div><label class="sr-only" for="filter-min">Minimum price</label>
        <input class="input input--sm" id="filter-min" type="number" min="0" inputmode="numeric" data-filter="min_price" value="${esc(state.filters.min_price || '')}" placeholder="${price?.min != null ? esc(price.min) : 'Min'}"></div>
      <div><label class="sr-only" for="filter-max">Maximum price</label>
        <input class="input input--sm" id="filter-max" type="number" min="0" inputmode="numeric" data-filter="max_price" value="${esc(state.filters.max_price || '')}" placeholder="${price?.max != null ? esc(price.max) : 'Max'}"></div>
    </div>
  </div>`);

  const brands = data?.brands || [];
  if (brands.length) {
    groups.push(`<div class="filter-group">
      <p class="filter-group__title">Brand</p>
      <div class="filter-group__options filter-group__options--scroll">
        ${brands.map((brand) => {
          const value = brand.name || brand;
          const label = brand.name || brand;
          const checked = String(state.filters.brand || '').split(',').includes(String(value));
          return `<label class="checkbox"><input type="checkbox" data-filter-multi="brand" value="${esc(value)}" ${checked ? 'checked' : ''}>
            <span>${esc(label)}${typeof brand.count === 'number' ? ` <span class="t-meta">(${brand.count})</span>` : ''}</span></label>`;
        }).join('')}
      </div>
    </div>`);
  }

  groups.push(`<div class="filter-group">
    <p class="filter-group__title">Availability</p>
    <div class="filter-group__options">
      ${[['in_stock', 'In stock'], ['out_of_stock', 'Out of stock']].map(([value, label]) => `
        <label class="radio"><input type="radio" name="availability" data-filter="availability" value="${value}" ${state.filters.availability === value ? 'checked' : ''}><span>${label}</span></label>`).join('')}
      <label class="radio"><input type="radio" name="availability" data-filter="availability" value="" ${!state.filters.availability ? 'checked' : ''}><span>Any availability</span></label>
    </div>
  </div>`);

  // Category-specific attributes: technical specs for electrical, size/colour
  // for fashion. The backend decides which attributes apply — never hardcoded.
  const attributes = data?.attributes || [];
  attributes.forEach((attribute) => {
    if (!attribute.values?.length) return;
    const key = `attr_${attribute.slug || attribute.key}`;
    const selected = String(state.filters[key] || '').split(',').filter(Boolean);
    const isSwatch = attribute.type === 'color' || attribute.type === 'colour';
    groups.push(`<div class="filter-group">
      <p class="filter-group__title">${esc(attribute.name || attribute.label)}</p>
      <div class="filter-group__options ${attribute.values.length > 8 ? 'filter-group__options--scroll' : ''}">
        ${attribute.values.map((value) => {
          const val = value.value ?? value;
          const label = value.label ?? value.value ?? value;
          return `<label class="checkbox">
            <input type="checkbox" data-filter-multi="${esc(key)}" value="${esc(val)}" ${selected.includes(String(val)) ? 'checked' : ''}>
            <span>${isSwatch && value.hex ? `<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${esc(value.hex)};border:1px solid var(--color-border);margin-right:6px;vertical-align:-1px"></span>` : ''}${esc(label)}${typeof value.count === 'number' ? ` <span class="t-meta">(${value.count})</span>` : ''}</span>
          </label>`;
        }).join('')}
      </div>
    </div>`);
  });

  groups.push(`<div class="filter-group">
    <p class="filter-group__title">Other</p>
    <div class="filter-group__options">
      <label class="checkbox"><input type="checkbox" data-filter-flag="discounted" ${state.filters.discounted ? 'checked' : ''}><span>Discounted products</span></label>
      <label class="checkbox"><input type="checkbox" data-filter-flag="featured" ${state.filters.featured ? 'checked' : ''}><span>Featured products</span></label>
      <label class="checkbox"><input type="checkbox" data-filter-flag="new" ${state.filters.new ? 'checked' : ''}><span>New arrivals</span></label>
    </div>
  </div>`);

  holder.innerHTML = groups.join('');
  bindFilterEvents(holder);
}

function bindFilterEvents(holder) {
  const applyDebounced = debounce(() => { state.page = 1; load(); }, 450);

  holder.querySelectorAll('[data-filter]').forEach((input) => {
    const key = input.dataset.filter;
    const handler = () => {
      const value = input.value.trim();
      if (value) state.filters[key] = value; else delete state.filters[key];
      applyDebounced();
    };
    input.addEventListener(input.type === 'radio' ? 'change' : 'input', handler);
    if (input.type === 'search') input.addEventListener('change', handler);
  });

  holder.querySelectorAll('[data-filter-multi]').forEach((input) => {
    input.addEventListener('change', () => {
      const key = input.dataset.filterMulti;
      const values = [...holder.querySelectorAll(`[data-filter-multi="${CSS.escape(key)}"]:checked`)].map((n) => n.value);
      if (values.length) state.filters[key] = values.join(','); else delete state.filters[key];
      state.page = 1;
      load();
    });
  });

  holder.querySelectorAll('[data-filter-flag]').forEach((input) => {
    input.addEventListener('change', () => {
      const key = input.dataset.filterFlag;
      if (input.checked) state.filters[key] = '1'; else delete state.filters[key];
      state.page = 1;
      load();
    });
  });
}

/* ============================================================================
   Data loading
   ========================================================================== */

async function load() {
  const region = $('[data-listing-results]');
  controller?.abort();
  controller = new AbortController();

  region.setAttribute('aria-busy', 'true');
  region.innerHTML = skeletons.productGrid(8);
  pushUrl();
  renderActiveFilters();

  try {
    const list = await listProducts(apiParams(), { signal: controller.signal });
    renderCount(list.count);
    if (!list.results.length) {
      resolveRegion(region, emptyState({
        title: 'No products match your filters',
        text: 'Try removing a filter, widening the price range, or browsing another category.',
        iconName: 'search',
        actionHtml: '<button type="button" class="btn btn--secondary btn--sm" data-filters-clear>Clear all filters</button><a class="btn btn--ghost btn--sm" href="/shop.html">Browse all products</a>',
      }));
      $('[data-listing-pagination]').innerHTML = '';
      announce('No products match your filters');
      return;
    }
    resolveRegion(region, `<div class="product-grid">${renderProductGrid(list.results, { eagerFirst: true })}</div>`, {
      label: `${list.count} products loaded`,
    });
    syncWishlistButtons();
    renderPagination(list.count);
  } catch (error) {
    if (error.isAborted) return;
    renderRegionError(region, error, load, { title: 'Products could not be loaded' });
    $('[data-listing-pagination]').innerHTML = '';
  }
}

/* ============================================================================
   Category chrome
   ========================================================================== */

async function initCategory() {
  if (!state.segments.length) {
    document.title = `Shop all products — ${BUSINESS_NAME}`;
    setCanonical(`${origin}/shop.html`);
    return;
  }
  try {
    const tree = await getCategories();
    const { category, trail } = resolveCategoryPath(tree, state.segments);
    if (!category) {
      $('[data-listing-title]').textContent = 'Category not found';
      $('[data-listing-description]').textContent = 'This category may have been renamed or removed.';
      resolveRegion($('[data-listing-results]'), emptyState({
        title: 'Category not found',
        text: 'The category you are looking for is no longer available.',
        iconName: 'folder',
        actionHtml: '<a class="btn btn--primary btn--sm" href="/shop.html">Browse all products</a>',
      }));
      document.querySelector('meta[name="robots"]')?.setAttribute('content', 'noindex, follow');
      return;
    }
    state.category = category;
    state.trail = trail;

    $('[data-listing-title]').textContent = category.name;
    const description = category.description || category.description || '';
    $('[data-listing-description]').textContent = description || `Browse ${category.name} at ${BUSINESS_NAME}.`;
    $('[data-listing-breadcrumbs]').innerHTML = renderCategoryBreadcrumbs(trail);

    document.title = category.seo?.title || `${category.name} — ${BUSINESS_NAME}`;
    setMeta('description', category.seo?.description || truncate(stripTags(description) || `Shop ${category.name} at ${BUSINESS_NAME}.`, 158));
    setCanonical(`${origin}${category.seo?.canonical || categoryUrl(category)}`);

    if (category.banner_image_url) {
      $('[data-listing-banner]').innerHTML = `<div class="category-banner"><img src="${esc(category.banner_image_url)}" alt="${esc(category.banner_alt || category.name)}" width="1600" height="320" loading="eager" decoding="async"></div>`;
    }
    if (category.children?.length) {
      $('[data-listing-subcategories]').innerHTML = renderSubcategoryTiles(category.children);
      hydrateIcons($('[data-listing-subcategories]'));
    }

    injectJsonLd(breadcrumbJsonLd(
      [{ name: 'Home', url: '/' }, { name: 'Shop', url: '/shop.html' }, ...trail.map((c) => ({ name: c.name, url: categoryUrl(c) }))],
      origin,
    ));
    injectJsonLd({
      '@context': 'https://schema.org',
      '@type': 'CollectionPage',
      name: category.name,
      url: `${origin}${categoryUrl(category)}`,
      ...(description ? { description: truncate(stripTags(description), 300) } : {}),
      isPartOf: { '@id': `${origin}/#website` },
    });
  } catch {
    // Category metadata is an enhancement; still load products by slug.
    state.category = { slug: state.segments[state.segments.length - 1], name: state.segments[state.segments.length - 1].replace(/-/g, ' ') };
    $('[data-listing-title]').textContent = state.category.name;
  }
}

function setMeta(name, content) {
  let tag = document.querySelector(`meta[name="${name}"]`);
  if (!tag) { tag = document.createElement('meta'); tag.name = name; document.head.appendChild(tag); }
  tag.content = content;
}
function setCanonical(href) {
  let tag = document.querySelector('link[rel="canonical"]');
  if (!tag) { tag = document.createElement('link'); tag.rel = 'canonical'; document.head.appendChild(tag); }
  tag.href = href;
}
function injectJsonLd(data) {
  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.textContent = JSON.stringify(data);
  document.head.appendChild(script);
}

/* ============================================================================
   Events
   ========================================================================== */

function initEvents() {
  $('[data-listing-sort]')?.addEventListener('change', (event) => {
    state.sort = event.target.value;
    state.page = 1;
    load();
  });

  const sortSelect = $('[data-listing-sort]');
  if (sortSelect) sortSelect.value = state.sort;

  document.addEventListener('click', (event) => {
    const pageLink = event.target.closest('[data-page]');
    if (pageLink) {
      event.preventDefault();
      state.page = Number(pageLink.dataset.page);
      load();
      $('[data-listing-results]')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    if (event.target.closest('[data-filters-clear]')) {
      state.filters = {};
      state.page = 1;
      load();
      loadFacets();
      return;
    }
    const remove = event.target.closest('[data-remove-filter]');
    if (remove) {
      delete state.filters[remove.dataset.removeFilter];
      state.page = 1;
      load();
      loadFacets();
      return;
    }
    const toggle = event.target.closest('[data-filters-toggle]');
    if (toggle) {
      const sidebar = $('[data-filters]');
      const open = sidebar.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    }
  });

  window.addEventListener('popstate', () => {
    const params = readQuery();
    state.page = Number(params.page) || 1;
    state.sort = params.sort || 'featured';
    load();
  });
}

/* ------------------------------------------------------------------- run -- */

initEvents();
await initCategory();
loadFacets();
load();
