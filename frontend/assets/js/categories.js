/**
 * categories.js — dynamic category tree.
 *
 * Nothing about the category structure is hardcoded. Depth is unlimited: the
 * mega menu shows the first two levels and every deeper level is reachable
 * through the category page, which renders its own children.
 */

import api, { normalizeList } from './api.js';
import { esc, enc } from './utils.js';
import { icon } from './icons.js';

let treePromise = null;
let treeValue = null;

/** Canonical SEO path for a category: /shop/<parent>/<child>/ */
export function categoryUrl(category) {
  if (!category) return '/shop.html';
  // Backend categories carry their canonical storefront path (`url_path`).
  if (category.url_path) return category.url_path;
  if (category.url) return category.url;
  if (category.path) return `/shop/${String(category.path).replace(/^\/+|\/+$/g, '')}/`;
  const segments = [];
  let node = category;
  const guard = new Set();
  while (node && !guard.has(node.id ?? node.slug)) {
    guard.add(node.id ?? node.slug);
    if (node.slug) segments.unshift(node.slug);
    node = node.parent && typeof node.parent === 'object' ? node.parent : null;
  }
  return segments.length ? `/shop/${segments.join('/')}/` : '/shop.html';
}

/** Breadcrumb trail from the root to this category. */
export function categoryTrail(category, flatList = null) {
  const trail = [];
  let node = category;
  const guard = new Set();
  while (node) {
    const key = node.id ?? node.slug;
    if (guard.has(key)) break;
    guard.add(key);
    trail.unshift(node);
    if (node.parent && typeof node.parent === 'object') node = node.parent;
    else if (node.parent && flatList) node = flatList.find((c) => String(c.id) === String(node.parent));
    else node = null;
  }
  return trail;
}

/**
 * Fetch the active category tree once per page load.
 * The backend is expected to return nested `children`; a flat list with
 * `parent` ids is also accepted and assembled here for display purposes only.
 */
export async function getCategories({ force = false } = {}) {
  if (treeValue && !force) return treeValue;
  if (treePromise && !force) return treePromise;

  treePromise = api.publicGet('/categories/')
    .then((data) => {
      const list = normalizeList(data).results;
      treeValue = assembleTree(list);
      return treeValue;
    })
    .finally(() => { treePromise = null; });

  return treePromise;
}

