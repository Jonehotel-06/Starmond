/** Product card, grid and pagination renderers shared by every listing page. */
import { esc, money, sitePath, starRow } from '../utils.js';
import { wishlist } from '../store.js';
import { CONFIG } from '../env.js';

/** In-memory lookup of rendered products, used by delegated cart/wishlist actions. */
export const productRegistry = new Map();

export function rememberProducts(products = []) {
  products.forEach((p) => { if (p?.id) productRegistry.set(String(p.id), p); });
  return products;
}

export function productImage(product) {
  const img = product.primary_image || product.image || product.thumbnail;
  if (img) return typeof img === 'string' ? img : (img.url || img.src || '');
  return '';
}

export function productUrl(product) {
  const slug = encodeURIComponent(product.slug || '');
  /* Set USE_PRETTY_PRODUCT_URLS once the backend serves /product/<slug>/. */
  if (CONFIG.USE_PRETTY_PRODUCT_URLS) return `${sitePath('product/')}${slug}/`;
  return `${sitePath('product.html')}?slug=${slug}`;
}

export function priceBlock(product) {
  const price = money(product.price, product.currency || 'NGN');
  const was = product.compare_at_price && Number(product.compare_at_price) > Number(product.price);
  const off = was
    ? Math.round(((Number(product.compare_at_price) - Number(product.price)) / Number(product.compare_at_price)) * 100)
    : 0;
  return `<div class="p-card__price">
      <span class="price">${price}</span>
      ${was ? `<span class="price--was">${money(product.compare_at_price, product.currency || 'NGN')}</span><span class="price--off">-${off}%</span>` : ''}
    </div>`;
}

export function stockLabel(product) {
  if (product.in_stock === false) return { text: 'Out of stock', cls: 'badge--out' };
  const qty = Number(product.stock_quantity);
  if (Number.isFinite(qty) && qty > 0 && qty <= 5) return { text: `Only ${qty} left`, cls: 'badge--low' };
  return { text: 'In stock', cls: 'badge--ok' };
}

export function productCard(product, { showWishlist = true } = {}) {
  rememberProducts([product]);
  const img = productImage(product);
  const stock = stockLabel(product);
  const onSale = product.compare_at_price && Number(product.compare_at_price) > Number(product.price);
  const rating = Number(product.rating_average ?? product.rating ?? 0);
  const reviews = product.review_count ?? 0;
  const saved = wishlist.has(product.id);
  const name = esc(product.name || 'Product');
  const category = product.category?.name || product.category_name || '';

  return `<article class="p-card" data-product-id="${esc(product.id)}">
    <div class="p-card__media">
      ${img
        ? `<img src="${esc(img)}" alt="${esc(name)}" loading="lazy" decoding="async" width="400" height="300">`
        : `<div class="media-placeholder" aria-hidden="true"><span>${esc(category || 'Product')}</span></div>`}
      <div class="p-card__badges">
        ${onSale ? '<span class="badge badge--sale">Sale</span>' : ''}
        ${product.is_new ? '<span class="badge badge--new">New</span>' : ''}
        <span class="badge ${stock.cls}">${esc(stock.text)}</span>
      </div>
      ${showWishlist ? `<button class="icon-btn p-card__wish" type="button" data-wishlist-toggle
          aria-pressed="${saved ? 'true' : 'false'}"
          aria-label="${saved ? 'Remove from' : 'Save to'} wishlist">
          <svg class="icon" aria-hidden="true"><use href="#i-heart"></use></svg>
        </button>` : ''}
    </div>
    <div class="p-card__body">
      ${category ? `<p class="p-card__cat">${esc(category)}</p>` : ''}
      <h3 class="p-card__title"><a href="${productUrl(product)}">${name}</a></h3>
      ${rating > 0 ? `<span class="p-card__rating"><svg class="icon" aria-hidden="true"><use href="#i-star"></use></svg>${rating.toFixed(1)}${reviews ? ` (${reviews})` : ''}</span>`
        : '<span class="p-card__rating muted">No reviews yet</span>'}
      ${priceBlock(product)}
      <div class="p-card__actions">
        <button class="btn btn--outline" type="button" data-add-to-cart ${product.in_stock === false ? 'disabled' : ''}>
          ${product.in_stock === false ? 'Unavailable' : 'Add to cart'}
        </button>
        <button class="btn btn--primary" type="button" data-buy-now ${product.in_stock === false ? 'disabled' : ''}>Buy now</button>
      </div>
    </div>
  </article>`;
}

export function renderProducts(container, products, opts = {}) {
  if (!container) return;
  container.removeAttribute('aria-busy');
  if (!products?.length) {
    container.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <svg class="icon icon--lg" aria-hidden="true"><use href="#i-package"></use></svg>
      <h2 class="h2">${esc(opts.emptyTitle || 'No products found')}</h2>
      <p>${esc(opts.emptyMessage || 'Try a different category or clear your filters.')}</p>
    </div>`;
    return;
  }
  container.innerHTML = products.map((p) => productCard(p, opts)).join('');
}

export function renderPager(nav, pageData, onNavigate) {
  if (!nav) return;
  const { page = 1, pages = 1 } = pageData || {};
  if (pages <= 1) { nav.hidden = true; nav.innerHTML = ''; return; }
  nav.hidden = false;
  const link = (label, target, { current = false, disabled = false, aria = '' } = {}) => {
    const tag = disabled ? 'span' : 'button';
    const attrs = disabled ? 'aria-disabled="true"' : `type="button" data-page="${target}"`;
    return `<${tag} class="pager__link" ${attrs} ${current ? 'aria-current="page"' : ''} ${aria}>${label}</${tag}>`;
  };
  const windowPages = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  for (let i = start; i <= end; i += 1) windowPages.push(i);

  nav.innerHTML = [
    link('Prev', page - 1, { disabled: page <= 1 }),
    ...windowPages.map((p) => link(String(p), p, { current: p === page })),
    link('Next', page + 1, { disabled: page >= pages })
  ].join('');

  nav.querySelectorAll('[data-page]').forEach((btn) => {
    btn.addEventListener('click', () => onNavigate(Number(btn.dataset.page)));
  });
}
