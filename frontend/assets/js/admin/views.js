/**
 * Administration views. Every list, figure and status in these views comes from
 * backend endpoints — there is no sample business data in this file.
 */
import { admin } from '../api.js';
import { session } from '../store.js';
import { toast } from '../ui/toast.js';
import { openModal } from '../ui/modal.js';
import {
  barChart, emptyRow, exportCsv, formModal, kpi, loadingRow, miniBarChart, panel, pagerBar,
  searchField, selectField, statusPill, table, thumb, toolbar, closeModal
} from './ui.js';
import { esc, formatDate, formatDateTime, money, qs, qsa } from '../utils.js';

const ORDER_STATUSES = [
  { value: 'pending_payment', label: 'Awaiting payment' },
  { value: 'paid', label: 'Paid' },
  { value: 'processing', label: 'Processing' },
  { value: 'shipped', label: 'Shipped' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'refunded', label: 'Refunded' }
];

function errorPanel(err) {
  return panel({
    body: `<div class="alert alert--error" role="alert"><div>
      <p><strong>This data could not be loaded.</strong></p>
      <p class="small">${esc(err?.message || 'Unexpected error.')}</p>
      <button class="btn btn--outline btn--sm" type="button" data-admin-retry>Try again</button>
    </div></div>`
  });
}

/* ============================================================== DASHBOARD */
export async function dashboard(root, ctx) {
  root.innerHTML = '<div class="admin-loading"><div class="skeleton skeleton--card"></div><div class="skeleton skeleton--card"></div></div>';
  try {
    const data = await admin.dashboard();
    const totals = data?.totals || data || {};
    const series = data?.sales_series || data?.series || [];
    const recent = data?.recent_orders || [];
    const lowStock = data?.low_stock || [];
    ctx.setSubtitle(`Live figures for ${formatDate(new Date())}`);

    root.innerHTML = `<div class="admin-section">
      <div class="kpi-grid">
        ${kpi({ label: 'Revenue (30 days)', value: money(totals.revenue_30d ?? totals.revenue ?? 0), hint: 'Verified payments only', brand: true })}
        ${kpi({ label: 'Orders (30 days)', value: String(totals.orders_30d ?? totals.orders ?? 0), hint: `${totals.pending_orders ?? 0} awaiting fulfilment` })}
        ${kpi({ label: 'Customers', value: String(totals.customers ?? 0), hint: `${totals.new_customers_30d ?? 0} new this month` })}
        ${kpi({ label: 'Awaiting payment', value: String(totals.pending_payments ?? 0), hint: 'Not yet verified' })}
        ${kpi({ label: 'Low stock items', value: String(lowStock.length || totals.low_stock || 0), hint: 'At or below reorder level' })}
      </div>

      <div class="admin-grid-2">
        ${panel({
          title: 'Sales',
          actions: '<button class="btn btn--ghost btn--sm" type="button" data-goto="reports">Full reports</button>',
          body: `${barChart(series.map((row) => ({ label: row.label || row.date, value: row.total ?? row.revenue ?? row.value ?? 0 })))}
            <div class="legend"><span class="legend__item"><span class="legend__swatch"></span>Verified revenue</span></div>`
        })}
        ${panel({
          title: 'Low stock',
          actions: '<button class="btn btn--ghost btn--sm" type="button" data-goto="inventory">Manage inventory</button>',
          flush: true,
          body: table({
            columns: [
              { key: 'name', label: 'Product', wrap: true, cell: (r) => `<strong>${esc(r.name || r.product_name || '')}</strong><br><span class="help-text">${esc(r.sku || '')}</span>` },
              { key: 'stock', label: 'In stock', num: true, cell: (r) => esc(r.stock_quantity ?? r.quantity ?? 0) },
              { key: 'threshold', label: 'Reorder at', num: true, cell: (r) => esc(r.reorder_level ?? r.threshold ?? '—') }
            ],
            rows: lowStock, emptyMessage: 'No low-stock items. Good.'
          })
        })}
      </div>

      ${panel({
        title: 'Recent orders',
        actions: '<button class="btn btn--ghost btn--sm" type="button" data-goto="orders">All orders</button>',
        flush: true,
        body: table({
          columns: [
            { key: 'number', label: 'Order', cell: (r) => `<strong>${esc(r.order_number || r.number || r.id)}</strong>` },
            { key: 'customer', label: 'Customer', wrap: true, cell: (r) => esc(r.customer_name || r.customer?.name || r.email || '—') },
            { key: 'date', label: 'Date', cell: (r) => formatDate(r.created_at) },
            { key: 'total', label: 'Total', num: true, cell: (r) => money(r.total ?? r.totals?.total ?? 0) },
            { key: 'status', label: 'Status', cell: (r) => statusPill(r.status) },
            { key: 'actions', label: 'Actions', num: true, cell: (r) => `<button class="btn btn--outline btn--sm" type="button" data-order="${esc(r.id)}">Open</button>` }
          ],
          rows: recent, emptyMessage: 'No orders yet.'
        })
      })}
    </div>`;

    qsa('[data-goto]', root).forEach((btn) => btn.addEventListener('click', () => ctx.navigate(btn.dataset.goto)));
    qsa('[data-order]', root).forEach((btn) => btn.addEventListener('click', () => ctx.navigate('orders', { open: btn.dataset.order })));
  } catch (err) {
    root.innerHTML = errorPanel(err);
    root.querySelector('[data-admin-retry]')?.addEventListener('click', () => dashboard(root, ctx));
  }
}

