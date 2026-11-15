/**
 * search.js — backend-powered search with debounced suggestions.
 *
 * The browser never downloads the catalogue to search it locally. Every query
 * hits `/products/search/?q=` (ranked) or `/products/?q=&ordering=` (sorted).
 * In-flight requests are aborted when the query changes.
 */

import { normalizeList } from './api.js';
import { searchProducts, listProducts } from './products.js';
import { getCategories, flattenTree } from './categories.js';
import { debounce, esc, enc, $, readQuery } from './utils.js';
import { icon, hydrateIcons } from './icons.js';
import { skeletons, announce, resolveRegion, renderRegionError } from './ui.js';
import { productImage, productPrice, PRODUCT_URL } from './products.js';
import { categoryUrl } from './categories.js';

const MIN_CHARS = 2;
const DEBOUNCE_MS = (typeof window !== 'undefined' && window.STARMOND_CONFIG?.SEARCH_DEBOUNCE_MS) || 300;

/* ============================================================================
   Header search with suggestion panel
   ========================================================================== */

export function initSearch() {
  const wrap = $('[data-header-search]');
  if (!wrap) return;
  const input = wrap.querySelector('input[type="search"], input[name="q"]');
  const panel = wrap.querySelector('[data-search-panel]');
  const form = wrap.querySelector('form');
  if (!input || !panel || !form) return;

  let controller = null;
  let open = false;
  let activeIndex = -1;
  let lastQuery = '';

  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', 'search-suggestions');
  input.setAttribute('autocomplete', 'off');
  panel.id = 'search-suggestions';
  panel.setAttribute('role', 'listbox');
  panel.setAttribute('aria-label', 'Search suggestions');

  const setOpen = (next) => {
    open = next;
    panel.hidden = !open;
    input.setAttribute('aria-expanded', String(open));
    if (!open) { activeIndex = -1; input.removeAttribute('aria-activedescendant'); }
  };

  const render = (data, query) => {
    const products = normalizeList(data?.products ?? data?.results ?? data).results.slice(0, 6);
    const categories = (data?.categories || []).slice(0, 3);

    if (!products.length && !categories.length) {
      resolveRegion(panel, `<div class="search-panel__empty">
        <p class="t-sm t-semibold">No matches for “${esc(query)}”</p>
        <p class="t-meta">Try a different product name, brand or category.</p>
        <a class="btn btn--secondary btn--sm" href="/shop.html">Browse all products</a>
      </div>`, { reveal: false });
      setOpen(true);
      announce(`No search results for ${query}`);
      return;
    }

    const html = `
      ${categories.length ? `
        <div class="search-panel__group">
          <p class="search-panel__label">Categories</p>
          ${categories.map((cat, i) => `<a class="search-panel__item" role="option" id="sg-cat-${i}" href="${esc(categoryUrl(cat))}">
            ${icon('folder', { size: 'sm' })}<span>${esc(cat.name)}</span>
          </a>`).join('')}
        </div>` : ''}
      ${products.length ? `
        <div class="search-panel__group">
          <p class="search-panel__label">Products</p>
          ${products.map((product, i) => {
            const image = productImage(product);
            const price = productPrice(product);
            return `<a class="search-panel__item search-panel__item--product" role="option" id="sg-prod-${i}" href="${esc(PRODUCT_URL(product))}">
              <span class="search-panel__thumb">
                ${image ? `<img src="${esc(image.url)}" alt="" width="40" height="40" loading="lazy" decoding="async">` : icon('image', { size: 'sm' })}
              </span>
              <span class="search-panel__meta">
                <span class="t-sm t-medium t-clamp-1">${esc(product.name)}</span>
                <span class="t-meta">${price.formatted ? esc(price.formatted) : 'Price unavailable'}</span>
              </span>
            </a>`;
          }).join('')}
        </div>` : ''}
      <a class="search-panel__all" href="/search.html?q=${enc(query)}">
        See all results for “${esc(query)}” ${icon('arrow-right', { size: 'sm' })}
      </a>`;

    resolveRegion(panel, html, { reveal: false });
    setOpen(true);
    announce(`${products.length + categories.length} suggestions available`);
  };

  const run = async (query) => {
    if (query.length < MIN_CHARS) { setOpen(false); return; }
    if (query === lastQuery && open) return;
    lastQuery = query;
    controller?.abort();
    controller = new AbortController();
    panel.innerHTML = `<div class="search-panel__group">${skeletons.list(3)}</div>`;
    setOpen(true);
    try {
      // Products: GET /products/search/ (relevance-ranked). Categories are
      // matched against the already-loaded category tree.
      const [found, tree] = await Promise.all([
        searchProducts({ q: query, page_size: 6 }, { signal: controller.signal }),
        getCategories().catch(() => []),
      ]);
      const needle = query.toLowerCase();
      const data = {
        products: found.results,
        categories: flattenTree(tree).filter((c) => String(c.name).toLowerCase().includes(needle)),
      };
      if (input.value.trim() !== query) return; // stale response
      render(data, query);
    } catch (error) {
      if (error.isAborted) return;
      resolveRegion(panel, `<div class="search-panel__empty">
        <p class="t-sm t-semibold">Search is unavailable</p>
        <p class="t-meta">${esc(error.userMessage || 'Please try again.')}</p>
        <a class="btn btn--secondary btn--sm" href="/search.html?q=${enc(query)}">Open full search</a>
      </div>`, { reveal: false });
      setOpen(true);
    }
  };

  const debounced = debounce((value) => run(value), DEBOUNCE_MS);

  input.addEventListener('input', () => {
    const value = input.value.trim();
    if (value.length < MIN_CHARS) { debounced.cancel(); setOpen(false); return; }
    debounced(value);
  });

  input.addEventListener('focus', () => {
    if (input.value.trim().length >= MIN_CHARS && panel.innerHTML.trim()) setOpen(true);
  });

  const options = () => [...panel.querySelectorAll('[role="option"]')];

  input.addEventListener('keydown', (event) => {
    if (!open) return;
    const items = options();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!items.length) return;
      event.preventDefault();
      activeIndex = event.key === 'ArrowDown'
        ? (activeIndex + 1) % items.length
        : (activeIndex - 1 + items.length) % items.length;
      items.forEach((item, i) => item.classList.toggle('is-active', i === activeIndex));
      input.setAttribute('aria-activedescendant', items[activeIndex].id);
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter' && activeIndex >= 0 && items[activeIndex]) {
      event.preventDefault();
      items[activeIndex].click();
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  });

  form.addEventListener('submit', (event) => {
    const value = input.value.trim();
    if (!value) { event.preventDefault(); input.focus(); return; }
    setOpen(false);
  });

  document.addEventListener('click', (event) => { if (!wrap.contains(event.target)) setOpen(false); });
}

