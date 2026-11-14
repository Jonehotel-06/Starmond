/**
 * admin.mjs — page definitions for the administration console.
 * Every page is noindex,nofollow and gated by backend permissions at runtime.
 */
import { ADMIN_MODULES } from '../lib/shell.mjs';

const sk = (cls) => `<span class="sk ${cls}" aria-hidden="true"></span>`;
const statSkeletons = (n) => `<div class="admin-stats" aria-hidden="true">${
  Array.from({ length: n }, () => `<div class="sk-stat"><div class="sk-stat__head">${sk('sk--text-sm sk--w-50')}${sk('sk--icon')}</div>${sk('sk--title sk--w-60')}${sk('sk--text-sm sk--w-40')}</div>`).join('')}</div>`;
const tableSkeleton = (rows = 8, cols = 5) => `<div class="sk-table" aria-hidden="true">${
  Array.from({ length: rows }, () => `<div class="sk-table__row" style="grid-template-columns:${Array.from({ length: cols }, (_, i) => (i === 0 ? '2fr' : '1fr')).join(' ')}">${Array.from({ length: cols }, () => sk('')).join('')}</div>`).join('')}</div>`;

const allModules = ADMIN_MODULES.flatMap((g) => g.items);

/** Generic CRUD module page: toolbar + table + pagination, driven by JS config. */
function modulePage(mod, { description, primaryAction = null }) {
  return `<div class="admin-page-head">
  <div class="admin-page-head__text">
    <h2 class="admin-page-head__title">${mod.label}</h2>
    <p class="admin-page-head__sub">${description}</p>
  </div>
  <div class="admin-page-head__actions" data-module-actions>
    ${primaryAction ? `<button type="button" class="btn btn--primary" data-create ${primaryAction.perm ? `data-perm="${primaryAction.perm}"` : ''}><i data-icon="plus" data-size="sm"></i> ${primaryAction.label}</button>` : ''}
  </div>
</div>
<div class="data-panel" data-admin-module="${mod.id}">
  <div class="data-panel__toolbar">
    <div class="data-panel__search">
      <i data-icon="search" data-size="sm"></i>
      <label class="sr-only" for="module-search-${mod.id}">Search ${mod.label.toLowerCase()}</label>
      <input class="input" id="module-search-${mod.id}" type="search" placeholder="Search ${mod.label.toLowerCase()}" data-module-search>
    </div>
    <div class="data-panel__filters" data-module-filters></div>
    <span class="data-panel__spacer"></span>
    <button type="button" class="btn btn--secondary btn--sm" data-module-refresh><i data-icon="refresh" data-size="sm"></i> Refresh</button>
    <button type="button" class="btn btn--secondary btn--sm" data-module-export hidden><i data-icon="download" data-size="sm"></i> Export</button>
  </div>
  <div data-module-bulk hidden></div>
  <div data-module-table data-loading-region aria-busy="true">${tableSkeleton()}</div>
  <div class="data-panel__foot">
    <p class="data-panel__count" data-module-count aria-live="polite"></p>
    <nav class="pagination" data-module-pagination aria-label="${mod.label} pagination"></nav>
  </div>
</div>`;
}

const DESCRIPTIONS = {
  products: 'Create, edit, archive and publish products. Prices and stock remain backend-authoritative.',
  categories: 'Manage top-level departments, their imagery, ordering and SEO fields.',
  subcategories: 'Manage nested categories under any parent department.',
  variations: 'Manage product options such as size and colour, and their SKUs.',
  inventory: 'Track stock levels, low-stock alerts and stock adjustments.',
  media: 'Upload and organise product, category and content imagery.',
  orders: 'Review orders, update fulfilment status and manage exceptions.',
  payments: 'Inspect Paystack transactions and their verified status.',
  refunds: 'Review refund requests and process approved refunds.',
  delivery: 'Manage delivery methods, assignments and dispatch updates.',
  'shipping-zones': 'Define delivery coverage and zone-based shipping rates.',
  customers: 'View customer records and their order activity.',
  reviews: 'Moderate customer reviews before they appear on the storefront.',
  enquiries: 'Respond to messages submitted through the contact form.',
  newsletter: 'Manage newsletter subscribers and consent records.',
  discounts: 'Create and manage discount codes and their eligibility rules.',
  promotions: 'Manage promotional banners and campaign scheduling.',
  notifications: 'Notification templates and delivery status.',
  'email-logs': 'Delivery log for transactional and marketing email.',
  staff: 'Invite staff, assign roles and review effective permissions.',
  'audit-logs': 'Immutable record of administrative actions.',
};

const PRIMARY = {
  products: { label: 'New product', perm: 'products.create' },
  categories: { label: 'New category', perm: 'categories.create' },
  subcategories: { label: 'New subcategory', perm: 'categories.create' },
  variations: { label: 'New variation', perm: 'products.create' },
  'shipping-zones': { label: 'New zone', perm: 'delivery.create' },
  delivery: { label: 'New delivery method', perm: 'delivery.create' },
  discounts: { label: 'New discount', perm: 'discounts.create' },
  promotions: { label: 'New promotion', perm: 'promotions.create' },
  staff: { label: 'Invite staff', perm: 'staff.create' },
  media: { label: 'Upload media', perm: 'media.create' },
};