/* =============================================================== PRODUCTS */
export async function products(root, ctx) {
  let page = 1;
  let search = '';
  let category = '';
  let categories = [];

  try {
    categories = await admin.list('categories', { page_size: 200 }).then((p) => p.items).catch(() => []);
  } catch { categories = []; }

  const categoryOptions = [{ value: '', label: 'All categories' },
    ...categories.map((c) => ({ value: c.id, label: c.name }))];

  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Products',
      actions: `<button class="btn btn--primary btn--sm" type="button" data-new>Add product</button>`,
      flush: true,
      body: toolbar([
        searchField('products-search', 'Search by name, SKU or brand'),
        selectField('products-category', categoryOptions, { label: 'Category' }),
        '<input class="input" type="date" data-admin-filter id="products-from" aria-label="Updated from">',
        '<span class="toolbar__spacer"></span>',
        '<button class="btn btn--outline btn--sm" type="button" data-export>Export CSV</button>'
      ]),
      footer: '<span data-page-info class="help-text"></span><span class="admin-actions" data-pager></span>'
    })}
  </div>
  <div data-table-slot>${table({ columns: [], rows: [], loading: true })}</div>`;

  const slot = root.querySelector('[data-table-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pagerSlot = root.querySelector('[data-pager]');
  let lastRows = [];

  const columns = [
    { key: 'product', label: 'Product', wrap: true, cell: (r) => `<div class="cell-product">${thumb(r.primary_image || r.image, r.name)}
        <span><span class="cell-product__name">${esc(r.name)}</span><br><span class="cell-product__sku">${esc(r.sku || '—')}</span></span></div>` },
    { key: 'category', label: 'Category', cell: (r) => esc(r.category?.name || r.category_name || '—') },
    { key: 'price', label: 'Price', num: true, cell: (r) => money(r.price, r.currency) },
    { key: 'stock', label: 'Stock', num: true, cell: (r) => `<span class="pill ${Number(r.stock_quantity) <= 0 ? 'pill--danger' : Number(r.stock_quantity) <= 5 ? 'pill--warn' : 'pill--ok'}">${esc(r.stock_quantity ?? 0)}</span>` },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.is_active === false ? 'draft' : (r.is_published === false ? 'draft' : 'active')) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<div class="row-actions">
        <button class="btn btn--outline btn--sm" type="button" data-edit="${esc(r.id)}">Edit</button>
        <button class="btn btn--danger btn--sm" type="button" data-delete="${esc(r.id)}">Delete</button></div>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('products', {
        page, search: search || undefined, category: category || undefined, page_size: 20
      });
      lastRows = data.items;
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No products match those filters.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} products`;
      pagerSlot.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pagerSlot).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-edit]', slot).forEach((b) => b.addEventListener('click', () => editProduct(data.items.find((p) => String(p.id) === b.dataset.edit))));
      qsa('[data-delete]', slot).forEach((b) => b.addEventListener('click', async () => {
        const row = data.items.find((p) => String(p.id) === b.dataset.delete);
        if (!window.confirm(`Delete “${row?.name}”? This cannot be undone.`)) return;
        try { await admin.remove('products', b.dataset.delete); toast('Product deleted.', { type: 'success' }); load(); }
        catch (err) { toast(err.message, { type: 'error' }); }
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  function productFields() {
    return [
      { name: 'name', label: 'Product name', required: true, full: true },
      { name: 'sku', label: 'SKU', help: 'Internal stock code. Must be unique.' },
      { name: 'brand', label: 'Brand' },
      { name: 'category', label: 'Category', type: 'select', required: true,
        options: [{ value: '', label: 'Select a category' }, ...categories.map((c) => ({ value: c.id, label: c.name }))] },
      { name: 'price', label: 'Price (₦)', type: 'number', step: '0.01', required: true },
      { name: 'compare_at_price', label: 'Compare-at price (₦)', type: 'number', step: '0.01', help: 'Optional. Leave blank if not on promotion.' },
      { name: 'stock_quantity', label: 'Stock quantity', type: 'number', step: '1', required: true },
      { name: 'reorder_level', label: 'Reorder level', type: 'number', step: '1', help: 'Low-stock alerts trigger at or below this number.' },
      { name: 'image_url', label: 'Main image URL', full: true, help: 'Uploading image files is handled by the product media endpoint; a URL works for now.' },
      { name: 'short_description', label: 'Short description', type: 'textarea', rows: 2, full: true },
      { name: 'description', label: 'Full description', type: 'textarea', rows: 6, full: true },
      { name: 'is_active', label: 'Published (visible in the store)', type: 'checkbox' },
      { name: 'is_featured', label: 'Show in the featured rail on the homepage', type: 'checkbox' }
    ];
  }

  function editProduct(product) {
    formModal({
      title: product ? `Edit ${product.name}` : 'Add product',
      size: 'wide',
      fields: productFields(),
      values: product ? {
        name: product.name, sku: product.sku, brand: product.brand,
        category: product.category?.id ?? product.category, price: product.price,
        compare_at_price: product.compare_at_price, stock_quantity: product.stock_quantity,
        reorder_level: product.reorder_level, image_url: product.primary_image || product.image,
        short_description: product.short_description, description: product.description,
        is_active: product.is_active !== false, is_featured: Boolean(product.is_featured)
      } : { is_active: true },
      submitLabel: product ? 'Save changes' : 'Create product',
      onSubmit: async (values, { form }) => {
        const payload = {
          ...values,
          price: values.price === '' ? null : Number(values.price),
          compare_at_price: values.compare_at_price === '' ? null : Number(values.compare_at_price),
          stock_quantity: values.stock_quantity === '' ? 0 : Number(values.stock_quantity),
          reorder_level: values.reorder_level === '' ? null : Number(values.reorder_level)
        };
        if (product) {
          await admin.update('products', product.id, payload);
          toast('Product updated.', { type: 'success' });
        } else {
          await admin.create('products', payload);
          toast('Product created.', { type: 'success' });
        }
        load();
        return form;
      }
    });
  }

  root.querySelector('[data-new]').addEventListener('click', () => editProduct(null));
  root.querySelector('[data-export]').addEventListener('click', () => exportCsv('products.csv', [
    { label: 'Name', value: (r) => r.name },
    { label: 'SKU', value: (r) => r.sku },
    { label: 'Category', value: (r) => r.category?.name || '' },
    { label: 'Price', value: (r) => r.price },
    { label: 'Stock', value: (r) => r.stock_quantity },
    { label: 'Active', value: (r) => (r.is_active === false ? 'no' : 'yes') }
  ], lastRows));

  const searchEl = root.querySelector('[data-admin-search]');
  const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  searchEl?.addEventListener('input', debounce(() => { search = searchEl.value; page = 1; load(); }));
  root.querySelector('#products-category')?.addEventListener('change', (e) => { category = e.target.value; page = 1; load(); });

  load();
}

/* ============================================================= CATEGORIES */
export async function categories(root, ctx) {
  let lastRows = [];
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Categories',
      actions: '<button class="btn btn--primary btn--sm" type="button" data-new>Add category</button>',
      flush: true,
      body: '<div data-slot></div>'
    })}
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const columns = [
    { key: 'name', label: 'Category', wrap: true, cell: (r) => `<strong>${esc(r.name)}</strong><br><span class="help-text">/${esc(r.slug)}</span>` },
    { key: 'parent', label: 'Parent', cell: (r) => esc(r.parent?.name || '—') },
    { key: 'count', label: 'Products', num: true, cell: (r) => esc(r.product_count ?? r.products_count ?? 0) },
    { key: 'order', label: 'Order', num: true, cell: (r) => esc(r.display_order ?? r.order ?? '—') },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.is_active === false ? 'disabled' : 'active') },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<div class="row-actions">
        <button class="btn btn--outline btn--sm" type="button" data-edit="${esc(r.id)}">Edit</button>
        <button class="btn btn--danger btn--sm" type="button" data-delete="${esc(r.id)}">Delete</button></div>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('categories', { page_size: 100 });
      lastRows = data.items;
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No categories yet.' });
      qsa('[data-edit]', slot).forEach((b) => b.addEventListener('click', () => edit(data.items.find((c) => String(c.id) === b.dataset.edit))));
      qsa('[data-delete]', slot).forEach((b) => b.addEventListener('click', async () => {
        if (!window.confirm('Delete this category? Products must be moved first.')) return;
        try { await admin.remove('categories', b.dataset.delete); toast('Category deleted.', { type: 'success' }); load(); }
        catch (err) { toast(err.message, { type: 'error' }); }
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  function edit(category) {
    formModal({
      title: category ? `Edit ${category.name}` : 'Add category',
      fields: [
        { name: 'name', label: 'Name', required: true },
        { name: 'slug', label: 'Slug', help: 'Used in the category URL, e.g. /category/laptops-computing/' },
        { name: 'description', label: 'Description', type: 'textarea', rows: 3, full: true },
        { name: 'meta_title', label: 'SEO title', full: true },
        { name: 'meta_description', label: 'SEO description', type: 'textarea', rows: 2, full: true },
        { name: 'display_order', label: 'Display order', type: 'number', step: '1' },
        { name: 'is_active', label: 'Visible in navigation', type: 'checkbox' }
      ],
      values: category || { is_active: true },
      onSubmit: async (values) => {
        if (category) await admin.update('categories', category.id, values);
        else await admin.create('categories', values);
        toast('Category saved.', { type: 'success' });
        load();
      }
    });
  }

  root.querySelector('[data-new]').addEventListener('click', () => edit(null));
  load();
}

/* ============================================================== INVENTORY */
export async function inventory(root, ctx) {
  let page = 1;
  let search = '';
  let lowOnly = false;
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Inventory',
      flush: true,
      body: toolbar([
        searchField('inventory-search', 'Search products'),
        `<label class="sort-field"><span>Show</span><select class="input" data-admin-filter id="inventory-filter">
          <option value="">All stock</option><option value="low">Low stock only</option><option value="out">Out of stock</option>
        </select></label>`
      ]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
    <div data-slot></div>
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'product', label: 'Product', wrap: true, cell: (r) => `<strong>${esc(r.name || r.product_name || '')}</strong><br><span class="help-text">${esc(r.sku || '')}</span>` },
    { key: 'stock', label: 'In stock', num: true, cell: (r) => `<strong>${esc(r.stock_quantity ?? r.quantity ?? 0)}</strong>` },
    { key: 'reserved', label: 'Reserved', num: true, cell: (r) => esc(r.reserved_quantity ?? r.reserved ?? 0) },
    { key: 'reorder', label: 'Reorder at', num: true, cell: (r) => esc(r.reorder_level ?? '—') },
    { key: 'updated', label: 'Last movement', cell: (r) => formatDateTime(r.last_movement_at || r.updated_at) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<button class="btn btn--outline btn--sm" type="button" data-adjust="${esc(r.id)}">Adjust</button>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.inventory({ page, search: search || undefined, filter: lowOnly || undefined });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No inventory rows match.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} items`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-adjust]', slot).forEach((b) => b.addEventListener('click', () => {
        const row = data.items.find((r) => String(r.id) === b.dataset.adjust);
        adjust(row);
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  function adjust(row) {
    formModal({
      title: `Adjust stock — ${row.name || row.product_name || ''}`,
      note: `Current quantity: ${row.stock_quantity ?? row.quantity ?? 0}. Adjustments are written to the stock ledger with your staff account.`,
      fields: [
        { name: 'mode', label: 'Adjustment type', type: 'select', required: true, options: [
          { value: 'set', label: 'Set exact quantity' },
          { value: 'add', label: 'Add stock (received)' },
          { value: 'remove', label: 'Remove stock (damage, loss)' }
        ] },
        { name: 'quantity', label: 'Quantity', type: 'number', step: '1', required: true },
        { name: 'reason', label: 'Reason', type: 'textarea', rows: 2, full: true, required: true,
          help: 'Required for the audit trail, e.g. “Restock from supplier invoice 4421”.' }
      ],
      submitLabel: 'Apply adjustment',
      onSubmit: async (values) => {
        await admin.adjustStock(row.id, {
          mode: values.mode,
          quantity: Number(values.quantity),
          reason: values.reason
        });
        toast('Stock adjusted.', { type: 'success' });
        load();
      }
    });
  }

  const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  root.querySelector('[data-admin-search]')?.addEventListener('input', debounce((e) => { search = e.target.value; page = 1; load(); }));
  root.querySelector('#inventory-filter')?.addEventListener('change', (e) => { lowOnly = e.target.value; page = 1; load(); });
  load();
}

/* ================================================================== ORDERS */
export async function orders(root, ctx) {
  let page = 1;
  let status = '';
  let search = '';
  let lastRows = [];

  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Orders',
      flush: true,
      body: toolbar([
        searchField('orders-search', 'Search order number, name or email'),
        selectField('orders-status', [{ value: '', label: 'All statuses' }, ...ORDER_STATUSES], { label: 'Status' }),
        '<span class="toolbar__spacer"></span>',
        '<button class="btn btn--outline btn--sm" type="button" data-export>Export CSV</button>'
      ]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
    <div data-slot></div>
  </div>`;

  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'number', label: 'Order', cell: (r) => `<strong>${esc(r.order_number || r.id)}</strong><br><span class="help-text">${formatDate(r.created_at)}</span>` },
    { key: 'customer', label: 'Customer', wrap: true, cell: (r) => `${esc(r.customer_name || r.customer?.name || 'Guest')}<br><span class="help-text">${esc(r.email || r.customer?.email || '')}</span>` },
    { key: 'items', label: 'Items', num: true, cell: (r) => esc(r.item_count ?? (r.items || []).length) },
    { key: 'total', label: 'Total', num: true, cell: (r) => money(r.total ?? r.totals?.total ?? 0, r.currency) },
    { key: 'payment', label: 'Payment', cell: (r) => statusPill(r.payment_status || r.payment?.status || 'pending_payment') },
    { key: 'status', label: 'Fulfilment', cell: (r) => statusPill(r.status) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<button class="btn btn--outline btn--sm" type="button" data-open="${esc(r.id)}">Open</button>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('orders', { page, status: status || undefined, search: search || undefined, page_size: 20 });
      lastRows = data.items;
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No orders match those filters.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} orders`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-open]', slot).forEach((b) => b.addEventListener('click', () => openOrder(b.dataset.open, load)));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  root.querySelector('[data-admin-search]')?.addEventListener('input', debounce((e) => { search = e.target.value; page = 1; load(); }));
  root.querySelector('#orders-status')?.addEventListener('change', (e) => { status = e.target.value; page = 1; load(); });
  root.querySelector('[data-export]')?.addEventListener('click', () => exportCsv('orders.csv', [
    { label: 'Order', value: (r) => r.order_number },
    { label: 'Date', value: (r) => r.created_at },
    { label: 'Customer', value: (r) => r.customer_name || r.customer?.name || '' },
    { label: 'Email', value: (r) => r.email || '' },
    { label: 'Total', value: (r) => r.total ?? '' },
    { label: 'Payment', value: (r) => r.payment_status || '' },
    { label: 'Status', value: (r) => r.status || '' }
  ], lastRows));

  load();

  if (ctx.options?.open) openOrder(ctx.options.open, load);
}

async function openOrder(id, refresh) {
  try {
    const order = await admin.get('orders', id);
    const items = order.items || order.line_items || [];
    const address = order.shipping_address || {};
    const payment = order.payment || {};
    const body = `
      <div class="detail-grid">
        <div class="detail-block"><h4>Customer</h4><p>${esc(order.customer_name || order.customer?.name || 'Guest')}<br>${esc(order.email || '')}<br>${esc(order.phone || '')}</p></div>
        <div class="detail-block"><h4>Payment</h4><p>${statusPill(order.payment_status || payment.status || 'pending_payment')}<br>
          ${esc(payment.reference || order.payment_reference || 'No reference')}<br>
          <span class="help-text">${money(order.total ?? order.totals?.total ?? 0)}</span></p></div>
        <div class="detail-block"><h4>Delivery</h4><address>${[address.first_name, address.last_name, address.line1, address.line2, address.area, address.city, address.state].filter(Boolean).map(esc).join('<br>') || 'No address recorded'}</address></div>
      </div>
      <h3 class="form-section__title" style="margin-top:1rem">Items</h3>
      ${table({
        columns: [
          { key: 'name', label: 'Item', wrap: true, cell: (r) => `${esc(r.product?.name || r.name || '')}<br><span class="help-text">${esc(r.variant?.name || '')}</span>` },
          { key: 'qty', label: 'Qty', num: true, cell: (r) => esc(r.quantity) },
          { key: 'unit', label: 'Unit price', num: true, cell: (r) => money(r.unit_price ?? r.price ?? 0) },
          { key: 'total', label: 'Line total', num: true, cell: (r) => money(r.line_total ?? 0) }
        ],
        rows: items, emptyMessage: 'No items recorded.'
      })}
      <div class="detail-grid" style="margin-top:1rem">
        <div class="detail-block"><h4>Order totals</h4><p>Subtotal ${money(order.subtotal ?? order.totals?.subtotal ?? 0)}<br>
          Discount ${money(order.discount_total ?? 0)}<br>Delivery ${money(order.shipping_total ?? order.totals?.shipping ?? 0)}<br>
          <strong>Total ${money(order.total ?? order.totals?.total ?? 0)}</strong></p></div>
        <div class="detail-block"><h4>Notes</h4><p>${esc(order.delivery_notes || order.notes || '—')}</p></div>
        <div class="detail-block"><h4>Timeline</h4><p>${(order.status_history || []).map((h) => `${esc(h.status)} · ${formatDateTime(h.created_at)}`).join('<br>') || formatDate(order.created_at)}</p></div>
      </div>
      <div class="form-section" style="margin-top:1rem">
        <h3 class="form-section__title">Change fulfilment status</h3>
        <div class="admin-actions">
          <label class="sr-only" for="order-status-select">New status</label>
          <select class="input" id="order-status-select">
            ${ORDER_STATUSES.map((s) => `<option value="${s.value}"${String(order.status) === s.value ? ' selected' : ''}>${s.label}</option>`).join('')}
          </select>
          <input class="input" type="text" id="order-status-note" placeholder="Internal note (optional)">
          <button class="btn btn--primary" type="button" data-status-apply>Update status</button>
        </div>
        <p class="help-text">Customers are notified automatically for shipped and delivered updates, subject to their notification preferences.</p>
      </div>`;

    openModal({
      title: `Order ${order.order_number || order.id}`,
      size: 'wide',
      body,
      footer: `<button class="btn btn--ghost" type="button" data-modal-close>Close</button>
        <button class="btn btn--danger" type="button" data-cancel-order>Cancel order</button>`,
      onMount: ({ body: bodyEl, footer }) => {
        bodyEl.querySelector('[data-status-apply]')?.addEventListener('click', async (event) => {
          const status = bodyEl.querySelector('#order-status-select').value;
          const note = bodyEl.querySelector('#order-status-note').value;
          const btn = event.currentTarget;
          btn.disabled = true;
          try {
            await admin.orderStatus(order.id, status, note);
            toast(`Order marked ${status.replace(/_/g, ' ')}.`, { type: 'success' });
            closeModal();
            refresh?.();
          } catch (err) {
            toast(err.message, { type: 'error' });
            btn.disabled = false;
          }
        });
        footer.querySelector('[data-cancel-order]')?.addEventListener('click', async () => {
          if (!window.confirm('Cancel this order and release its stock?')) return;
          try {
            await admin.orderStatus(order.id, 'cancelled', 'Cancelled by staff');
            toast('Order cancelled.', { type: 'info' });
            closeModal();
            refresh?.();
          } catch (err) { toast(err.message, { type: 'error' }); }
        });
      }
    });
  } catch (err) {
    toast(err.message, { type: 'error' });
  }
}

/* ================================================================ PAYMENTS */
export async function payments(root, ctx) {
  let page = 1;
  let status = '';
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Payments',
      flush: true,
      body: toolbar([
        selectField('payments-status', [{ value: '', label: 'All payments' },
          { value: 'success', label: 'Successful' },
          { value: 'pending', label: 'Pending' },
          { value: 'failed', label: 'Failed' }], { label: 'Status' })
      ]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
    <div data-slot></div>
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'reference', label: 'Reference', cell: (r) => `<span class="mono-cell">${esc(r.reference || r.gateway_reference || '—')}</span>` },
    { key: 'order', label: 'Order', cell: (r) => esc(r.order_number || r.order?.order_number || r.order_id || '—') },
    { key: 'amount', label: 'Amount', num: true, cell: (r) => money(r.amount ?? 0, r.currency) },
    { key: 'channel', label: 'Channel', cell: (r) => esc(r.channel || r.payment_method || '—') },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.status) },
    { key: 'paid_at', label: 'Paid', cell: (r) => formatDateTime(r.paid_at || r.verified_at) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => (String(r.status).toLowerCase() === 'success' ? '' : `<button class="btn btn--outline btn--sm" type="button" data-verify="${esc(r.id)}">Verify</button>`) }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('payments', { page, status: status || undefined, page_size: 20 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No payments recorded.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} payments`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-verify]', slot).forEach((b) => b.addEventListener('click', async () => {
        b.disabled = true;
        try {
          await admin.verifyPayment(b.dataset.verify);
          toast('Payment re-verified with Paystack.', { type: 'success' });
          load();
        } catch (err) { toast(err.message, { type: 'error' }); b.disabled = false; }
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  root.querySelector('#payments-status')?.addEventListener('change', (e) => { status = e.target.value; page = 1; load(); });
  load();
}