/* ============================================================================
   Full search results page
   ========================================================================== */

export function initSearchPage({ renderGrid, onResults }) {
  const params = readQuery();
  const input = $('[data-search-page-input]');
  if (input && params.q) input.value = params.q;

  const state = {
    q: params.q || '',
    category: params.category || '',
    page: Number(params.page) || 1,
    sort: params.sort || 'relevance',
  };

  let controller = null;

  const load = async () => {
    const region = $('[data-search-results]');
    const heading = $('[data-search-heading]');
    if (heading) {
      heading.textContent = state.q ? `Search results for “${state.q}”` : 'Search the store';
    }
    document.title = state.q ? `Search: ${state.q} — Starmond Technology Limited` : 'Search — Starmond Technology Limited';

    if (!state.q) {
      resolveRegion(region, `<div class="state state--flat">
        <span class="state__icon">${icon('search', { size: 'xl' })}</span>
        <p class="state__title">What are you looking for?</p>
        <p class="state__text">Search by product name, brand, SKU, category or attribute.</p>
      </div>`, { reveal: false });
      $('[data-search-count]')?.replaceChildren();
      return;
    }

    controller?.abort();
    controller = new AbortController();
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.productGrid(8);

    try {
      const ordering = { newest: '-created_at', price_asc: 'price', price_desc: '-price', rating: '-avg_rating' }[state.sort];
      const query = { q: state.q, category: state.category || undefined, page: state.page };
      // "Most relevant" uses the ranked search endpoint; explicit sorts use the
      // catalogue endpoint with the same keyword filter.
      const list = ordering
        ? await listProducts({ ...query, ordering }, { signal: controller.signal })
        : await searchProducts(query, { signal: controller.signal });
      onResults?.(list, state);
      renderGrid(region, list, state);
      announce(`${list.count} results for ${state.q}`);
    } catch (error) {
      if (error.isAborted) return;
      renderRegionError(region, error, load, { title: 'Search is unavailable' });
    }
  };

  $('[data-search-page-form]')?.addEventListener('submit', (event) => {
    event.preventDefault();
    state.q = input.value.trim();
    state.page = 1;
    const url = new URL(location.href);
    if (state.q) url.searchParams.set('q', state.q); else url.searchParams.delete('q');
    url.searchParams.delete('page');
    history.replaceState({}, '', url);
    load();
  });

  $('[data-search-sort]')?.addEventListener('change', (event) => {
    state.sort = event.target.value;
    state.page = 1;
    load();
  });

  return { state, load, setPage: (page) => { state.page = page; load(); } };
}

export default { initSearch, initSearchPage };