export function assembleTree(list) {
  if (!Array.isArray(list) || !list.length) return [];
  const hasNested = list.some((c) => Array.isArray(c.children));
  if (hasNested) return list.filter((c) => !c.parent || typeof c.parent === 'object');

  const byId = new Map(list.map((c) => [String(c.id), { ...c, children: [] }]));
  const roots = [];
  byId.forEach((node) => {
    const parentId = node.parent && typeof node.parent === 'object' ? node.parent.id : node.parent;
    if (parentId && byId.has(String(parentId))) byId.get(String(parentId)).children.push(node);
    else roots.push(node);
  });
  const sortRec = (nodes) => {
    nodes.sort((a, b) => (a.display_order ?? a.order ?? 0) - (b.display_order ?? b.order ?? 0) || String(a.name).localeCompare(String(b.name)));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

/** Depth-first flatten with depth metadata. */
export function flattenTree(nodes, depth = 0, out = []) {
  nodes.forEach((node) => {
    out.push({ ...node, depth });
    if (node.children?.length) flattenTree(node.children, depth + 1, out);
  });
  return out;
}

export function findCategoryBySlug(tree, slug) {
  for (const node of tree) {
    if (node.slug === slug) return node;
    if (node.children?.length) {
      const found = findCategoryBySlug(node.children, slug);
      if (found) return found;
    }
  }
  return null;
}

/** Resolve /shop/a/b/c/ to the deepest matching category. */
export function resolveCategoryPath(tree, segments) {
  let current = null;
  let nodes = tree;
  const trail = [];
  for (const segment of segments) {
    const match = nodes.find((n) => n.slug === segment);
    if (!match) break;
    current = match;
    trail.push(match);
    nodes = match.children || [];
  }
  return { category: current, trail };
}

/* ============================================================================
   Renderers
   ========================================================================== */

const MAX_MENU_CHILDREN = 8;

/** Mega menu: top-level columns, each with a capped list of children. */
export function renderMegaMenu(tree, { maxColumns = 4 } = {}) {
  if (!tree.length) {
    return `<div class="state state--inline state--flat">
      <p class="state__title">Categories are unavailable right now</p>
      <p class="state__text">Browse the full catalogue instead.</p>
      <div class="state__actions"><a class="btn btn--secondary btn--sm" href="/shop.html">Open shop</a></div>
    </div>`;
  }
  const columns = tree.slice(0, maxColumns);
  return `
    <div class="mega__grid">
      ${columns.map((cat) => `
        <div>
          <p class="mega__col-title">
            <a href="${esc(categoryUrl(cat))}">${esc(cat.name)}</a>
          </p>
          ${cat.children?.length ? `
            <ul class="mega__list">
              ${cat.children.slice(0, MAX_MENU_CHILDREN).map((child) => `
                <li><a href="${esc(categoryUrl(child))}">${esc(child.name)}</a></li>`).join('')}
              ${cat.children.length > MAX_MENU_CHILDREN ? `<li><a href="${esc(categoryUrl(cat))}">View all ${esc(cat.name.toLowerCase())} ${icon('arrow-right', { size: 'sm' })}</a></li>` : ''}
            </ul>` : `<p class="t-meta">${esc(cat.description || '')}</p>`}
        </div>`).join('')}
    </div>
    <div class="mega__footer">
      <p class="t-meta">Explore every department in the store.</p>
      <a class="btn btn--soft btn--sm" href="/shop.html">Browse all categories ${icon('arrow-right', { size: 'sm' })}</a>
    </div>`;
}

/** Mobile drawer category accordion. */
export function renderDrawerCategories(tree) {
  if (!tree.length) return '<p class="t-meta" style="padding:var(--space-3)">Categories are unavailable right now.</p>';
  return tree.map((cat) => `
    <details>
      <summary class="drawer-nav__link">
        <span>${esc(cat.name)}</span>
        ${icon('chevron-down', { size: 'sm' })}
      </summary>
      <div class="drawer-nav__sub">
        <a href="${esc(categoryUrl(cat))}">All ${esc(cat.name)}</a>
        ${(cat.children || []).map((child) => `<a href="${esc(categoryUrl(child))}">${esc(child.name)}</a>`).join('')}
      </div>
    </details>`).join('');
}

/** Footer category column (top-level only, capped). */
export function renderFooterCategories(tree, limit = 6) {
  if (!tree.length) return '<li><a href="/shop.html">All products</a></li>';
  return tree.slice(0, limit).map((cat) => `<li><a href="${esc(categoryUrl(cat))}">${esc(cat.name)}</a></li>`).join('');
}

/** Homepage / shop category cards. */
export function renderCategoryCards(categories) {
  return categories.map((cat) => {
    const image = cat.image_url || cat.image || null;
    return `<a class="category-card" href="${esc(categoryUrl(cat))}">
      <span class="category-card__media">
        ${image
          ? `<img src="${esc(image)}" alt="${esc(cat.image_alt || cat.name)}" width="480" height="360" loading="lazy" decoding="async">`
          : `<span class="category-card__placeholder" aria-hidden="true">${icon('folder', { size: 'xl' })}</span>`}
      </span>
      <span class="category-card__body">
        <span class="category-card__name">${esc(cat.name)}</span>
        ${cat.short_description || cat.description ? `<span class="category-card__desc t-clamp-2">${esc(cat.short_description || cat.description)}</span>` : ''}
        <span class="category-card__cta">Browse ${icon('arrow-right', { size: 'sm' })}</span>
      </span>
    </a>`;
  }).join('');
}

/** Child-category tiles shown at the top of a category page. */
export function renderSubcategoryTiles(children) {
  if (!children?.length) return '';
  return `<div class="subcategory-tiles">
    ${children.map((child) => {
      const image = child.image_url || child.image;
      return `<a class="category-tile" href="${esc(categoryUrl(child))}">
        ${image ? `<img class="category-tile__thumb" src="${esc(image)}" alt="" width="44" height="44" loading="lazy" decoding="async">`
                : `<span class="category-tile__thumb" aria-hidden="true" style="display:inline-flex;align-items:center;justify-content:center;color:var(--color-primary)">${icon('folder')}</span>`}
        <span>${esc(child.name)}</span>
        ${typeof child.product_count === 'number' ? `<span class="t-meta" style="margin-left:auto">${child.product_count}</span>` : ''}
      </a>`;
    }).join('')}
  </div>`;
}

/** Breadcrumb HTML for a category trail. */
export function renderCategoryBreadcrumbs(trail, currentLabel = null) {
  const items = [{ name: 'Home', url: '/' }, { name: 'Shop', url: '/shop.html' }];
  trail.forEach((cat) => items.push({ name: cat.name, url: categoryUrl(cat) }));
  if (currentLabel) items.push({ name: currentLabel, url: null });
  return `<nav class="breadcrumbs" aria-label="Breadcrumb">
    <ol class="breadcrumbs__list">
      ${items.map((item, i) => `<li class="breadcrumbs__item">${
        item.url && i < items.length - 1
          ? `<a href="${esc(item.url)}">${esc(item.name)}</a>`
          : `<span aria-current="page">${esc(item.name)}</span>`
      }</li>`).join('')}
    </ol>
  </nav>`;
}

/** JSON-LD BreadcrumbList — only real, resolvable URLs. */
export function breadcrumbJsonLd(items, origin) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      ...(item.url ? { item: `${origin}${item.url}` } : {}),
    })),
  };
}

export function categorySearchParams(category) {
  return category ? { category: category.slug ?? category.id } : {};
}

export { enc };
export default { getCategories, categoryUrl, renderMegaMenu, renderCategoryCards };