/* ================================================================= REFUNDS */
export async function refunds(root, ctx) {
  let page = 1;
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Refunds',
      actions: '<button class="btn btn--primary btn--sm" type="button" data-new>Record refund</button>',
      flush: true,
      body: '<div data-slot></div>',
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'order', label: 'Order', cell: (r) => esc(r.order_number || r.order?.order_number || '—') },
    { key: 'amount', label: 'Amount', num: true, cell: (r) => money(r.amount ?? 0) },
    { key: 'reason', label: 'Reason', wrap: true, cell: (r) => esc(r.reason || '—') },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.status) },
    { key: 'created', label: 'Requested', cell: (r) => formatDateTime(r.created_at) },
    { key: 'processed', label: 'Processed', cell: (r) => formatDateTime(r.processed_at) }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.refunds({ page, page_size: 20 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No refunds recorded.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} refunds`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  root.querySelector('[data-new]')?.addEventListener('click', () => {
    formModal({
      title: 'Record a refund',
      note: 'Refunds are executed through Paystack by the backend. Never mark a refund complete manually.',
      fields: [
        { name: 'order_number', label: 'Order number', required: true },
        { name: 'amount', label: 'Amount (₦)', type: 'number', step: '0.01', required: true },
        { name: 'reason', label: 'Reason', type: 'textarea', rows: 3, required: true, full: true },
        { name: 'notify_customer', label: 'Notify the customer by email', type: 'checkbox' }
      ],
      submitLabel: 'Submit refund request',
      onSubmit: async (values) => {
        await admin.createRefund(values);
        toast('Refund request created.', { type: 'success' });
        load();
      }
    });
  });

  load();
}

/* ================================================================= REPORTS */
export async function reports(root, ctx) {
  const today = new Date();
  const start = new Date(today.getTime() - 29 * 86400000).toISOString().slice(0, 10);
  const end = today.toISOString().slice(0, 10);

  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Reports',
      actions: `<label class="sort-field"><span>From</span><input class="input" type="date" id="report-start" value="${start}"></label>
        <label class="sort-field"><span>To</span><input class="input" type="date" id="report-end" value="${end}"></label>
        <button class="btn btn--primary btn--sm" type="button" data-run>Run report</button>`,
      body: '<div data-slot><p class="help-text">Choose a period and run the report.</p></div>'
    })}
  </div>`;
  const slot = root.querySelector('[data-slot]');
  let last = null;

  async function run() {
    slot.innerHTML = '<div class="skeleton skeleton--card"></div>';
    try {
      const data = await admin.reports({
        start: root.querySelector('#report-start').value,
        end: root.querySelector('#report-end').value
      });
      last = data;
      const summary = data.summary || data;
      const series = data.series || data.sales_series || [];
      const byCategory = data.by_category || data.categories || [];
      const topProducts = data.top_products || [];
      slot.innerHTML = `
        <div class="kpi-grid" style="margin-bottom:1rem">
          ${kpi({ label: 'Revenue', value: money(summary.revenue ?? 0), hint: 'Verified payments', brand: true })}
          ${kpi({ label: 'Orders', value: String(summary.orders ?? 0), hint: `${summary.units ?? 0} units` })}
          ${kpi({ label: 'Average order value', value: money(summary.average_order_value ?? summary.aov ?? 0) })}
          ${kpi({ label: 'Refunds', value: money(summary.refunds ?? 0) })}
          ${kpi({ label: 'Discounts given', value: money(summary.discounts ?? 0) })}
        </div>
        <div class="admin-grid-2">
          ${panel({ title: 'Revenue over time', body: barChart(series.map((r) => ({ label: r.label || r.date, value: r.total ?? r.revenue ?? 0 }))) })}
          ${panel({ title: 'Revenue by category', body: miniBarChart(byCategory.map((r) => ({ label: r.category || r.name, value: r.revenue ?? r.total ?? 0 }))) })}
        </div>
        ${panel({
          title: 'Best sellers',
          flush: true,
          actions: '<button class="btn btn--outline btn--sm" type="button" data-export>Export CSV</button>',
          body: table({
            columns: [
              { key: 'name', label: 'Product', wrap: true, cell: (r) => `<strong>${esc(r.name || r.product_name)}</strong><br><span class="help-text">${esc(r.sku || '')}</span>` },
              { key: 'units', label: 'Units sold', num: true, cell: (r) => esc(r.units ?? r.quantity ?? 0) },
              { key: 'revenue', label: 'Revenue', num: true, cell: (r) => money(r.revenue ?? r.total ?? 0) }
            ],
            rows: topProducts, emptyMessage: 'No sales in this period.'
          })
        })}`;
      slot.querySelector('[data-export]')?.addEventListener('click', () => exportCsv('best-sellers.csv', [
        { label: 'Product', value: (r) => r.name || r.product_name },
        { label: 'SKU', value: (r) => r.sku || '' },
        { label: 'Units', value: (r) => r.units ?? r.quantity ?? 0 },
        { label: 'Revenue', value: (r) => r.revenue ?? r.total ?? 0 }
      ], topProducts));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', run);
    }
  }

  root.querySelector('[data-run]')?.addEventListener('click', run);
  run();
}