/* ---------------------------------------------------------------- custom -- */

const dashboardBody = `<div class="admin-page-head">
  <div class="admin-page-head__text">
    <h2 class="admin-page-head__title">Business overview</h2>
    <p class="admin-page-head__sub">Live figures from the order, payment and inventory systems. Pending payments are never counted as realised revenue.</p>
  </div>
  <div class="admin-page-head__actions">
    <label class="sr-only" for="dash-range">Reporting period</label>
    <select class="select" id="dash-range" data-dashboard-range style="width:auto">
      <option value="7">Last 7 days</option>
      <option value="30" selected>Last 30 days</option>
      <option value="90">Last 90 days</option>
      <option value="365">Last 12 months</option>
    </select>
    <button type="button" class="btn btn--secondary" data-dashboard-refresh><i data-icon="refresh" data-size="sm"></i> Refresh</button>
  </div>
</div>

<div data-dashboard-stats data-loading-region aria-busy="true">${statSkeletons(8)}</div>

<div class="admin-grid-2-1">
  <div class="card">
    <div class="card__head"><h3 class="card__title">Sales trend</h3><span class="t-meta" data-trend-caption></span></div>
    <div class="card__body" data-dashboard-chart data-loading-region aria-busy="true">
      <div class="stack" aria-hidden="true">${sk('sk--text-sm sk--w-25')}<span class="sk" style="height:220px;border-radius:var(--radius-md)"></span></div>
    </div>
  </div>
  <div class="card">
    <div class="card__head"><h3 class="card__title">Inventory alerts</h3><a class="t-sm" href="/admin/inventory.html">Manage</a></div>
    <div class="card__body" data-dashboard-inventory data-loading-region aria-busy="true">
      <div class="sk-list" aria-hidden="true">${Array.from({ length: 4 }, () => `<div class="sk-list__item">${sk('sk--thumb')}<div class="sk-list__body">${sk('sk--text sk--w-70')}${sk('sk--text-sm sk--w-40')}</div></div>`).join('')}</div>
    </div>
  </div>
</div>

<div class="admin-grid-2">
  <div class="card">
    <div class="card__head"><h3 class="card__title">Recent orders</h3><a class="t-sm" href="/admin/orders.html">View all</a></div>
    <div class="card__body card__body--flush" data-dashboard-orders data-loading-region aria-busy="true">${tableSkeleton(5, 4)}</div>
  </div>
  <div class="card">
    <div class="card__head"><h3 class="card__title">Best-selling products</h3><a class="t-sm" href="/admin/reports.html">Full report</a></div>
    <div class="card__body card__body--flush" data-dashboard-bestsellers data-loading-region aria-busy="true">${tableSkeleton(5, 3)}</div>
  </div>
</div>`;

const reportsBody = `<div class="admin-page-head">
  <div class="admin-page-head__text">
    <h2 class="admin-page-head__title">Financial reports</h2>
    <p class="admin-page-head__sub">All figures are generated by the backend reporting service. Orders created, paid, fulfilled, cancelled and refunded are reported separately.</p>
  </div>
  <div class="admin-page-head__actions">
    <button type="button" class="btn btn--secondary" data-export="csv" data-perm="reports.export"><i data-icon="download" data-size="sm"></i> CSV</button>
    <button type="button" class="btn btn--secondary" data-export="xlsx" data-perm="reports.export"><i data-icon="download" data-size="sm"></i> Excel</button>
    <button type="button" class="btn btn--secondary" data-export="pdf" data-perm="reports.export"><i data-icon="download" data-size="sm"></i> PDF</button>
  </div>
</div>

<div class="card">
  <div class="card__body">
    <form class="report-filters" data-report-filters>
      <div class="field"><label class="field__label" for="rp-from">From</label><input class="input" id="rp-from" name="date_from" type="date"></div>
      <div class="field"><label class="field__label" for="rp-to">To</label><input class="input" id="rp-to" name="date_to" type="date"></div>
      <div class="field"><label class="field__label" for="rp-group">Group by</label>
        <select class="select" id="rp-group" name="group_by"><option value="day">Day</option><option value="week">Week</option><option value="month" selected>Month</option></select>
      </div>
      <div class="field"><label class="field__label" for="rp-category">Category</label><select class="select" id="rp-category" name="category"><option value="">All categories</option></select></div>
      <button class="btn btn--primary" type="submit">Apply</button>
    </form>
  </div>
</div>

<div data-report-summary data-loading-region aria-busy="true">${statSkeletons(4)}</div>

<div class="admin-grid-2">
  <div class="card">
    <div class="card__head"><h3 class="card__title">Sales over time</h3></div>
    <div class="card__body" data-report-chart data-loading-region aria-busy="true"><div class="stack" aria-hidden="true"><span class="sk" style="height:220px;border-radius:var(--radius-md)"></span></div></div>
  </div>
  <div class="card">
    <div class="card__head"><h3 class="card__title">Payment outcomes</h3></div>
    <div class="card__body" data-report-payments data-loading-region aria-busy="true">${tableSkeleton(5, 2)}</div>
  </div>
</div>

<div class="admin-grid-2">
  <div class="card">
    <div class="card__head"><h3 class="card__title">Sales by category</h3></div>
    <div class="card__body card__body--flush" data-report-categories data-loading-region aria-busy="true">${tableSkeleton(5, 3)}</div>
  </div>
  <div class="card">
    <div class="card__head"><h3 class="card__title">Order lifecycle</h3></div>
    <div class="card__body card__body--flush" data-report-lifecycle data-loading-region aria-busy="true">${tableSkeleton(5, 2)}</div>
  </div>
</div>

<div class="card">
  <div class="card__head"><h3 class="card__title">Best-selling products</h3></div>
  <div class="card__body card__body--flush" data-report-products data-loading-region aria-busy="true">${tableSkeleton(6, 4)}</div>
</div>`;

