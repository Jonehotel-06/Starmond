/**
 * Shared listing engine for shop.html, category/<slug>/ and deals.html.
 * All filtering/sorting/pagination is executed by the backend; this module only
 * translates UI state into query parameters and renders what comes back.
 */
import { catalog } from '../api.js';
import { CONFIG } from '../env.js';
import { renderProducts, renderPager } from '../ui/cards.js';
import { skeletonGrid, errorState, inlineLoading } from '../ui/feedback.js';
import { debounce, esc, money, qs, qsa, setParams } from '../utils.js';

const CATEGORY_LABELS = {
  'laptops-computing': 'Laptops & Computing',
  'phones-tablets': 'Phones & Tablets',
  'audio-headphones': 'Audio & Headphones',
  'wearables-smart-devices': 'Wearables & Smart Devices',
  'power-charging': 'Power & Charging',
  'accessories-cables': 'Accessories & Cables',
  'networking-smart-home': 'Networking & Smart Home'
};

export function setupListing({ fixedCategory = null, preset = {}, summaryEl = null } = {}) {
  const form = qs('[data-filters-form]');
  const grid = qs('[data-results-grid]');
  const countEl = qs('[data-results-count]');
  const chipsEl = qs('[data-active-chips]');
  const pager = qs('[data-pager]');
  const sortEl = qs('[data-sort]');
  const brandsEl = qs('[data-filter-brands]');
  const filtersToggle = qs('[data-filters-toggle]');
  const filtersPanel = qs('[data-filters-panel]');
  if (!grid) return null;

  let lastPage = null;
  let requestId = 0;

  function readQuery() {
    const sp = new URLSearchParams(window.location.search);
    const query = { ...preset };
    if (sp.get('q')) query.q = sp.get('q');
    query.ordering = sp.get('ordering') || preset.ordering || '-created_at';
    query.page = Number(sp.get('page') || 1) || 1;
    query.page_size = CONFIG.PRODUCTS_PER_PAGE;
    if (sp.get('min_price')) query.min_price = sp.get('min_price');
    if (sp.get('max_price')) query.max_price = sp.get('max_price');
    if (sp.get('in_stock')) query.in_stock = 1;
    if (sp.get('on_sale')) query.on_sale = 1;
    const brands = sp.getAll('brand').filter(Boolean);
    if (brands.length) query.brand = brands;
    const cats = sp.getAll('category').filter(Boolean);
    if (fixedCategory) query.category = fixedCategory;
    else if (cats.length) query.category = cats;
    return query;
  }

  function syncControls() {
    const sp = new URLSearchParams(window.location.search);
    if (sortEl) sortEl.value = sp.get('ordering') || preset.ordering || '-created_at';
    if (!form) return;
    qsa('input[type="checkbox"][name]', form).forEach((input) => {
      input.checked = sp.getAll(input.name).includes(input.value);
    });
    ['min_price', 'max_price'].forEach((name) => {
      const input = form.querySelector(`[name="${name}"]`);
      if (input) input.value = sp.get(name) || '';
    });
  }

  function renderChips(query) {
    if (!chipsEl) return;
    const chips = [];
    if (query.q) chips.push({ label: `“${query.q}”`, params: { q: null } });
    (Array.isArray(query.category) ? query.category : []).forEach((c) => chips.push({
      label: CATEGORY_LABELS[c] || c, params: { category: null, __pull: { key: 'category', value: c } }
    }));
    (Array.isArray(query.brand) ? query.brand : []).forEach((b) => chips.push({
      label: b, params: { brand: null, __pull: { key: 'brand', value: b } }
    }));
    if (query.min_price) chips.push({ label: `From ${money(query.min_price)}`, params: { min_price: null } });
    if (query.max_price) chips.push({ label: `Up to ${money(query.max_price)}`, params: { max_price: null } });
    if (query.in_stock) chips.push({ label: 'In stock only', params: { in_stock: null } });
    if (query.on_sale) chips.push({ label: 'On promotion', params: { on_sale: null } });

    chipsEl.innerHTML = chips.map((chip, i) => `<span class="chip">${esc(chip.label)}
      <button type="button" data-chip="${i}" aria-label="Remove filter ${esc(chip.label)}">
        <svg class="icon icon--sm" aria-hidden="true"><use href="#i-close"></use></svg>
      </button></span>`).join('');

    qsa('[data-chip]', chipsEl).forEach((btn) => {
      btn.addEventListener('click', () => {
        const chip = chips[Number(btn.dataset.chip)];
        const url = new URL(window.location.href);
        if (chip.params.__pull) {
          const { key, value } = chip.params.__pull;
          const remaining = url.searchParams.getAll(key).filter((v) => v !== value);
          url.searchParams.delete(key);
          remaining.forEach((v) => url.searchParams.append(key, v));
        } else {
          Object.keys(chip.params).forEach((key) => url.searchParams.delete(key));
        }
        url.searchParams.delete('page');
        window.history.pushState({}, '', url.pathname + url.search);
        load();
      });
    });
  }

  async function load({ scroll = false } = {}) {
    const query = readQuery();
    const ticket = ++requestId;
    skeletonGrid(grid, Math.min(8, CONFIG.PRODUCTS_PER_PAGE));
    if (countEl) countEl.textContent = 'Loading products…';
    if (pager) pager.hidden = true;

    try {
      const data = await catalog.products(query);
      if (ticket !== requestId) return;
      lastPage = data;
      renderProducts(grid, data.items, {
        emptyTitle: query.q ? 'No products match that search' : 'No products available',
        emptyMessage: query.q
          ? 'Try a shorter or more general search term, or clear the filters.'
          : 'Nothing in this category matches the selected filters yet.'
      });
      if (countEl) {
        countEl.textContent = data.count
          ? `${data.count} product${data.count === 1 ? '' : 's'}${query.q ? ` for “${query.q}”` : ''}`
          : 'No products found';
      }
      if (summaryEl && !query.q) {
        summaryEl.textContent = data.count
          ? `${data.count} product${data.count === 1 ? '' : 's'} currently listed. Prices and stock are live from our inventory system.`
          : 'No products are listed here yet. Check back soon.';
      }
      renderChips(query);
      renderPager(pager, data, (page) => {
        setParams({ page: page === 1 ? null : page });
        load({ scroll: true });
      });
      if (scroll) {
        grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
        grid.setAttribute('tabindex', '-1');
        grid.focus({ preventScroll: true });
      }
      document.dispatchEvent(new CustomEvent('starmond:products-loaded', { detail: data }));
    } catch (err) {
      if (ticket !== requestId) return;
      errorState(grid, err);
      grid.querySelector('[data-retry]')?.addEventListener('click', () => load());
      if (countEl) countEl.textContent = 'Could not load products';
    }
  }

  async function loadFacets() {
    if (!brandsEl) return;
    const query = fixedCategory ? { category: fixedCategory } : {};
    try {
      const facets = await catalog.facets(query);
      const brands = facets?.brands || facets?.facets?.brands || [];
      if (!brands.length) {
        brandsEl.innerHTML = '<p class="muted small">No brand filter available for this selection.</p>';
        return;
      }
      const selected = new URLSearchParams(window.location.search).getAll('brand');
      brandsEl.innerHTML = brands.map((brand) => {
        const value = typeof brand === 'string' ? brand : (brand.value ?? brand.name ?? brand.slug);
        const count = typeof brand === 'object' ? (brand.count ?? brand.doc_count) : null;
        return `<label class="check"><input type="checkbox" name="brand" value="${esc(value)}"
          ${selected.includes(String(value)) ? 'checked' : ''}><span>${esc(value)}${count ? ` <span class="muted">(${count})</span>` : ''}</span></label>`;
      }).join('');
    } catch {
      brandsEl.innerHTML = '<p class="muted small">Brand filter unavailable right now.</p>';
    }
  }

  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const url = new URL(window.location.href);
      ['category', 'brand', 'min_price', 'max_price', 'in_stock', 'on_sale'].forEach((key) => url.searchParams.delete(key));
      ['min_price', 'max_price'].forEach((key) => {
        const value = String(data.get(key) || '').trim();
        if (value) url.searchParams.set(key, value);
      });
      if (data.get('in_stock')) url.searchParams.set('in_stock', '1');
      if (data.get('on_sale')) url.searchParams.set('on_sale', '1');
      if (!fixedCategory) data.getAll('category').forEach((v) => url.searchParams.append('category', String(v)));
      data.getAll('brand').forEach((v) => url.searchParams.append('brand', String(v)));
      url.searchParams.delete('page');
      window.history.pushState({}, '', url.pathname + url.search);
      load({ scroll: true });
      if (window.innerWidth <= 980) filtersPanel?.classList.remove('is-open');
    });
  }

  qs('[data-filters-reset]')?.addEventListener('click', () => {
    const url = new URL(window.location.href);
    ['category', 'brand', 'min_price', 'max_price', 'in_stock', 'on_sale', 'page', 'q'].forEach((k) => url.searchParams.delete(k));
    window.history.pushState({}, '', url.pathname + url.search);
    syncControls();
    load();
  });

  sortEl?.addEventListener('change', () => {
    setParams({ ordering: sortEl.value, page: null });
    load();
  });

  filtersToggle?.addEventListener('click', () => {
    const open = filtersPanel?.classList.toggle('is-open');
    filtersToggle.setAttribute('aria-expanded', String(Boolean(open)));
  });

  window.addEventListener('popstate', () => { syncControls(); load(); });

  syncControls();
  loadFacets();
  load();
  return { load, reload: () => load() };
}