/* =============================================================== CUSTOMERS */
export async function customers(root, ctx) {
  let page = 1;
  let search = '';
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Customers',
      flush: true,
      body: toolbar([searchField('customers-search', 'Search name, email or phone')]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
    <div data-slot></div>
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'name', label: 'Customer', wrap: true, cell: (r) => `<strong>${esc([r.first_name, r.last_name].filter(Boolean).join(' ') || r.name || 'Guest')}</strong><br><span class="help-text">${esc(r.email || '')}</span>` },
    { key: 'phone', label: 'Phone', cell: (r) => esc(r.phone || '—') },
    { key: 'orders', label: 'Orders', num: true, cell: (r) => esc(r.order_count ?? r.orders ?? 0) },
    { key: 'spend', label: 'Lifetime value', num: true, cell: (r) => money(r.total_spent ?? r.lifetime_value ?? 0) },
    { key: 'joined', label: 'Joined', cell: (r) => formatDate(r.date_joined || r.created_at) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<button class="btn btn--outline btn--sm" type="button" data-view="${esc(r.id)}">View</button>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('customers', { page, search: search || undefined, page_size: 20 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No customers yet.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} customers`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-view]', slot).forEach((b) => b.addEventListener('click', async () => {
        try {
          const customer = await admin.customer(b.dataset.view);
          const ordersList = customer.orders || [];
          const body = `<div class="detail-grid">
              <div class="detail-block"><h4>Contact</h4><p>${esc(customer.email || '')}<br>${esc(customer.phone || '')}</p></div>
              <div class="detail-block"><h4>Summary</h4><p>${esc(customer.order_count ?? ordersList.length)} orders<br>${money(customer.total_spent ?? 0)} lifetime</p></div>
              <div class="detail-block"><h4>Addresses</h4><p>${(customer.addresses || []).map((a) => esc([a.line1, a.city, a.state].filter(Boolean).join(', '))).join('<br>') || 'None saved'}</p></div>
            </div>
            <h3 class="form-section__title" style="margin-top:1rem">Orders</h3>
            ${table({
              columns: [
                { key: 'order', label: 'Order', cell: (r) => esc(r.order_number || r.id) },
                { key: 'date', label: 'Date', cell: (r) => formatDate(r.created_at) },
                { key: 'total', label: 'Total', num: true, cell: (r) => money(r.total ?? 0) },
                { key: 'status', label: 'Status', cell: (r) => statusPill(r.status) }
              ], rows: ordersList, emptyMessage: 'No orders yet.'
            })}`;
          openModal({
            title: [customer.first_name, customer.last_name].filter(Boolean).join(' ') || 'Customer',
            size: 'wide',
            body,
            footer: '<button class="btn btn--ghost" type="button" data-modal-close>Close</button>'
          });
        } catch (err) { toast(err.message, { type: 'error' }); }
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  root.querySelector('[data-admin-search]')?.addEventListener('input', debounce((e) => { search = e.target.value; page = 1; load(); }));
  load();
}

/* ================================================================= REVIEWS */
export async function reviews(root, ctx) {
  let page = 1;
  let status = 'pending';
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Product reviews',
      flush: true,
      body: toolbar([
        selectField('reviews-status', [
          { value: 'pending', label: 'Awaiting moderation' },
          { value: 'approved', label: 'Published' },
          { value: 'rejected', label: 'Rejected' },
          { value: '', label: 'All reviews' }
        ], { label: 'Status', value: 'pending' })
      ]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
    <div data-slot></div>
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'product', label: 'Product', wrap: true, cell: (r) => esc(r.product?.name || r.product_name || '—') },
    { key: 'rating', label: 'Rating', num: true, cell: (r) => `${esc(r.rating)}/5` },
    { key: 'review', label: 'Review', wrap: true, cell: (r) => `<strong>${esc(r.title || '')}</strong><br><span class="help-text">${esc((r.body || r.comment || '').slice(0, 140))}</span>` },
    { key: 'customer', label: 'Customer', cell: (r) => esc(r.customer_name || r.author_name || '—') },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.status || (r.is_approved ? 'approved' : 'pending')) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<div class="row-actions">
        <button class="btn btn--outline btn--sm" type="button" data-approve="${esc(r.id)}">Approve</button>
        <button class="btn btn--danger btn--sm" type="button" data-reject="${esc(r.id)}">Reject</button></div>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('reviews', { page, status: status || undefined, page_size: 20 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No reviews in this queue.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} reviews`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      const act = (id, action) => async (event) => {
        event.currentTarget.disabled = true;
        try {
          await admin.action('reviews', id, action);
          toast(`Review ${action === 'approve' ? 'published' : 'rejected'}.`, { type: 'success' });
          load();
        } catch (err) { toast(err.message, { type: 'error' }); event.currentTarget.disabled = false; }
      };
      qsa('[data-approve]', slot).forEach((b) => b.addEventListener('click', act(b.dataset.approve, 'approve')));
      qsa('[data-reject]', slot).forEach((b) => b.addEventListener('click', act(b.dataset.reject, 'reject')));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  root.querySelector('#reviews-status')?.addEventListener('change', (e) => { status = e.target.value; page = 1; load(); });
  load();
}

/* =============================================================== DISCOUNTS */
export async function discounts(root, ctx) {
  let page = 1;
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Discounts and promotions',
      actions: '<button class="btn btn--primary btn--sm" type="button" data-new>Create discount</button>',
      flush: true,
      body: '<div data-slot></div>',
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>'
    })}
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');

  const columns = [
    { key: 'code', label: 'Code', cell: (r) => `<span class="mono-cell">${esc(r.code)}</span>` },
    { key: 'type', label: 'Type', cell: (r) => (String(r.type || r.discount_type) === 'percentage' ? `${esc(r.value)}%` : money(r.value)) },
    { key: 'min', label: 'Minimum spend', num: true, cell: (r) => (r.minimum_order_amount ? money(r.minimum_order_amount) : '—') },
    { key: 'window', label: 'Valid', cell: (r) => `${formatDate(r.starts_at)} → ${formatDate(r.ends_at)}` },
    { key: 'usage', label: 'Used', num: true, cell: (r) => `${esc(r.usage_count ?? 0)}${r.usage_limit ? ` / ${esc(r.usage_limit)}` : ''}` },
    { key: 'status', label: 'Status', cell: (r) => statusPill(r.is_active === false ? 'disabled' : 'active') },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<div class="row-actions">
        <button class="btn btn--outline btn--sm" type="button" data-edit="${esc(r.id)}">Edit</button>
        <button class="btn btn--danger btn--sm" type="button" data-delete="${esc(r.id)}">Delete</button></div>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('discounts', { page, page_size: 20 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No discount codes yet.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} codes`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-edit]', slot).forEach((b) => b.addEventListener('click', () => edit(data.items.find((d) => String(d.id) === b.dataset.edit))));
      qsa('[data-delete]', slot).forEach((b) => b.addEventListener('click', async () => {
        if (!window.confirm('Delete this discount code?')) return;
        try { await admin.remove('discounts', b.dataset.delete); toast('Discount deleted.', { type: 'success' }); load(); }
        catch (err) { toast(err.message, { type: 'error' }); }
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  function edit(discount) {
    formModal({
      title: discount ? `Edit ${discount.code}` : 'Create discount',
      fields: [
        { name: 'code', label: 'Code', required: true, help: 'Customers type this at checkout.' },
        { name: 'type', label: 'Type', type: 'select', required: true, options: [
          { value: 'percentage', label: 'Percentage off' }, { value: 'fixed', label: 'Fixed amount off' }
        ] },
        { name: 'value', label: 'Value', type: 'number', step: '0.01', required: true },
        { name: 'minimum_order_amount', label: 'Minimum spend (₦)', type: 'number', step: '0.01' },
        { name: 'usage_limit', label: 'Total uses allowed', type: 'number', step: '1', help: 'Leave blank for unlimited.' },
        { name: 'starts_at', label: 'Starts', type: 'date' },
        { name: 'ends_at', label: 'Ends', type: 'date' },
        { name: 'is_active', label: 'Active', type: 'checkbox', full: true }
      ],
      values: discount || { type: 'percentage', is_active: true },
      onSubmit: async (values) => {
        if (discount) await admin.update('discounts', discount.id, values);
        else await admin.create('discounts', values);
        toast('Discount saved.', { type: 'success' });
        load();
      }
    });
  }

  root.querySelector('[data-new]')?.addEventListener('click', () => edit(null));
  load();
}

/* =========================================================== NOTIFICATIONS */
export async function notifications(root, ctx) {
  let page = 1;
  root.innerHTML = `<div class="admin-section">
    ${panel({
      title: 'Send a notification',
      body: `<form class="admin-form" data-notify-form novalidate>
        <div class="form-grid">
          <div class="field"><label for="nt-audience">Audience</label>
            <select class="input" id="nt-audience" name="audience">
              <option value="all_customers">All customers</option>
              <option value="order_customers">Customers with orders</option>
              <option value="single">One customer</option>
            </select></div>
          <div class="field"><label for="nt-email">Customer email (single audience only)</label>
            <input class="input" id="nt-email" name="email" type="email" autocomplete="off"></div>
          <div class="field field--full"><label for="nt-title">Title</label>
            <input class="input" id="nt-title" name="title" type="text" required maxlength="120"></div>
          <div class="field field--full"><label for="nt-body">Message</label>
            <textarea class="input" id="nt-body" name="body" rows="4" required maxlength="2000"></textarea></div>
          <label class="check field--full"><input type="checkbox" name="send_email"><span>Also send by email</span></label>
        </div>
        <p class="form-error" data-notify-error role="alert" hidden></p>
        <button class="btn btn--primary" type="submit">Send notification</button>
      </form>`
    })}
    ${panel({ title: 'Recently sent', flush: true, body: '<div data-slot></div>',
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>' })}
  </div>`;

  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');
  const form = root.querySelector('[data-notify-form]');

  const columns = [
    { key: 'title', label: 'Title', wrap: true, cell: (r) => `<strong>${esc(r.title)}</strong><br><span class="help-text">${esc((r.message || r.body || '').slice(0, 110))}</span>` },
    { key: 'audience', label: 'Audience', cell: (r) => esc((r.audience || '—').replace(/_/g, ' ')) },
    { key: 'sent', label: 'Sent', cell: (r) => formatDateTime(r.sent_at || r.created_at) },
    { key: 'recipients', label: 'Recipients', num: true, cell: (r) => esc(r.recipient_count ?? r.recipients ?? '—') }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.list('notifications', { page, page_size: 15 });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No notifications sent yet.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} notifications`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = form.querySelector('[data-notify-error]');
    errorEl.hidden = true;
    const data = new FormData(form);
    const button = form.querySelector('button[type="submit"]');
    const payload = {
      audience: data.get('audience'),
      email: data.get('email') || undefined,
      title: data.get('title'),
      message: data.get('body'),
      send_email: data.get('send_email') === 'on'
    };
    if (!String(payload.title || '').trim() || !String(payload.message || '').trim()) {
      errorEl.textContent = 'A title and message are required.';
      errorEl.hidden = false;
      return;
    }
    button.disabled = true;
    try {
      await admin.sendNotification(payload);
      toast('Notification queued.', { type: 'success' });
      form.reset();
      load();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    } finally {
      button.disabled = false;
    }
  });

  load();
}

/* ================================================================ CONTENT */
export async function content(root, ctx) {
  root.innerHTML = `<div class="admin-section">
    ${panel({ title: 'Site content', flush: true,
      body: toolbar([searchField('content-search', 'Search content keys')]),
      footer: '<span class="help-text" data-page-info></span><span class="admin-actions" data-pager></span>' })}
    <div data-slot></div>
  </div>`;
  const slot = root.querySelector('[data-slot]');
  const pageInfo = root.querySelector('[data-page-info]');
  const pager = root.querySelector('[data-pager]');
  let page = 1;
  let search = '';

  const columns = [
    { key: 'key', label: 'Key', cell: (r) => `<span class="mono-cell">${esc(r.key || r.slug || '')}</span>` },
    { key: 'title', label: 'Title', wrap: true, cell: (r) => `<strong>${esc(r.title || '')}</strong><br><span class="help-text">${esc((r.body || r.content || '').slice(0, 90))}</span>` },
    { key: 'updated', label: 'Updated', cell: (r) => formatDateTime(r.updated_at) },
    { key: 'actions', label: 'Actions', num: true, cell: (r) => `<button class="btn btn--outline btn--sm" type="button" data-edit="${esc(r.id)}">Edit</button>` }
  ];

  async function load() {
    slot.innerHTML = table({ columns, rows: [], loading: true });
    try {
      const data = await admin.content({ page, search: search || undefined });
      slot.innerHTML = table({ columns, rows: data.items, emptyMessage: 'No editable content blocks registered.' });
      pageInfo.textContent = `Page ${data.page} of ${data.pages} · ${data.count} blocks`;
      pager.innerHTML = `<button class="btn btn--outline btn--sm" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn--outline btn--sm" type="button" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next</button>`;
      qsa('[data-page]', pager).forEach((b) => b.addEventListener('click', () => { page = Number(b.dataset.page); load(); }));
      qsa('[data-edit]', slot).forEach((b) => b.addEventListener('click', () => {
        const row = data.items.find((c) => String(c.id) === b.dataset.edit);
        formModal({
          title: `Edit ${row.key || row.title}`,
          fields: [
            { name: 'title', label: 'Title', full: true },
            { name: 'subtitle', label: 'Subtitle', full: true },
            { name: 'body', label: 'Body', type: 'textarea', rows: 8, full: true },
            { name: 'cta_label', label: 'Button label' },
            { name: 'cta_url', label: 'Button URL' },
            { name: 'is_active', label: 'Visible on the site', type: 'checkbox', full: true }
          ],
          values: row,
          onSubmit: async (values) => {
            await admin.updateContent(row.id, values);
            toast('Content updated.', { type: 'success' });
            load();
          }
        });
      }));
    } catch (err) {
      slot.innerHTML = errorPanel(err);
      slot.querySelector('[data-admin-retry]')?.addEventListener('click', load);
    }
  }

  const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  root.querySelector('[data-admin-search]')?.addEventListener('input', debounce((e) => { search = e.target.value; page = 1; load(); }));
  load();
}

/* ==================================================================== SEO */
export async function seo(root, ctx) {
  root.innerHTML = '<div class="admin-loading"><div class="skeleton skeleton--card"></div></div>';
  try {
    const data = await admin.seo();
    const pages = data.pages || data.overrides || [];
    root.innerHTML = `<div class="admin-section">
      ${panel({
        title: 'Default search metadata',
        body: `<form class="admin-form" data-seo-form>
          <div class="form-grid">
            <div class="field field--full"><label for="seo-title">Default title suffix</label>
              <input class="input" id="seo-title" name="default_title" type="text" value="${esc(data.default_title || '')}"></div>
            <div class="field field--full"><label for="seo-desc">Default meta description</label>
              <textarea class="input" id="seo-desc" name="default_description" rows="3">${esc(data.default_description || '')}</textarea></div>
            <div class="field"><label for="seo-og">Default share image URL</label>
              <input class="input" id="seo-og" name="default_og_image" type="text" value="${esc(data.default_og_image || '')}"></div>
            <div class="field"><label for="seo-robots">robots.txt policy</label>
              <select class="input" id="seo-robots" name="robots_policy">
                <option value="index">Allow indexing (index, follow)</option>
                <option value="noindex">Discourage indexing (noindex) — staging only</option>
              </select></div>
            <div class="field"><label for="seo-ga">Google Analytics / Tag ID</label>
              <input class="input" id="seo-ga" name="analytics_id" type="text" value="${esc(data.analytics_id || '')}"></div>
            <div class="field"><label for="seo-gsc">Search Console verification token</label>
              <input class="input" id="seo-gsc" name="search_console_verification" type="text" value="${esc(data.search_console_verification || '')}"></div>
          </div>
          <p class="help-text">Sitemaps are generated by the backend: /sitemap.xml, /sitemap-products.xml and /sitemap-categories.xml are declared in robots.txt.</p>
          <p class="form-success" data-seo-success role="status" hidden>SEO settings saved.</p>
          <button class="btn btn--primary" type="submit">Save SEO settings</button>
        </form>`
      })}
      ${panel({
        title: 'Per-page overrides',
        flush: true,
        body: table({
          columns: [
            { key: 'path', label: 'Path', cell: (r) => `<span class="mono-cell">${esc(r.path || r.url)}</span>` },
            { key: 'title', label: 'Title', wrap: true, cell: (r) => esc(r.title || '—') },
            { key: 'desc', label: 'Description', wrap: true, cell: (r) => esc((r.description || '').slice(0, 120)) },
            { key: 'robots', label: 'Robots', cell: (r) => esc(r.robots || 'index, follow') }
          ],
          rows: pages, emptyMessage: 'No per-page overrides. Pages use the static metadata built into them.'
        })
      })}
    </div>`;

    root.querySelector('[data-seo-form]')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const values = Object.fromEntries(new FormData(form).entries());
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        await admin.updateSeo(values);
        const ok = form.querySelector('[data-seo-success]');
        ok.hidden = false;
        setTimeout(() => { ok.hidden = true; }, 4000);
        toast('SEO settings saved.', { type: 'success' });
      } catch (err) {
        toast(err.message, { type: 'error' });
      } finally { btn.disabled = false; }
    });
  } catch (err) {
    root.innerHTML = errorPanel(err);
    root.querySelector('[data-admin-retry]')?.addEventListener('click', () => seo(root, ctx));
  }
}