function settingsPage(id, title, sub, formId) {
  return `<div class="admin-page-head">
  <div class="admin-page-head__text">
    <h2 class="admin-page-head__title">${title}</h2>
    <p class="admin-page-head__sub">${sub}</p>
  </div>
</div>
<div class="card">
  <div class="card__body" data-admin-settings="${formId}" data-loading-region aria-busy="true">
    <div class="stack" aria-hidden="true">${Array.from({ length: 5 }, () => `<div class="stack stack--sm">${sk('sk--text-sm sk--w-25')}${sk('sk--input')}</div>`).join('')}${sk('sk--btn sk--w-20')}</div>
  </div>
</div>`;
}

const mediaBody = `<div class="admin-page-head">
  <div class="admin-page-head__text">
    <h2 class="admin-page-head__title">Media library</h2>
    <p class="admin-page-head__sub">Upload and organise imagery. Alt text is required so every published image is accessible and indexable.</p>
  </div>
  <div class="admin-page-head__actions">
    <button type="button" class="btn btn--primary" data-media-upload data-perm="media.create"><i data-icon="upload" data-size="sm"></i> Upload media</button>
  </div>
</div>
<div class="data-panel" data-admin-module="media">
  <div class="data-panel__toolbar">
    <div class="data-panel__search">
      <i data-icon="search" data-size="sm"></i>
      <label class="sr-only" for="media-search">Search media</label>
      <input class="input" id="media-search" type="search" placeholder="Search by filename or alt text" data-module-search>
    </div>
    <span class="data-panel__spacer"></span>
    <button type="button" class="btn btn--secondary btn--sm" data-module-refresh><i data-icon="refresh" data-size="sm"></i> Refresh</button>
  </div>
  <div class="card__body" data-media-grid data-loading-region aria-busy="true">
    <div class="image-picker" aria-hidden="true">${Array.from({ length: 12 }, () => sk('sk--square')).join('')}</div>
  </div>
  <div class="data-panel__foot">
    <p class="data-panel__count" data-module-count aria-live="polite"></p>
    <nav class="pagination" data-module-pagination aria-label="Media pagination"></nav>
  </div>
</div>`;

/* ============================================================================
   Registry
   ========================================================================== */

const TITLES = {
  dashboard: 'Dashboard', reports: 'Reports', settings: 'Business settings',
  homepage: 'Homepage management', content: 'Website content', seo: 'SEO settings', media: 'Media library',
};

export const adminPages = allModules.map((mod) => {
  const heading = TITLES[mod.id] || mod.label;
  let body;
  if (mod.id === 'dashboard') body = dashboardBody;
  else if (mod.id === 'reports') body = reportsBody;
  else if (mod.id === 'media') body = mediaBody;
  else if (mod.id === 'settings') body = settingsPage(mod.id, heading, 'Business identity, contact details, currency and storefront defaults.', 'business');
  else if (mod.id === 'homepage') body = settingsPage(mod.id, heading, 'Hero content, section visibility, trust items and promotional banners.', 'homepage');
  else if (mod.id === 'content') body = settingsPage(mod.id, heading, 'About page, policies, FAQs and footer content.', 'content');
  else if (mod.id === 'seo') body = settingsPage(mod.id, heading, 'Default metadata, social sharing, sitemap and indexing controls.', 'seo');
  else body = modulePage(mod, { description: DESCRIPTIONS[mod.id] || `Manage ${mod.label.toLowerCase()}.`, primaryAction: PRIMARY[mod.id] || null });

  const moduleName = ['dashboard', 'reports', 'media'].includes(mod.id)
    ? `/assets/js/admin/${mod.id}.js`
    : ['settings', 'homepage', 'content', 'seo'].includes(mod.id)
      ? '/assets/js/admin/settings.js'
      : '/assets/js/admin/module.js';

  return {
    file: `admin/${mod.id === 'dashboard' ? 'index' : mod.id}.html`,
    path: `/admin/${mod.id === 'dashboard' ? 'index' : mod.id}.html`,
    title: `${heading} — Starmond Admin`,
    description: `${heading} administration for Starmond Technology Limited.`,
    heading,
    adminId: mod.id,
    module: moduleName,
    jsonLd: [],
    body,
  };
});