/* =============================================================== SETTINGS */
export async function settings(root, ctx) {
  root.innerHTML = '<div class="admin-loading"><div class="skeleton skeleton--card"></div></div>';
  try {
    const data = await admin.settings();
    root.innerHTML = `<div class="admin-section">
      ${panel({
        title: 'Business settings',
        body: `<form class="admin-form" data-settings-form>
          <div class="form-section">
            <h3 class="form-section__title">Business</h3>
            <div class="form-grid">
              <div class="field"><label for="st-name">Business name</label><input class="input" id="st-name" name="business_name" type="text" value="${esc(data.business_name || 'STARMOND TECHNOLOGY LIMITED')}"></div>
              <div class="field"><label for="st-email">Support email</label><input class="input" id="st-email" name="support_email" type="email" value="${esc(data.support_email || '')}"></div>
              <div class="field"><label for="st-phone">Support phone</label><input class="input" id="st-phone" name="support_phone" type="tel" value="${esc(data.support_phone || '')}"></div>
              <div class="field"><label for="st-currency">Currency</label><input class="input" id="st-currency" name="currency" type="text" value="${esc(data.currency || 'NGN')}"></div>
            </div>
          </div>
          <div class="form-section">
            <h3 class="form-section__title">Checkout and delivery</h3>
            <div class="form-grid">
              <div class="field"><label for="st-free">Free delivery threshold (₦)</label><input class="input" id="st-free" name="free_shipping_threshold" type="number" step="100" value="${esc(data.free_shipping_threshold ?? '')}"></div>
              <div class="field"><label for="st-tax">VAT rate (%)</label><input class="input" id="st-tax" name="tax_rate" type="number" step="0.01" value="${esc(data.tax_rate ?? '')}"></div>
              <div class="field"><label for="st-low">Low stock threshold</label><input class="input" id="st-low" name="low_stock_threshold" type="number" step="1" value="${esc(data.low_stock_threshold ?? 5)}"></div>
              <div class="field"><label for="st-prefix">Order number prefix</label><input class="input" id="st-prefix" name="order_prefix" type="text" value="${esc(data.order_prefix || 'STM')}"></div>
            </div>
          </div>
          <div class="form-section">
            <h3 class="form-section__title">Payments</h3>
            <p class="help-text">Paystack secret keys are configured on the backend only and are never present in the frontend.</p>
            <div class="form-grid">
              <div class="field"><label for="st-paystack-mode">Paystack mode</label>
                <select class="input" id="st-paystack-mode" name="paystack_mode">
                  <option value="test"${data.paystack_mode === 'test' ? ' selected' : ''}>Test</option>
                  <option value="live"${data.paystack_mode === 'live' ? ' selected' : ''}>Live</option>
                </select></div>
              <label class="check field--full"><input type="checkbox" name="maintenance_mode" ${data.maintenance_mode ? 'checked' : ''}><span>Maintenance mode (storefront shows a notice and blocks checkout)</span></label>
            </div>
          </div>
          <p class="form-error" data-settings-error role="alert" hidden></p>
          <button class="btn btn--primary" type="submit">Save settings</button>
        </form>`
      })}
    </div>`;

    root.querySelector('[data-settings-form]')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const raw = Object.fromEntries(new FormData(form).entries());
      const payload = {
        ...raw,
        maintenance_mode: raw.maintenance_mode === 'on',
        free_shipping_threshold: raw.free_shipping_threshold === '' ? null : Number(raw.free_shipping_threshold),
        tax_rate: raw.tax_rate === '' ? null : Number(raw.tax_rate),
        low_stock_threshold: raw.low_stock_threshold === '' ? null : Number(raw.low_stock_threshold)
      };
      const btn = form.querySelector('button[type="submit"]');
      const errorEl = form.querySelector('[data-settings-error]');
      btn.disabled = true;
      errorEl.hidden = true;
      try {
        await admin.updateSettings(payload);
        toast('Settings saved.', { type: 'success' });
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.hidden = false;
      } finally { btn.disabled = false; }
    });
  } catch (err) {
    root.innerHTML = errorPanel(err);
    root.querySelector('[data-admin-retry]')?.addEventListener('click', () => settings(root, ctx));
  }
}

/* ============================================================ STAFF/ROLES */
export async function staff(root, ctx) {
  root.innerHTML = '<div class="admin-loading"><div class="skeleton skeleton--card"></div></div>';
  const canManage = session.can('staff.manage');
  try {
    const data = await admin.staff();
    root.innerHTML = `<div class="admin-section">
      ${panel({
        title: 'Staff accounts',
        actions: canManage ? '<button class="btn btn--primary btn--sm" type="button" data-invite>Invite staff member</button>' : '',
        flush: true,
        body: table({
          columns: [
            { key: 'name', label: 'Name', wrap: true, cell: (r) => `<strong>${esc([r.first_name, r.last_name].filter(Boolean).join(' ') || r.name || '')}</strong><br><span class="help-text">${esc(r.email || '')}</span>` },
            { key: 'role', label: 'Role', cell: (r) => `<span class="pill">${esc(r.role || 'staff')}</span>` },
            { key: 'active', label: 'Status', cell: (r) => statusPill(r.is_active === false ? 'disabled' : 'active') },
            { key: 'login', label: 'Last sign-in', cell: (r) => formatDateTime(r.last_login) }
          ],
          rows: data.items, emptyMessage: 'No staff accounts yet.'
        })
      })}
      ${panel({
        title: 'Roles and permissions',
        body: `<p class="help-text">Permissions are enforced by the backend. This matrix is a read-only view of what each role is granted.</p>
          ${table({
            columns: [
              { key: 'role', label: 'Role', cell: (r) => `<strong>${esc(r.role)}</strong>` },
              { key: 'perms', label: 'Permissions', wrap: true, cell: (r) => (r.permissions || []).map((p) => `<span class="pill">${esc(p)}</span>`).join(' ') || '—' }
            ],
            rows: data.roles || [], emptyMessage: 'No role definitions returned by the backend.'
          })}`
      })}
    </div>`;

    root.querySelector('[data-invite]')?.addEventListener('click', () => {
      formModal({
        title: 'Invite a staff member',
        fields: [
          { name: 'email', label: 'Email address', type: 'email', required: true, full: true },
          { name: 'first_name', label: 'First name' },
          { name: 'last_name', label: 'Last name' },
          { name: 'role', label: 'Role', type: 'select', required: true, full: true, options: [
            { value: 'staff', label: 'Staff — day-to-day orders and catalogue' },
            { value: 'manager', label: 'Manager — orders, refunds, reports' },
            { value: 'admin', label: 'Administrator — full access except ownership' }
          ] }
        ],
        note: 'The invitee receives a sign-in link by email. They do not get a password from you.',
        submitLabel: 'Send invitation',
        onSubmit: async (values) => {
          await admin.inviteStaff(values);
          toast('Invitation sent.', { type: 'success' });
          staff(root, ctx);
        }
      });
    });
  } catch (err) {
    root.innerHTML = errorPanel(err);
    root.querySelector('[data-admin-retry]')?.addEventListener('click', () => staff(root, ctx));
  }
}

/* =================================================================== INDEX */
export const views = {
  dashboard, products, categories, inventory, orders, payments, refunds, reports,
  customers, reviews, discounts, notifications, content, seo, settings, staff
};

export const VIEW_META = {
  dashboard: { title: 'Dashboard', permission: null },
  products: { title: 'Products', permission: 'products.view' },
  categories: { title: 'Categories', permission: 'categories.view' },
  inventory: { title: 'Inventory', permission: 'inventory.view' },
  orders: { title: 'Orders', permission: 'orders.view' },
  payments: { title: 'Payments', permission: 'payments.view' },
  refunds: { title: 'Refunds', permission: 'refunds.view' },
  reports: { title: 'Reports', permission: 'reports.view' },
  customers: { title: 'Customers', permission: 'customers.view' },
  reviews: { title: 'Reviews', permission: 'reviews.view' },
  discounts: { title: 'Discounts', permission: 'discounts.view' },
  notifications: { title: 'Notifications', permission: 'notifications.view' },
  content: { title: 'Site content', permission: 'content.view' },
  seo: { title: 'SEO', permission: 'seo.view' },
  settings: { title: 'Settings', permission: 'settings.view' },
  staff: { title: 'Staff & roles', permission: 'staff.view' }
};
