/**
 * admin-modules.js — declarative configuration for every table-driven admin
 * module. Every endpoint, field name, filter and permission codename below
 * mirrors the Django REST backend (see backend/README.md → API map):
 *
 *   • permissions use backend codenames (apps/core/constants.py::Perm)
 *   • list endpoints are paginated ({count, results}); `search` is DRF's
 *     SearchFilter unless a module sets `searchParam`
 *   • nothing is invented client-side: when the API rejects a request the
 *     real error is shown.
 */

import api, { normalizeList } from '../api.js';
import { toast, confirmDialog, openDialog, withSubmit } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { esc, formatMoney, formatDateTime, formatNumber, titleCase } from '../utils.js';

/* Statuses a staff member may set by hand. Financial statuses (paid, refunded,
   expired, payment_failed…) are owned by the payment layer and rejected by the API. */
const ORDER_STATUSES = ['pending_payment', 'paid', 'processing', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'completed', 'cancelled', 'payment_failed', 'expired', 'refund_requested', 'partially_refunded', 'refunded'];
const STAFF_SETTABLE_ORDER_STATUSES = ['processing', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'completed', 'cancelled'];
const ORDER_PAYMENT_STATUSES = ['pending', 'paid', 'partially_refunded', 'refunded', 'failed', 'expired'];
const PAYMENT_STATUSES = ['pending', 'successful', 'failed', 'abandoned', 'reversed', 'refunded', 'partially_refunded'];
const REFUND_STATUSES = ['requested', 'approved', 'processing', 'successful', 'failed', 'rejected'];
const NG_STATES = ['Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara', 'Abuja FCT'];

const ORDER_TONES = { delivered: 'success', completed: 'success', paid: 'success', shipped: 'info', out_for_delivery: 'info', processing: 'info', packed: 'info', pending_payment: 'warning', refund_requested: 'warning', cancelled: 'danger', payment_failed: 'danger', expired: 'neutral', refunded: 'neutral', partially_refunded: 'neutral' };
const PAY_TONES = { successful: 'success', paid: 'success', pending: 'warning', failed: 'danger', abandoned: 'neutral', reversed: 'warning', refunded: 'info', partially_refunded: 'info', expired: 'neutral' };
const REFUND_TONES = { requested: 'warning', approved: 'info', processing: 'info', successful: 'success', failed: 'danger', rejected: 'danger' };

const statusOptions = (values) => values.map((value) => ({ value, label: titleCase(value) }));
const YES_NO = (yes, no) => [{ value: 'true', label: yes }, { value: 'false', label: no }];
const badge = (tone, text) => `<span class="badge badge--${tone} badge--dot">${esc(text)}</span>`;
const mainImage = (product) => (product.images || []).find((image) => image.is_main)?.url || product.images?.[0]?.url || null;
const orderStatusUrl = (row) => `/orders/admin/${encodeURIComponent(row.reference)}/status/`;

const CATEGORY_SOURCE = { source: '/categories/admin/', sourceParams: { page_size: 100, ordering: 'name' } };

const categoryForm = ({ sub }) => [
  { key: 'name', label: sub ? 'Subcategory name' : 'Category name', required: true, section: 'Details', maxLength: 120 },
  { key: 'slug', label: 'URL slug', section: 'Details', hint: 'Leave blank to generate from the name.' },
  sub
    ? { key: 'parent', label: 'Parent category', type: 'select', ...CATEGORY_SOURCE, required: true, section: 'Details' }
    : { key: 'parent', label: 'Parent category', type: 'select', ...CATEGORY_SOURCE, nullable: true, placeholder: 'None — top-level department', section: 'Details' },
  { key: 'display_order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Details', hint: 'Lower numbers appear first.' },
  { key: 'description', label: 'Description', type: 'textarea', rows: 4, section: 'Details' },
  { key: 'image', label: 'Category image', type: 'image', section: 'Media', full: true, hint: 'JPEG, PNG or WebP. Shown on category cards.' },
  { key: 'banner_image', label: 'Banner image', type: 'image', section: 'Media', full: true, hint: 'Wide image shown at the top of the category page.' },
  { key: 'is_active', label: 'Visible on the storefront', type: 'switch', default: true, section: 'Publishing' },
  { key: 'seo_title', label: 'SEO title', section: 'SEO', full: true, maxLength: 70 },
  { key: 'seo_description', label: 'SEO description', type: 'textarea', rows: 2, section: 'SEO', full: true, maxLength: 160 },
  { key: 'seo_keywords', label: 'SEO keywords', section: 'SEO', full: true },
];

const categoryActions = [
  { id: 'activate', label: 'Activate', icon: 'check', perm: 'categories.manage', when: (r) => !r.is_active, handler: simpleAction((r) => `/categories/admin/${r.id}/activate/`, 'Category activated.') },
  { id: 'deactivate', label: 'Deactivate (with its subcategories)', icon: 'eye-off', perm: 'categories.manage', when: (r) => r.is_active, handler: simpleAction((r) => `/categories/admin/${r.id}/deactivate/`, 'Category deactivated.') },
];

const CATEGORY_PERMS = { create: 'categories.manage', update: 'categories.manage', delete: 'categories.manage' };

export const MODULES = {
  /* ------------------------------------------------------------- products */
  products: {
    id: 'products', label: 'products', singular: 'product', createLabel: 'New product',
    endpoint: '/products/admin/', archiveLabel: 'archive', deletable: true, exportable: true,
    emptyIcon: 'package', emptyText: 'Create your first product to start selling.',
    viewPermission: 'products.view',
    permissions: { create: 'products.manage', update: 'products.manage', delete: 'products.manage' },
    viewUrl: (row) => `/products/${row.slug}/`,
    columns: [
      { key: 'name', label: 'Product', type: 'image', resolve: mainImage, subKey: 'sku' },
      { key: 'category_name', label: 'Category' },
      { key: 'effective_price', label: 'Price', type: 'money', numeric: true },
      { key: 'stock.available', label: 'Available', type: 'number', numeric: true },
      { key: 'status', label: 'Status', type: 'status', tones: { active: 'success', draft: 'neutral', inactive: 'warning', archived: 'neutral', out_of_stock: 'danger' } },
      { key: 'is_featured', label: 'Featured', type: 'boolean' },
    ],
    exportColumns: [
      { key: 'id', label: 'ID' }, { key: 'sku', label: 'SKU' }, { key: 'name', label: 'Name' }, { key: 'category_name', label: 'Category' },
      { key: 'brand', label: 'Brand' }, { key: 'regular_price', label: 'Regular price' }, { key: 'sale_price', label: 'Sale price' },
      { key: 'stock.on_hand', label: 'On hand' }, { key: 'stock.reserved', label: 'Reserved' }, { key: 'stock.available', label: 'Available' },
      { key: 'status', label: 'Status' }, { key: 'is_featured', label: 'Featured' }, { key: 'url_path', label: 'URL' },
    ],
    filters: [
      { key: 'category', label: 'All categories', type: 'select', ...CATEGORY_SOURCE },
      { key: 'status', label: 'All statuses', type: 'select', options: ['active', 'draft', 'inactive', 'out_of_stock', 'archived'] },
      { key: 'is_featured', label: 'Featured or not', type: 'select', options: YES_NO('Featured', 'Not featured') },
    ],
    bulkActions: [
      { id: 'activate', label: 'Publish', perm: 'products.manage', run: (row) => api.post(`/products/admin/${row.id}/activate/`, {}) },
      { id: 'deactivate', label: 'Unpublish', perm: 'products.manage', run: (row) => api.post(`/products/admin/${row.id}/deactivate/`, {}) },
      { id: 'archive', label: 'Archive', tone: 'danger', perm: 'products.manage', run: (row) => api.post(`/products/admin/${row.id}/archive/`, {}) },
    ],
    rowActions: [
      { id: 'images', label: 'Manage images', icon: 'image', perm: 'products.manage', handler: openProductImagesDialog },
      { id: 'variations', label: 'Manage variations', icon: 'grid', perm: 'products.manage', handler: openVariationsDialog },
      { id: 'publish', label: 'Publish', icon: 'check', perm: 'products.manage', when: (r) => r.status !== 'active', handler: simpleAction((r) => `/products/admin/${r.id}/activate/`, 'Product published.') },
      { id: 'unpublish', label: 'Unpublish', icon: 'eye-off', perm: 'products.manage', when: (r) => r.status === 'active', handler: simpleAction((r) => `/products/admin/${r.id}/deactivate/`, 'Product unpublished.') },
    ],
    form: (row) => [
      { key: 'name', label: 'Product name', required: true, section: 'Basics', full: true, maxLength: 200 },
      { key: 'sku', label: 'SKU', section: 'Basics', required: true, hint: 'Unique stock code. The product URL is generated from it.' },
      { key: 'category', label: 'Category', type: 'select', ...CATEGORY_SOURCE, required: true, section: 'Basics' },
      { key: 'brand', label: 'Brand', section: 'Basics', maxLength: 120 },
      { key: 'tags', label: 'Tags', section: 'Basics', hint: 'Comma-separated keywords used by search.' },
      { key: 'short_description', label: 'Short description', type: 'textarea', rows: 2, section: 'Basics', full: true, maxLength: 300 },
      { key: 'description', label: 'Full description', type: 'richtext', section: 'Basics' },
      { key: 'specifications', label: 'Specifications', type: 'keyvalue', section: 'Basics', hint: 'One per line, e.g. “Voltage: 220V”.', placeholder: 'Voltage: 220V\nWarranty: 12 months' },
      { key: 'regular_price', label: 'Regular price (NGN)', type: 'money', required: true, section: 'Pricing & stock' },
      { key: 'sale_price', label: 'Sale price (NGN)', type: 'money', section: 'Pricing & stock', hint: 'Optional. Must be lower than the regular price.',
        validate: (value, values) => (value != null && values.regular_price != null && Number(value) >= Number(values.regular_price) ? 'Sale price must be lower than the regular price.' : '') },
      { key: 'cost_price', label: 'Cost price (NGN)', type: 'money', section: 'Pricing & stock', hint: 'Internal only — never shown to customers.' },
      ...(row ? [] : [{ key: 'stock_quantity', label: 'Opening stock', type: 'number', min: 0, default: 0, section: 'Pricing & stock', hint: 'Later changes are made from Inventory so every movement is recorded.' }]),
      { key: 'low_stock_threshold', label: 'Low-stock threshold', type: 'number', min: 0, default: 5, emptyValue: 5, section: 'Pricing & stock' },
      { key: 'weight_kg', label: 'Weight (kg)', type: 'money', section: 'Pricing & stock' },
      { key: 'images', label: row ? 'Add images' : 'Product images', type: 'images', section: 'Media', hint: 'Up to 10 images per upload. Use “Manage images” on the product row to delete images or choose the main one.' },
      { key: 'video_url', label: 'Video URL', type: 'url', section: 'Media', full: true },
      { key: 'status', label: 'Status', type: 'select', options: ['draft', 'active', 'inactive'], default: 'draft', required: true, section: 'Publishing' },
      { key: 'is_featured', label: 'Featured product', type: 'switch', section: 'Publishing' },
      { key: 'is_new_arrival', label: 'New arrival', type: 'switch', section: 'Publishing' },
      { key: 'is_best_seller', label: 'Best seller', type: 'switch', section: 'Publishing' },
      { key: 'supports_customization', label: 'Accepts customisation notes at checkout', type: 'switch', section: 'Publishing' },
      { key: 'seo_title', label: 'SEO title', section: 'SEO', full: true, maxLength: 70 },
      { key: 'seo_description', label: 'SEO description', type: 'textarea', rows: 2, section: 'SEO', full: true, maxLength: 160 },
      { key: 'seo_keywords', label: 'SEO keywords', section: 'SEO', full: true },
    ],
    // Product images have their own multipart route.
    afterSave: async (product, { files }) => {
      const images = files.filter((f) => f.name === 'images');
      if (!images.length || !product?.id) return;
      const fd = new FormData();
      images.forEach(({ file }) => fd.append('images', file));
      await api.upload(`/products/admin/${product.id}/images/`, fd);
    },
  },

  /* ----------------------------------------------------------- categories */
  categories: {
    id: 'categories', label: 'categories', singular: 'category', createLabel: 'New category',
    endpoint: '/categories/admin/', extraParams: { level: 'top' }, deletable: true, exportable: true,
    emptyIcon: 'folder', viewPermission: 'categories.manage',
    deleteMessage: 'Categories that still contain products or subcategories cannot be deleted — the server will refuse.',
    permissions: CATEGORY_PERMS,
    viewUrl: (row) => row.url_path,
    columns: [
      { key: 'name', label: 'Category', type: 'image', resolve: (r) => r.image, subKey: 'slug', sortable: true },
      { key: 'product_count', label: 'Products', type: 'number', numeric: true },
      { key: 'display_order', label: 'Order', type: 'number', numeric: true, sortable: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'is_active', label: 'Any status', type: 'select', options: YES_NO('Active', 'Inactive') }],
    rowActions: categoryActions,
    form: categoryForm({ sub: false }),
  },

  subcategories: {
    id: 'subcategories', label: 'subcategories', singular: 'subcategory', createLabel: 'New subcategory',
    endpoint: '/categories/admin/', extraParams: { level: 'sub' }, deletable: true, exportable: true,
    emptyIcon: 'layers', viewPermission: 'categories.manage',
    deleteMessage: 'Subcategories that still contain products cannot be deleted — the server will refuse.',
    permissions: CATEGORY_PERMS,
    viewUrl: (row) => row.url_path,
    columns: [
      { key: 'name', label: 'Subcategory', type: 'image', resolve: (r) => r.image, subKey: 'slug', sortable: true },
      { key: 'parent_name', label: 'Parent' },
      { key: 'product_count', label: 'Products', type: 'number', numeric: true },
      { key: 'display_order', label: 'Order', type: 'number', numeric: true, sortable: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [
      { key: 'parent', label: 'All parents', type: 'select', source: '/categories/admin/', sourceParams: { level: 'top', page_size: 100, ordering: 'name' } },
      { key: 'is_active', label: 'Any status', type: 'select', options: YES_NO('Active', 'Inactive') },
    ],
    rowActions: categoryActions,
    form: categoryForm({ sub: true }),
  },

  /* ------------------------------------------------------------ inventory */
  inventory: {
    id: 'inventory', label: 'stock records', singular: 'stock record',
    endpoint: '/inventory/', exportable: true, emptyIcon: 'clipboard', viewPermission: 'inventory.view',
    labelKey: 'product_name',
    columns: [
      { key: 'product_name', label: 'Product', type: 'primary', subKey: 'product_sku' },
      { key: 'variation_name', label: 'Variation' },
      { key: 'on_hand', label: 'On hand', type: 'number', numeric: true },
      { key: 'reserved', label: 'Reserved', type: 'number', numeric: true },
      { key: 'available', label: 'Available', type: 'number', numeric: true },
      { key: 'level', label: 'Level', type: 'custom', render: (r) => (r.is_out_of_stock ? badge('danger', 'Out of stock') : r.is_low_stock ? badge('warning', 'Low stock') : badge('success', 'In stock')) },
    ],
    exportColumns: [
      { key: 'product_sku', label: 'Product SKU' }, { key: 'product_name', label: 'Product' },
      { key: 'variation_sku', label: 'Variation SKU' }, { key: 'variation_name', label: 'Variation' },
      { key: 'on_hand', label: 'On hand' }, { key: 'reserved', label: 'Reserved' }, { key: 'available', label: 'Available' },
      { key: 'effective_threshold', label: 'Low-stock threshold' }, { key: 'updated_at', label: 'Updated' },
    ],
    filters: [
      { key: 'low_stock', label: 'Any level', type: 'select', options: [{ value: 'true', label: 'Low stock only' }] },
      { key: 'out_of_stock', label: 'Any availability', type: 'select', options: [{ value: 'true', label: 'Out of stock only' }] },
    ],
    rowActions: [
      { id: 'receive', label: 'Receive stock', icon: 'plus', perm: 'inventory.manage', handler: openReceiveDialog },
      { id: 'adjust', label: 'Adjust stock', icon: 'clipboard', perm: 'inventory.manage', handler: openStockDialog },
      { id: 'movements', label: 'Stock movements', icon: 'eye', handler: openMovementsDialog },
    ],
  },

  /* --------------------------------------------------------------- orders */
  orders: {
    id: 'orders', label: 'orders', singular: 'order', endpoint: '/orders/admin/', exportable: true,
    idKey: 'reference', labelKey: 'reference', searchParam: 'q',
    defaultOrdering: '-placed_at', emptyIcon: 'receipt', viewPermission: 'orders.view',
    emptyText: 'Orders appear here as soon as customers check out.',
    columns: [
      { key: 'reference', label: 'Reference', type: 'primary' },
      { key: 'contact.email', label: 'Customer', type: 'custom', render: (r) => `<span class="cell-stack"><span>${esc(r.delivery?.full_name || r.contact?.full_name || '—')}</span><span class="cell-muted">${esc(r.contact?.email || r.customer_email || '')}</span></span>` },
      { key: 'totals.total', label: 'Total', type: 'money', numeric: true, sortable: true, sortKey: 'total_amount' },
      { key: 'payment_status', label: 'Payment', type: 'status', tones: PAY_TONES },
      { key: 'status', label: 'Order status', type: 'status', tones: ORDER_TONES },
      { key: 'placed_at', label: 'Placed', type: 'datetime', sortable: true },
    ],
    exportColumns: [
      { key: 'reference', label: 'Reference' }, { key: 'placed_at', label: 'Placed at' },
      { key: 'status', label: 'Order status' }, { key: 'payment_status', label: 'Payment status' },
      { key: 'contact.email', label: 'Email' }, { key: 'contact.phone', label: 'Phone' },
      { key: 'delivery.full_name', label: 'Recipient' }, { key: 'delivery.state', label: 'State' }, { key: 'delivery.city', label: 'City' },
      { key: 'delivery.method', label: 'Delivery method' }, { key: 'delivery.tracking_reference', label: 'Tracking' },
      { key: 'totals.subtotal', label: 'Subtotal' }, { key: 'totals.discount', label: 'Discount' },
      { key: 'totals.shipping_fee', label: 'Delivery fee' }, { key: 'totals.total', label: 'Total' }, { key: 'totals.refunded', label: 'Refunded' },
      { label: 'Items', value: (r) => (r.items || []).map((i) => `${i.quantity} x ${i.product_name}${i.variation_label ? ` (${i.variation_label})` : ''}`).join('; ') },
    ],
    filters: [
      { key: 'status', label: 'Any order status', type: 'select', options: statusOptions(ORDER_STATUSES) },
      { key: 'payment_status', label: 'Any payment status', type: 'select', options: statusOptions(ORDER_PAYMENT_STATUSES) },
      { key: 'date_from', label: 'Placed from', type: 'date' },
      { key: 'date_to', label: 'Placed to', type: 'date' },
    ],
    bulkActions: [
      { id: 'processing', label: 'Mark processing', perm: 'orders.fulfil', run: (row) => api.post(orderStatusUrl(row), { status: 'processing' }) },
      { id: 'packed', label: 'Mark packed', perm: 'orders.fulfil', run: (row) => api.post(orderStatusUrl(row), { status: 'packed' }) },
    ],
    rowActions: [
      { id: 'view', label: 'View order', icon: 'eye', handler: openOrderDialog },
      { id: 'status', label: 'Update status', icon: 'truck', perm: 'orders.fulfil', handler: openOrderStatusDialog },
      { id: 'receipt', label: 'Print receipt', icon: 'printer', when: (r) => ['paid', 'partially_refunded', 'refunded'].includes(r.payment_status), handler: printReceipt },
    ],
  },

  /* ------------------------------------------------------------- payments */
  payments: {
    id: 'payments', label: 'payments', singular: 'payment', endpoint: '/payments/admin/', exportable: true,
    emptyIcon: 'credit-card', labelKey: 'reference', viewPermission: 'finance.view',
    columns: [
      { key: 'reference', label: 'Reference', type: 'primary', subKey: 'order_reference' },
      { key: 'amount', label: 'Amount', type: 'money', numeric: true },
      { key: 'status', label: 'Status', type: 'status', tones: PAY_TONES },
      { key: 'channel', label: 'Channel' },
      { key: 'initialized_at', label: 'Started', type: 'datetime' },
      { key: 'verified_at', label: 'Verified', type: 'datetime' },
    ],
    exportColumns: [
      { key: 'reference', label: 'Reference' }, { key: 'provider_reference', label: 'Provider reference' },
      { key: 'order_reference', label: 'Order' }, { key: 'amount', label: 'Amount' }, { key: 'currency', label: 'Currency' },
      { key: 'status', label: 'Status' }, { key: 'channel', label: 'Channel' },
      { key: 'initialized_at', label: 'Initialized at' }, { key: 'verified_at', label: 'Verified at' }, { key: 'failure_reason', label: 'Failure reason' },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: statusOptions(PAYMENT_STATUSES) }],
    rowActions: [
      { id: 'detail', label: 'Payment detail', icon: 'eye', handler: openPaymentDialog },
      {
        id: 'verify', label: 'Re-check with Paystack', icon: 'refresh', perm: 'orders.view',
        when: (r) => ['pending', 'abandoned', 'failed'].includes(r.status),
        handler: async (row, table) => {
          try {
            // The same server-side verification the storefront uses.
            const result = await api.post('/payments/paystack/verify/', { reference: row.provider_reference || row.reference });
            toast(`Paystack reports: ${titleCase(result?.payment_status || 'unknown')}.`, { type: result?.payment_status === 'successful' ? 'success' : 'info' });
            table.load();
          } catch (error) { toast(error.userMessage, { type: 'danger' }); }
        },
      },
    ],
  },

  /* -------------------------------------------------------------- refunds */
  refunds: {
    id: 'refunds', label: 'refund requests', singular: 'refund', endpoint: '/refunds/admin/', exportable: true,
    emptyIcon: 'undo', labelKey: 'reference', viewPermission: 'finance.view',
    columns: [
      { key: 'order_reference', label: 'Order', type: 'primary', subKey: 'reference' },
      { key: 'requested_amount', label: 'Requested', type: 'money', numeric: true },
      { key: 'approved_amount', label: 'Approved', type: 'money', numeric: true },
      { key: 'reason', label: 'Reason', type: 'truncate' },
      { key: 'status', label: 'Status', type: 'status', tones: REFUND_TONES },
      { key: 'created_at', label: 'Requested on', type: 'datetime' },
    ],
    exportColumns: [
      { key: 'reference', label: 'Refund' }, { key: 'order_reference', label: 'Order' }, { key: 'payment_reference', label: 'Payment' },
      { key: 'requested_amount', label: 'Requested' }, { key: 'approved_amount', label: 'Approved' }, { key: 'status', label: 'Status' },
      { key: 'reason', label: 'Reason' }, { key: 'processed_by_email', label: 'Processed by' },
      { key: 'created_at', label: 'Requested at' }, { key: 'processed_at', label: 'Processed at' },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: statusOptions(REFUND_STATUSES) }],
    rowActions: [
      { id: 'approve', label: 'Approve refund', icon: 'check', perm: 'refunds.manage', when: (r) => r.status === 'requested', handler: refundDecision('approve') },
      { id: 'reject', label: 'Reject refund', icon: 'x', tone: 'danger', perm: 'refunds.manage', when: (r) => r.status === 'requested', handler: refundDecision('reject') },
      { id: 'check', label: 'Check provider status', icon: 'refresh', perm: 'refunds.manage', when: (r) => ['approved', 'processing'].includes(r.status), handler: simpleAction((r) => `/refunds/admin/${r.id}/check-status/`, 'Refund status refreshed.') },
    ],
  },

  /* ------------------------------------------------------------- delivery */
  delivery: {
    id: 'delivery', label: 'delivery methods', singular: 'delivery method', createLabel: 'New delivery method',
    endpoint: '/shipping/methods/', deletable: true, emptyIcon: 'truck', viewPermission: 'shipping.manage',
    emptyText: 'Customers cannot check out until at least one active delivery method covers their state.',
    permissions: { create: 'shipping.manage', update: 'shipping.manage', delete: 'shipping.manage' },
    columns: [
      { key: 'name', label: 'Method', type: 'primary', subKey: 'estimated_delivery' },
      { key: 'kind', label: 'Type', type: 'status', tones: { standard: 'neutral', express: 'info', pickup: 'warning' } },
      { key: 'zone_name', label: 'Zone' },
      { key: 'fee', label: 'Fee', type: 'money', numeric: true },
      { key: 'free_above_amount', label: 'Free above', type: 'money', numeric: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    form: [
      { key: 'name', label: 'Method name', required: true, section: 'Method', maxLength: 120 },
      { key: 'kind', label: 'Type', type: 'select', options: ['standard', 'express', 'pickup'], default: 'standard', required: true, section: 'Method' },
      { key: 'zone', label: 'Shipping zone', type: 'select', source: '/shipping/zones/', nullable: true, placeholder: 'All states (no zone)', section: 'Method', hint: 'Limit this method to the states in one zone.' },
      { key: 'display_order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Method' },
      { key: 'fee', label: 'Delivery fee (NGN)', type: 'money', required: true, default: '0', section: 'Pricing' },
      { key: 'free_above_amount', label: 'Free when subtotal is at least (NGN)', type: 'money', section: 'Pricing', hint: 'Leave blank to always charge the fee.' },
      { key: 'min_days', label: 'Minimum days', type: 'number', min: 0, default: 1, section: 'Estimate' },
      { key: 'max_days', label: 'Maximum days', type: 'number', min: 0, default: 5, section: 'Estimate', validate: (value, values) => (Number(value) < Number(values.min_days) ? 'Maximum days cannot be less than minimum days.' : '') },
      { key: 'pickup_address', label: 'Pickup address', type: 'textarea', rows: 2, section: 'Estimate', hint: 'Only for pickup methods.' },
      { key: 'is_active', label: 'Offered at checkout', type: 'switch', default: true, section: 'Estimate' },
    ],
  },

  'shipping-zones': {
    id: 'shipping-zones', label: 'shipping zones', singular: 'shipping zone', createLabel: 'New zone',
    endpoint: '/shipping/zones/', deletable: true, emptyIcon: 'map-pin', viewPermission: 'shipping.manage',
    permissions: { create: 'shipping.manage', update: 'shipping.manage', delete: 'shipping.manage' },
    columns: [
      { key: 'name', label: 'Zone', type: 'primary' },
      { key: 'states', label: 'States', type: 'custom', render: (r) => `<span class="t-clamp-2">${esc((r.states || []).join(', ') || '—')}</span>` },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    form: [
      { key: 'name', label: 'Zone name', required: true, section: 'Zone', maxLength: 120 },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Zone' },
      { key: 'states', label: 'States covered', type: 'checklist', options: NG_STATES, required: true, section: 'Coverage' },
    ],
  },

  /* ------------------------------------------------------------ customers */
  customers: {
    id: 'customers', label: 'customers', singular: 'customer', endpoint: '/admin-panel/customers/', exportable: true,
    emptyIcon: 'users', labelKey: 'email', viewPermission: 'customers.view',
    columns: [
      { key: 'full_name', label: 'Customer', type: 'primary', subKey: 'email' },
      { key: 'phone', label: 'Phone' },
      { key: 'orders_count', label: 'Orders', type: 'number', numeric: true },
      { key: 'total_spent', label: 'Paid total', type: 'money', numeric: true },
      { key: 'is_email_verified', label: 'Email verified', type: 'boolean' },
      { key: 'date_joined', label: 'Joined', type: 'date' },
    ],
    exportColumns: [
      { key: 'full_name', label: 'Name' }, { key: 'email', label: 'Email' }, { key: 'phone', label: 'Phone' },
      { key: 'orders_count', label: 'Orders' }, { key: 'total_spent', label: 'Paid total' },
      { key: 'is_email_verified', label: 'Email verified' }, { key: 'date_joined', label: 'Joined' },
    ],
    rowActions: [
      { id: 'orders', label: 'View this customer’s orders', icon: 'receipt', perm: 'orders.view', handler: (row) => { window.location.assign(`/admin/orders.html?q=${encodeURIComponent(row.email)}`); } },
    ],
  },

  /* -------------------------------------------------------------- reviews */
  reviews: {
    id: 'reviews', label: 'reviews', singular: 'review', endpoint: '/reviews/admin/', deletable: true,
    emptyIcon: 'star', labelKey: 'product_name', viewPermission: 'reviews.moderate',
    permissions: { delete: 'reviews.moderate' },
    columns: [
      { key: 'product_name', label: 'Product', type: 'primary', subKey: 'customer_email' },
      { key: 'rating', label: 'Rating', type: 'custom', render: (r) => `<span aria-label="${esc(r.rating)} out of 5">${'★'.repeat(r.rating || 0)}<span class="cell-muted">${'★'.repeat(5 - (r.rating || 0))}</span></span>` },
      { key: 'body', label: 'Review', type: 'custom', render: (r) => `<span class="cell-stack">${r.title ? `<strong>${esc(r.title)}</strong>` : ''}<span class="t-clamp-2">${esc(r.body || '')}</span></span>` },
      { key: 'is_verified_purchase', label: 'Verified buyer', type: 'boolean' },
      { key: 'moderation_status', label: 'Status', type: 'status', tones: { approved: 'success', pending: 'warning', rejected: 'danger' } },
      { key: 'created_at', label: 'Submitted', type: 'date' },
    ],
    filters: [{ key: 'moderation_status', label: 'Any status', type: 'select', options: ['pending', 'approved', 'rejected'] }],
    bulkActions: [
      { id: 'approve', label: 'Approve', perm: 'reviews.moderate', run: (row) => api.post(`/reviews/admin/${row.id}/approve/`, {}) },
      { id: 'reject', label: 'Reject', tone: 'danger', perm: 'reviews.moderate', run: (row) => api.post(`/reviews/admin/${row.id}/reject/`, {}) },
    ],
    rowActions: [
      { id: 'approve', label: 'Approve and publish', icon: 'check', perm: 'reviews.moderate', when: (r) => r.moderation_status !== 'approved', handler: simpleAction((r) => `/reviews/admin/${r.id}/approve/`, 'Review published.') },
      { id: 'reject', label: 'Reject', icon: 'x', tone: 'danger', perm: 'reviews.moderate', when: (r) => r.moderation_status !== 'rejected', handler: reviewReject },
    ],
  },

  /* ------------------------------------------------------------ enquiries */
  enquiries: {
    id: 'enquiries', label: 'enquiries', singular: 'enquiry', endpoint: '/notifications/enquiries/admin/', deletable: true,
    emptyIcon: 'message', labelKey: 'subject', viewPermission: 'notifications.manage',
    permissions: { delete: 'notifications.manage' },
    columns: [
      { key: 'subject', label: 'Subject', type: 'primary', subKey: 'full_name' },
      { key: 'email', label: 'Email' },
      { key: 'order_reference', label: 'Order' },
      { key: 'status', label: 'Status', type: 'status', tones: { new: 'warning', in_progress: 'info', resolved: 'success' } },
      { key: 'created_at', label: 'Received', type: 'datetime' },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: ['new', 'in_progress', 'resolved'] }],
    rowActions: [{ id: 'open', label: 'Open enquiry', icon: 'eye', handler: openEnquiryDialog }],
  },

  /* ----------------------------------------------------------- newsletter */
  newsletter: {
    id: 'newsletter', label: 'subscribers', singular: 'subscriber', endpoint: '/notifications/newsletter/admin/',
    exportable: true, emptyIcon: 'mail', labelKey: 'email', viewPermission: 'notifications.manage',
    columns: [
      { key: 'email', label: 'Email', type: 'primary' },
      { key: 'is_active', label: 'Subscribed', type: 'boolean' },
      { key: 'source', label: 'Source' },
      { key: 'created_at', label: 'Subscribed on', type: 'datetime' },
      { key: 'unsubscribed_at', label: 'Unsubscribed on', type: 'datetime' },
    ],
    filters: [{ key: 'is_active', label: 'Any status', type: 'select', options: YES_NO('Subscribed', 'Unsubscribed') }],
  },

  /* ----------------------------------------------------------- promotions */
  promotions: {
    id: 'promotions', label: 'promotions', singular: 'promotion', createLabel: 'New promotion',
    endpoint: '/promotions/', deletable: true, exportable: true, emptyIcon: 'percent', labelKey: 'code',
    viewPermission: 'promotions.manage',
    permissions: { create: 'promotions.manage', update: 'promotions.manage', delete: 'promotions.manage' },
    columns: [
      { key: 'code', label: 'Code', type: 'primary', subKey: 'name' },
      { key: 'value', label: 'Discount', type: 'custom', render: (r) => esc(r.kind === 'percentage' ? `${Number(r.value)}%` : formatMoney(r.value)) },
      { key: 'scope', label: 'Applies to', type: 'status', labels: { all: 'Whole order', products: 'Selected products', categories: 'Selected categories' } },
      { key: 'total_usages', label: 'Used', type: 'custom', render: (r) => esc(`${formatNumber(r.total_usages || 0)}${r.usage_limit ? ` / ${formatNumber(r.usage_limit)}` : ''}`) },
      { key: 'state', label: 'State', type: 'custom', render: (r) => (!r.is_active ? badge('neutral', 'Disabled') : r.is_within_window ? badge('success', 'Live') : badge('warning', 'Outside schedule')) },
      { key: 'ends_at', label: 'Ends', type: 'datetime' },
    ],
    exportColumns: [
      { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'kind', label: 'Kind' }, { key: 'value', label: 'Value' },
      { key: 'scope', label: 'Scope' }, { key: 'min_purchase_amount', label: 'Minimum purchase' }, { key: 'max_discount_amount', label: 'Maximum discount' },
      { key: 'starts_at', label: 'Starts' }, { key: 'ends_at', label: 'Ends' }, { key: 'usage_limit', label: 'Usage limit' },
      { key: 'total_usages', label: 'Used' }, { key: 'is_active', label: 'Active' },
    ],
    filters: [
      { key: 'is_active', label: 'Any state', type: 'select', options: YES_NO('Enabled', 'Disabled') },
      { key: 'kind', label: 'Any type', type: 'select', options: [{ value: 'percentage', label: 'Percentage' }, { value: 'fixed', label: 'Fixed amount' }] },
    ],
    form: [
      { key: 'code', label: 'Code', required: true, section: 'Promotion', hint: 'What customers type at checkout, e.g. WELCOME10.', maxLength: 40 },
      { key: 'name', label: 'Internal name', required: true, section: 'Promotion', maxLength: 120 },
      { key: 'description', label: 'Description', type: 'textarea', rows: 2, section: 'Promotion' },
      { key: 'kind', label: 'Discount type', type: 'select', options: [{ value: 'percentage', label: 'Percentage off' }, { value: 'fixed', label: 'Fixed amount off (NGN)' }], required: true, default: 'percentage', section: 'Discount' },
      { key: 'value', label: 'Value', type: 'money', required: true, section: 'Discount', hint: 'Percent (1–100) or an amount in NGN.',
        validate: (value, values) => (values.kind === 'percentage' && value != null && (Number(value) <= 0 || Number(value) > 100) ? 'A percentage must be between 1 and 100.' : '') },
      { key: 'min_purchase_amount', label: 'Minimum purchase (NGN)', type: 'money', section: 'Discount' },
      { key: 'max_discount_amount', label: 'Maximum discount (NGN)', type: 'money', section: 'Discount', hint: 'Caps a percentage discount.' },
      { key: 'scope', label: 'Applies to', type: 'select', options: [{ value: 'all', label: 'Whole order' }, { value: 'products', label: 'Selected products' }, { value: 'categories', label: 'Selected categories' }], default: 'all', required: true, section: 'Eligibility' },
      { key: 'category_ids', label: 'Categories (when scope is “Selected categories”)', type: 'checklist', numeric: true, ...CATEGORY_SOURCE, section: 'Eligibility' },
      { key: 'product_ids', label: 'Product IDs (when scope is “Selected products”)', type: 'idlist', section: 'Eligibility', full: true, hint: 'Comma-separated product IDs. Product IDs are included in the Products export.' },
      { key: 'applies_to_sale_items', label: 'Also applies to items already on sale', type: 'switch', default: true, section: 'Eligibility' },
      { key: 'first_time_customers_only', label: 'First-time customers only', type: 'switch', section: 'Eligibility' },
      { key: 'starts_at', label: 'Starts', type: 'datetime', section: 'Schedule & limits' },
      { key: 'ends_at', label: 'Ends', type: 'datetime', section: 'Schedule & limits',
        validate: (value, values) => (value && values.starts_at && new Date(value) <= new Date(values.starts_at) ? 'The end must be after the start.' : '') },
      { key: 'usage_limit', label: 'Total usage limit', type: 'number', min: 1, section: 'Schedule & limits' },
      { key: 'usage_limit_per_customer', label: 'Limit per customer', type: 'number', min: 1, default: 1, emptyValue: 1, section: 'Schedule & limits' },
      { key: 'is_active', label: 'Enabled', type: 'switch', default: true, section: 'Schedule & limits' },
      { key: 'banner_image', label: 'Banner image', type: 'image', section: 'Banner', full: true },
    ],
    toPayload: (body) => ({ ...body, code: String(body.code || '').trim().toUpperCase() }),
  },

  /* ----------------------------------------------------------- email logs */
  content: {
    id: 'content', label: 'pages', singular: 'page', createLabel: 'New page', idKey: 'slug', labelKey: 'title',
    endpoint: '/cms/admin/pages/', deletable: true, emptyIcon: 'file-text', viewPermission: 'cms.manage',
    emptyText: 'About, policy and FAQ pages shown on the storefront are managed here.',
    deleteMessage: 'The storefront page with this address will stop showing its content.',
    permissions: { create: 'cms.manage', update: 'cms.manage', delete: 'cms.manage' },
    defaultOrdering: 'display_order',
    columns: [
      { key: 'title', label: 'Page', type: 'primary', subKey: 'slug' },
      { key: 'excerpt', label: 'Summary', truncate: true },
      { key: 'is_published', label: 'Published', type: 'boolean' },
      { key: 'updated_at', label: 'Last updated', type: 'datetime' },
    ],
    form: (row) => [
      { key: 'title', label: 'Page title', required: true, full: true, maxLength: 200, section: 'Page' },
      row
        ? { key: 'slug', label: 'Address (slug)', type: 'readonly', section: 'Page', hint: 'Storefront pages are linked by this address, so it cannot be changed.' }
        : { key: 'slug', label: 'Address (slug)', required: true, section: 'Page', placeholder: 'e.g. warranty-policy', hint: 'Lowercase letters, numbers and hyphens.', validate: (v) => (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v || '') ? '' : 'Use lowercase letters, numbers and hyphens only.') },
      { key: 'excerpt', label: 'Short summary', type: 'textarea', rows: 2, section: 'Page' },
      { key: 'body', label: 'Page content (HTML)', type: 'richtext', rows: 14, section: 'Page', hint: 'Headings, paragraphs, lists and links are allowed. Scripts are removed by the server.' },
      { key: 'display_order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Publishing' },
      { key: 'is_published', label: 'Published on the storefront', type: 'switch', default: true, section: 'Publishing' },
      { key: 'seo_title', label: 'SEO title', maxLength: 180, section: 'Search engines', hint: 'Leave blank to use the page title.' },
      { key: 'seo_description', label: 'Meta description', type: 'textarea', rows: 2, maxLength: 320, section: 'Search engines' },
      { key: 'canonical_url', label: 'Canonical URL', type: 'url', section: 'Search engines' },
    ],
  },

  banners: {
    id: 'banners', label: 'banners', singular: 'banner', createLabel: 'New banner', labelKey: 'title',
    endpoint: '/cms/admin/banners/', deletable: true, emptyIcon: 'image', viewPermission: 'cms.manage',
    emptyText: 'Promotional banners appear on the homepage while they are active and within their dates.',
    permissions: { create: 'cms.manage', update: 'cms.manage', delete: 'cms.manage' },
    columns: [
      { key: 'image_url', label: 'Image', type: 'image' },
      { key: 'title', label: 'Banner', type: 'primary', subKey: 'subtitle' },
      { key: 'placement', label: 'Placement' },
      { key: 'starts_at', label: 'Starts', type: 'datetime' },
      { key: 'ends_at', label: 'Ends', type: 'datetime' },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    form: [
      { key: 'title', label: 'Headline', required: true, full: true, maxLength: 150, section: 'Banner' },
      { key: 'subtitle', label: 'Supporting text', full: true, maxLength: 250, section: 'Banner' },
      { key: 'image_key', label: 'Image', type: 'mediakey', kind: 'banner', previewKey: 'image_url', section: 'Banner' },
      { key: 'link_url', label: 'Link', section: 'Banner', placeholder: '/shop.html?on_sale=true', hint: 'Where the banner takes the customer.' },
      { key: 'placement', label: 'Placement', default: 'homepage', section: 'Banner', hint: 'The storefront shows banners placed on "homepage".' },
      { key: 'starts_at', label: 'Show from', type: 'datetime', section: 'Schedule' },
      { key: 'ends_at', label: 'Show until', type: 'datetime', section: 'Schedule' },
      { key: 'display_order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Schedule' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Schedule' },
    ],
  },

  'homepage-sections': {
    id: 'homepage-sections', label: 'homepage sections', singular: 'section', createLabel: 'New section', labelKey: 'title',
    endpoint: '/cms/admin/sections/', deletable: true, emptyIcon: 'layers', viewPermission: 'cms.manage',
    emptyText: 'Sections control which blocks appear on the homepage and in what order.',
    permissions: { create: 'cms.manage', update: 'cms.manage', delete: 'cms.manage' },
    defaultOrdering: 'display_order',
    columns: [
      { key: 'display_order', label: 'Order', type: 'number', numeric: true },
      { key: 'title', label: 'Section', type: 'primary', subKey: 'subtitle' },
      { key: 'kind', label: 'Type', type: 'status', tones: {} },
      { key: 'is_active', label: 'Shown', type: 'boolean' },
    ],
    form: [
      { key: 'kind', label: 'Type', type: 'select', required: true, default: 'featured_products', section: 'Section',
        options: statusOptions(['hero', 'featured_products', 'new_arrivals', 'best_sellers', 'category_spotlight', 'banner', 'custom']) },
      { key: 'display_order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Section' },
      { key: 'title', label: 'Heading', full: true, maxLength: 150, section: 'Section' },
      { key: 'subtitle', label: 'Sub-heading', full: true, maxLength: 250, section: 'Section' },
      { key: 'image_key', label: 'Image', type: 'mediakey', kind: 'banner', previewKey: 'image_url', section: 'Section' },
      { key: 'config', label: 'Options', type: 'json', rows: 5, default: {}, section: 'Section', hint: 'Optional JSON, e.g. {"category_slug": "electrical", "limit": 8, "cta_url": "/category.html?slug=electrical"}' },
      { key: 'is_active', label: 'Shown on the homepage', type: 'switch', default: true, section: 'Section' },
    ],
  },

  'email-logs': {
    id: 'email-logs', label: 'email log entries', singular: 'email', endpoint: '/emails/logs/',
    exportable: true, emptyIcon: 'send', labelKey: 'subject', viewPermission: 'notifications.manage',
    columns: [
      { key: 'subject', label: 'Subject', type: 'primary', subKey: 'recipient' },
      { key: 'template_key', label: 'Template' },
      { key: 'order_reference', label: 'Order' },
      { key: 'status', label: 'Status', type: 'status', tones: { sent: 'success', queued: 'warning', failed: 'danger', duplicate_skipped: 'neutral' } },
      { key: 'attempts', label: 'Attempts', type: 'number', numeric: true },
      { key: 'created_at', label: 'Created', type: 'datetime' },
    ],
    filters: [
      { key: 'status', label: 'Any status', type: 'select', options: statusOptions(['queued', 'sent', 'failed', 'duplicate_skipped']) },
      { key: 'date_from', label: 'From', type: 'date' },
    ],
    rowActions: [{ id: 'view', label: 'Delivery detail', icon: 'eye', handler: openEmailDialog }],
  },

  /* ---------------------------------------------------------------- staff */
  staff: {
    id: 'staff', label: 'staff accounts', singular: 'staff account', createLabel: 'New staff account',
    endpoint: '/admin-panel/staff/', deletable: true, emptyIcon: 'shield', labelKey: 'email',
    viewPermission: 'staff.manage', searchable: false,
    emptyText: 'Create a staff account and assign it a role. The owner account always has full access.',
    deleteMessage: 'This removes the person’s staff access. Their past actions stay in the audit log.',
    permissions: { create: 'staff.manage', update: 'staff.manage', delete: 'staff.manage' },
    columns: [
      { key: 'full_name', label: 'Staff member', type: 'primary', subKey: 'email' },
      { key: 'role_name', label: 'Role' },
      { key: 'is_active', label: 'Active', type: 'boolean' },
      { key: 'created_at', label: 'Added', type: 'date' },
    ],
    rowActions: [
      { id: 'activate', label: 'Reactivate access', icon: 'check', perm: 'staff.manage', when: (r) => !r.is_active, handler: simpleAction((r) => `/admin-panel/staff/${r.id}/activate/`, 'Staff access reactivated.') },
      { id: 'deactivate', label: 'Deactivate access', icon: 'lock', tone: 'danger', perm: 'staff.manage', when: (r) => r.is_active, handler: simpleAction((r) => `/admin-panel/staff/${r.id}/deactivate/`, 'Staff access deactivated.') },
    ],
    form: (row) => (row
      ? [
        { key: 'email', label: 'Email', type: 'readonly', section: 'Account' },
        { key: 'role', label: 'Role', type: 'select', source: '/admin-panel/roles/', required: true, section: 'Account' },
        { key: 'notes', label: 'Internal notes', type: 'textarea', rows: 3, section: 'Account' },
      ]
      : [
        { key: 'full_name', label: 'Full name', required: true, section: 'Account', maxLength: 150 },
        { key: 'email', label: 'Email address', type: 'email', required: true, section: 'Account' },
        { key: 'phone', label: 'Phone number', type: 'tel', section: 'Account' },
        { key: 'role', label: 'Role', type: 'select', source: '/admin-panel/roles/', required: true, section: 'Account' },
        { key: 'temporary_password', label: 'Temporary password', type: 'password', required: true, section: 'Account', full: true,
          hint: 'At least 10 characters. Share it securely and ask the person to change it after first sign-in.',
          validate: (value) => (value && String(value).length < 10 ? 'Use at least 10 characters.' : '') },
      ]),
  },

  roles: {
    id: 'roles', label: 'roles', singular: 'role', createLabel: 'New role',
    endpoint: '/admin-panel/roles/', deletable: true, emptyIcon: 'lock', viewPermission: 'staff.manage', searchable: false,
    deleteMessage: 'Built-in roles and roles still assigned to staff cannot be deleted — the server will refuse.',
    permissions: { create: 'staff.manage', update: 'staff.manage', delete: 'staff.manage' },
    columns: [
      { key: 'name', label: 'Role', type: 'primary', subKey: 'description' },
      { key: 'permissions', label: 'Permissions', type: 'custom', render: (r) => `<span class="t-clamp-2 cell-muted">${esc((r.permissions || []).join(', ') || 'None')}</span>` },
      { key: 'staff_count', label: 'Staff', type: 'number', numeric: true },
      { key: 'is_system', label: 'Built-in', type: 'boolean' },
    ],
    form: [
      { key: 'name', label: 'Role name', required: true, section: 'Role', maxLength: 80 },
      { key: 'description', label: 'Description', section: 'Role' },
      { key: 'permissions', label: 'Permissions granted', type: 'checklist', source: '/admin-panel/permissions/', valueKey: 'codename', labelKey: 'name', groupKey: 'group', section: 'Permissions',
        hint: 'Permissions are enforced by the server on every request.' },
    ],
  },

  /* ----------------------------------------------------------- audit logs */
  'audit-logs': {
    id: 'audit-logs', label: 'audit entries', singular: 'audit entry', endpoint: '/audit/logs/',
    exportable: true, emptyIcon: 'eye', labelKey: 'action', viewPermission: 'audit.view', searchable: false,
    columns: [
      { key: 'created_at', label: 'When', type: 'datetime' },
      { key: 'actor_email', label: 'Who', type: 'custom', render: (r) => esc(r.actor_email || 'System') },
      { key: 'action', label: 'Action', type: 'primary' },
      { key: 'entity_type', label: 'Record', type: 'custom', render: (r) => esc([r.entity_type, r.entity_id].filter(Boolean).join(' #') || '—') },
      { key: 'ip_address', label: 'IP address' },
    ],
    exportColumns: [
      { key: 'created_at', label: 'When' }, { key: 'actor_email', label: 'Actor' }, { key: 'action', label: 'Action' },
      { key: 'entity_type', label: 'Entity' }, { key: 'entity_id', label: 'Entity ID' }, { key: 'ip_address', label: 'IP' }, { key: 'data', label: 'Data' },
    ],
    filters: [
      { key: 'date_from', label: 'From', type: 'date' },
      { key: 'date_to', label: 'To', type: 'date' },
    ],
    rowActions: [{ id: 'view', label: 'View detail', icon: 'eye', handler: openAuditDialog }],
  },
};

/* ============================================================================
   Shared helpers
   ========================================================================== */

/** POST to an action route, toast the server message, reload the table. */
function simpleAction(urlFor, fallbackMessage) {
  return async (row, table) => {
    try {
      const result = await api.post(urlFor(row), {});
      api.invalidate();
      toast(result?.message || fallbackMessage, { type: 'success' });
      table.load();
    } catch (error) { toast(error.userMessage, { type: 'danger' }); }
  };
}

const CANCEL = '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button>';
const saveButton = (label, pending = 'Saving') => `<button type="button" class="btn btn--primary" data-save data-pending-label="${esc(pending)}">${esc(label)}</button>`;
const loadingBody = '<div class="stack" aria-hidden="true"><span class="sk sk--text sk--w-70"></span><span class="sk sk--text sk--w-50"></span><span class="sk sk--input"></span></div>';
const errorBody = (error) => `<div class="alert alert--danger" role="alert"><span class="alert__body">${esc(error?.userMessage || 'This could not be loaded.')}</span></div>`;
const meta = (label, value) => `<div><span class="order-meta__label">${esc(label)}</span><span class="order-meta__value">${value}</span></div>`;

/**
 * Small form dialog: renders `fields` HTML, runs `submit(values, form)` with
 * inline API errors, then closes and reloads the table.
 */
function formDialog({ title, sub, fields, saveLabel, pendingLabel, submit, success, table, size = 'narrow' }) {
  openDialog({
    title, sub, size,
    body: `<form class="stack" data-dialog-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>${fields}</form>`,
    footer: `${CANCEL}${saveButton(saveLabel, pendingLabel)}`,
    onMount({ element, close }) {
      const form = element.querySelector('[data-dialog-form]');
      const button = element.querySelector('[data-save]');
      hydrateIcons(element);
      const run = async () => {
        if (!form.reportValidity()) return;
        const values = Object.fromEntries(new FormData(form).entries());
        try {
          const result = await withSubmit(form, button, async () => submit(values, form));
          api.invalidate();
          close();
          toast(result?.message || success, { type: 'success' });
          table?.load();
        } catch { /* withSubmit shows the API error on the form */ }
      };
      form.addEventListener('submit', (event) => { event.preventDefault(); run(); });
      button.addEventListener('click', run);
    },
  });
}

/** An Error shaped like an ApiError so withSubmit can show it on the form. */
function formError(field, message) {
  const error = new Error(message);
  error.userMessage = message;
  error.fieldErrors = { [field]: [message] };
  return error;
}

/* ============================================================================
   Inventory
   ========================================================================== */

function stockSummary(row) {
  return `<p class="t-sm t-muted">On hand <strong>${esc(row.on_hand)}</strong> · reserved <strong>${esc(row.reserved)}</strong> · available <strong>${esc(row.available)}</strong></p>`;
}
const stockTitle = (row) => [row.product_name, row.variation_name].filter(Boolean).join(' — ');

function openStockDialog(row, table) {
  formDialog({
    title: 'Adjust stock', sub: stockTitle(row), table,
    fields: `${stockSummary(row)}
      <div class="field"><label class="field__label" for="st-delta">Adjustment</label>
        <input class="input" id="st-delta" name="delta" type="number" required step="1" placeholder="e.g. 10 or -2">
        <p class="field__hint">A positive number adds stock, a negative number removes it. Stock can never go below what is reserved for unpaid orders.</p>
        <p class="field__error" data-error-for="delta"></p></div>
      <div class="field"><label class="field__label" for="st-reason">Reason</label>
        <input class="input" id="st-reason" name="reason" required maxlength="255" placeholder="e.g. Stock count correction, damaged units">
        <p class="field__error" data-error-for="reason"></p></div>`,
    saveLabel: 'Apply adjustment',
    submit: (values) => {
      if (!Number(values.delta)) throw formError('delta', 'Enter a number other than zero.');
      return api.post(`/inventory/${row.id}/adjust/`, { delta: Number(values.delta), reason: values.reason.trim() });
    },
    success: 'Stock adjusted.',
  });
}

function openReceiveDialog(row, table) {
  formDialog({
    title: 'Receive stock', sub: stockTitle(row), table,
    fields: `${stockSummary(row)}
      <div class="field"><label class="field__label" for="rc-qty">Quantity received</label>
        <input class="input" id="rc-qty" name="quantity" type="number" required min="1" step="1">
        <p class="field__error" data-error-for="quantity"></p></div>
      <div class="field"><label class="field__label" for="rc-reason">Note</label>
        <input class="input" id="rc-reason" name="reason" maxlength="255" placeholder="e.g. Supplier delivery, invoice number">
        <p class="field__error" data-error-for="reason"></p></div>`,
    saveLabel: 'Receive stock',
    submit: (values) => api.post(`/inventory/${row.id}/receive/`, { quantity: Number(values.quantity), reason: (values.reason || '').trim() }),
    success: 'Stock received.',
  });
}

async function openMovementsDialog(row) {
  const dlg = openDialog({ title: 'Stock movements', sub: stockTitle(row), size: 'wide', body: loadingBody });
  try {
    const movements = normalizeList(await api.get(`/inventory/${row.id}/movements/`, { cache: false })).results;
    dlg.body.innerHTML = movements.length
      ? `<div class="table-wrap"><table class="table"><caption class="sr-only">Stock movements, newest first</caption>
          <thead><tr><th scope="col">When</th><th scope="col">Type</th><th scope="col" class="num">Change</th><th scope="col" class="num">On hand</th><th scope="col" class="num">Reserved</th><th scope="col">Order</th><th scope="col">By</th><th scope="col">Reason</th></tr></thead>
          <tbody>${movements.map((m) => `<tr>
            <td>${esc(formatDateTime(m.created_at))}</td><td>${esc(titleCase(m.movement_type))}</td>
            <td class="num">${m.quantity_change > 0 ? '+' : ''}${esc(m.quantity_change)}</td>
            <td class="num">${esc(m.on_hand_before)} → ${esc(m.on_hand_after)}</td>
            <td class="num">${esc(m.reserved_before)} → ${esc(m.reserved_after)}</td>
            <td>${esc(m.order_reference || '—')}</td><td>${esc(m.performed_by_email || 'System')}</td><td>${esc(m.reason || '—')}</td>
          </tr>`).join('')}</tbody></table></div>`
      : '<p class="t-sm t-muted">No stock movements have been recorded for this item yet.</p>';
  } catch (error) { dlg.body.innerHTML = errorBody(error); }
}

/* ============================================================================
   Products: images and variations
   ========================================================================== */

async function openProductImagesDialog(row, table) {
  const dlg = openDialog({ title: 'Product images', sub: row.name, size: 'wide', body: loadingBody });
  const base = `/products/admin/${row.id}`;
  const changed = () => { api.invalidate(); table.load(); };
  const render = async () => {
    let product;
    try { product = await api.get(`${base}/`, { cache: false, dedupe: false }); }
    catch (error) { dlg.body.innerHTML = errorBody(error); return; }
    const images = product.images || [];
    dlg.body.innerHTML = `<div class="stack stack--lg">
      <form class="stack" data-upload novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="field"><label class="field__label" for="pi-files">Add images</label>
          <input class="input" id="pi-files" name="images" type="file" accept="image/jpeg,image/png,image/webp" multiple required>
          <p class="field__hint">JPEG, PNG or WebP. Up to 10 files per upload.</p></div>
        <div class="field"><label class="field__label" for="pi-alt">Alt text for these images</label>
          <input class="input" id="pi-alt" name="alt_text" maxlength="255" placeholder="Describe the image for screen readers (defaults to the product name)"></div>
        <div><button type="submit" class="btn btn--primary btn--sm" data-pending-label="Uploading">${icon('upload', { size: 'sm' })} Upload</button></div>
      </form>
      ${images.length ? `<ul class="media-grid" aria-label="Current images">${images.map((image) => `<li class="media-card">
          <div class="media-card__thumb"><img src="${esc(image.url)}" alt="${esc(image.alt_text || '')}" loading="lazy" decoding="async"></div>
          <div class="media-card__body cluster cluster--between">
            ${image.is_main ? badge('success', 'Main image') : `<button type="button" class="link-btn" data-main="${esc(image.id)}">Set as main</button>`}
            <button type="button" class="link-btn" data-remove="${esc(image.id)}">Delete</button>
          </div></li>`).join('')}</ul>`
        : '<p class="t-sm t-muted">This product has no images yet. Products without images show a placeholder on the storefront.</p>'}
    </div>`;
    hydrateIcons(dlg.body);
    const form = dlg.body.querySelector('[data-upload]');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      try {
        await withSubmit(form, form.querySelector('button[type="submit"]'), () => api.upload(`${base}/images/`, new FormData(form)));
        toast('Images uploaded.', { type: 'success' });
        changed();
        render();
      } catch { /* shown on the form */ }
    });
    dlg.body.querySelectorAll('[data-main]').forEach((button) => button.addEventListener('click', async () => {
      try { await api.post(`${base}/images/${button.dataset.main}/set-main/`, {}); changed(); render(); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }));
    dlg.body.querySelectorAll('[data-remove]').forEach((button) => button.addEventListener('click', async () => {
      const ok = await confirmDialog({ title: 'Delete this image?', message: 'The image is removed from the product immediately.', confirmLabel: 'Delete', tone: 'danger' });
      if (!ok) return;
      try { await api.delete(`${base}/images/${button.dataset.remove}/`); changed(); render(); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }));
  };
  render();
}

const optionsToText = (options) => (options && typeof options === 'object' ? Object.entries(options).map(([k, v]) => `${k}: ${v}`).join(', ') : '');
const textToOptions = (text) => Object.fromEntries(String(text || '').split(',')
  .map((pair) => pair.split(/:(.*)/s).slice(0, 2).map((part) => (part || '').trim()))
  .filter(([key, value]) => key && value));

async function openVariationsDialog(row, table) {
  const dlg = openDialog({ title: 'Product variations', sub: row.name, size: 'wide', body: loadingBody });
  const base = `/products/admin/${row.id}`;

  const editVariation = (variation, reload) => {
    formDialog({
      title: variation ? 'Edit variation' : 'New variation', sub: row.name, size: 'default',
      fields: `<div class="form-grid">
        <div class="field"><label class="field__label" for="vr-sku">SKU</label>
          <input class="input" id="vr-sku" name="sku" required maxlength="80" value="${esc(variation?.sku || '')}"><p class="field__error" data-error-for="sku"></p></div>
        <div class="field"><label class="field__label" for="vr-name">Label</label>
          <input class="input" id="vr-name" name="name" maxlength="150" value="${esc(variation?.name || '')}" placeholder="e.g. Medium / Black"><p class="field__error" data-error-for="name"></p></div>
        <div class="field form-grid__full"><label class="field__label" for="vr-options">Options</label>
          <input class="input" id="vr-options" name="options" required value="${esc(optionsToText(variation?.options))}" placeholder="Size: M, Colour: Black">
          <p class="field__hint">Comma-separated “Option: value” pairs. Customers choose from these on the product page.</p><p class="field__error" data-error-for="options"></p></div>
        <div class="field"><label class="field__label" for="vr-price">Fixed price (NGN)</label>
          <input class="input" id="vr-price" name="price" type="number" min="0" step="0.01" value="${esc(variation?.price ?? '')}">
          <p class="field__hint">Leave blank to use the product price.</p><p class="field__error" data-error-for="price"></p></div>
        <div class="field"><label class="field__label" for="vr-adj">Or price adjustment (NGN)</label>
          <input class="input" id="vr-adj" name="price_adjustment" type="number" step="0.01" value="${esc(variation?.price_adjustment ?? '')}">
          <p class="field__hint">Added to the product price. Use one or the other, not both.</p><p class="field__error" data-error-for="price_adjustment"></p></div>
        ${variation ? '' : `<div class="field"><label class="field__label" for="vr-stock">Opening stock</label>
          <input class="input" id="vr-stock" name="stock_quantity" type="number" min="0" step="1" value="0"></div>`}
        <div class="field"><label class="switch"><input type="checkbox" name="is_available" ${!variation || variation.is_available ? 'checked' : ''}><span class="switch__track"></span><span>Available for sale</span></label></div>
      </div>`,
      saveLabel: variation ? 'Save variation' : 'Add variation',
      submit: (values, form) => {
        const options = textToOptions(values.options);
        if (!Object.keys(options).length) throw formError('options', 'Enter at least one option as “Name: value”, for example “Size: M”.');
        if (values.price !== '' && values.price_adjustment !== '') throw formError('price_adjustment', 'Use a fixed price or an adjustment, not both.');
        const body = {
          sku: values.sku.trim(), name: (values.name || '').trim(), options,
          price: values.price === '' ? null : values.price,
          price_adjustment: values.price_adjustment === '' ? null : values.price_adjustment,
          is_available: form.elements.is_available.checked,
        };
        if (variation) body.id = variation.id;
        else body.stock_quantity = Number(values.stock_quantity || 0);
        return api.post(`${base}/variations/`, body);
      },
      success: 'Variation saved.',
      table: { load: reload },
    });
  };

  const render = async () => {
    let product;
    try { product = await api.get(`${base}/`, { cache: false, dedupe: false }); }
    catch (error) { dlg.body.innerHTML = errorBody(error); return; }
    const variations = product.variations || [];
    dlg.body.innerHTML = `<div class="stack">
      <div class="cluster cluster--between">
        <p class="t-sm t-muted">Variations are the purchasable options of a product (size, colour…). Each has its own SKU and stock.</p>
        <button type="button" class="btn btn--primary btn--sm" data-add>${icon('plus', { size: 'sm' })} Add variation</button>
      </div>
      ${variations.length ? `<div class="table-wrap"><table class="table"><caption class="sr-only">Variations</caption>
        <thead><tr><th scope="col">Variation</th><th scope="col">Options</th><th scope="col" class="num">Price</th><th scope="col" class="num">Available stock</th><th scope="col">For sale</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${variations.map((v) => `<tr>
          <td><span class="cell-stack"><span class="table__primary">${esc(v.display_name || v.name || v.sku)}</span><span class="cell-muted">${esc(v.sku)}</span></span></td>
          <td>${esc(optionsToText(v.options) || '—')}</td>
          <td class="num">${esc(formatMoney(v.effective_price))}</td>
          <td class="num">${esc(v.stock?.available ?? '—')}</td>
          <td>${v.is_available ? badge('success', 'Yes') : badge('neutral', 'No')}</td>
          <td class="table__actions"><span class="row-actions">
            <button type="button" class="row-action" data-edit-variation="${esc(v.id)}" aria-label="Edit ${esc(v.sku)}">${icon('edit', { size: 'sm' })}</button>
            <button type="button" class="row-action row-action--danger" data-delete-variation="${esc(v.id)}" aria-label="Delete ${esc(v.sku)}">${icon('trash', { size: 'sm' })}</button>
          </span></td></tr>`).join('')}</tbody></table></div>
        <p class="t-xs t-muted">Change variation stock from Inventory so every movement is recorded.</p>`
        : '<p class="t-sm t-muted">This product has no variations. It is sold as a single item with its own stock.</p>'}
    </div>`;
    hydrateIcons(dlg.body);
    const reload = () => { table.load(); render(); };
    dlg.body.querySelector('[data-add]').addEventListener('click', () => editVariation(null, reload));
    dlg.body.querySelectorAll('[data-edit-variation]').forEach((button) => button.addEventListener('click', () => {
      editVariation(variations.find((v) => String(v.id) === button.dataset.editVariation), reload);
    }));
    dlg.body.querySelectorAll('[data-delete-variation]').forEach((button) => button.addEventListener('click', async () => {
      const ok = await confirmDialog({ title: 'Delete this variation?', message: 'Variations that appear on past orders are marked unavailable instead of being deleted.', confirmLabel: 'Delete', tone: 'danger' });
      if (!ok) return;
      try {
        const result = await api.delete(`${base}/variations/${button.dataset.deleteVariation}/`);
        api.invalidate();
        toast(result?.message || 'Variation deleted.', { type: 'success' });
        reload();
      } catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }));
  };
  render();
}

/* ============================================================================
   Orders
   ========================================================================== */

async function openOrderDialog(row) {
  const dlg = openDialog({ title: `Order ${row.reference}`, size: 'wide', body: loadingBody });
  const url = `/orders/admin/${encodeURIComponent(row.reference)}/`;
  const render = async () => {
    try {
      const raw = await api.get(url, { cache: false, dedupe: false });
      const { renderOrderDetail, normalizeOrder } = await import('../orders.js');
      const history = raw.status_history || [];
      const payments = raw.payments || [];
      dlg.body.innerHTML = `<div class="stack stack--lg">
        ${renderOrderDetail(normalizeOrder(raw), { staff: true })}
        <section aria-labelledby="od-payments"><h3 class="t-sm t-semibold" id="od-payments">Payments</h3>
          ${payments.length ? `<div class="table-wrap"><table class="table"><thead><tr><th scope="col">Reference</th><th scope="col">Status</th><th scope="col">Channel</th><th scope="col" class="num">Amount</th><th scope="col">Verified</th></tr></thead>
            <tbody>${payments.map((p) => `<tr><td>${esc(p.reference || p.provider_reference || '')}</td><td>${badge(PAY_TONES[p.status] || 'neutral', titleCase(p.status || ''))}</td><td>${esc(p.channel || '—')}</td><td class="num">${esc(formatMoney(p.amount, p.currency || 'NGN'))}</td><td>${esc(p.verified_at ? formatDateTime(p.verified_at) : '—')}</td></tr>`).join('')}</tbody></table></div>`
            : '<p class="t-sm t-muted">No payment attempt has been recorded for this order.</p>'}
        </section>
        <section aria-labelledby="od-history"><h3 class="t-sm t-semibold" id="od-history">Status history</h3>
          ${history.length ? `<ol class="stack stack--sm t-sm">${history.map((h) => `<li><strong>${esc(titleCase(h.to_status || h.status || ''))}</strong>
            <span class="t-muted"> · ${esc(formatDateTime(h.created_at))} · ${esc(h.actor_email || h.actor || 'System')}</span>${h.note ? `<br><span>${esc(h.note)}</span>` : ''}</li>`).join('')}</ol>`
            : '<p class="t-sm t-muted">No status changes recorded yet.</p>'}
        </section>
        <section aria-labelledby="od-notes"><h3 class="t-sm t-semibold" id="od-notes">Internal notes</h3>
          ${raw.internal_notes ? `<div class="panel"><p class="t-sm" style="white-space:pre-wrap">${esc(raw.internal_notes)}</p></div>` : '<p class="t-sm t-muted">No internal notes. Notes are never shown to the customer.</p>'}
          <form class="stack stack--sm" data-note-form novalidate data-perm="orders.manage">
            <div class="alert alert--danger" data-form-error hidden role="alert"></div>
            <label class="sr-only" for="od-note">Add an internal note</label>
            <textarea class="textarea" id="od-note" name="note" rows="2" required maxlength="1000" placeholder="Add an internal note"></textarea>
            <div><button type="submit" class="btn btn--secondary btn--sm" data-pending-label="Saving">Add note</button></div>
          </form>
        </section>
      </div>`;
      hydrateIcons(dlg.body);
      const { applyPermissions } = await import('./admin-core.js');
      applyPermissions(dlg.body);
      const form = dlg.body.querySelector('[data-note-form]');
      form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        try {
          await withSubmit(form, form.querySelector('button'), () => api.post(`${url}notes/`, { note: form.elements.note.value.trim() }));
          toast('Note added.', { type: 'success' });
          render();
        } catch { /* shown on the form */ }
      });
    } catch (error) { dlg.body.innerHTML = errorBody(error); }
  };
  await render();
}

function openOrderStatusDialog(row, table) {
  formDialog({
    title: 'Update order status', sub: row.reference, table,
    fields: `<p class="t-sm t-muted">Current status: <strong>${esc(titleCase(row.status))}</strong>. Payment and refund statuses are set automatically by Paystack verification and cannot be changed here.</p>
      <div class="field"><label class="field__label" for="os-status">New status</label>
        <select class="select" id="os-status" name="status" required>${STAFF_SETTABLE_ORDER_STATUSES.map((s) => `<option value="${s}" ${row.status === s ? 'selected' : ''}>${esc(titleCase(s))}</option>`).join('')}</select>
        <p class="field__error" data-error-for="status"></p></div>
      <div class="field"><label class="field__label" for="os-tracking">Tracking reference</label>
        <input class="input" id="os-tracking" name="tracking_reference" maxlength="120" value="${esc(row.delivery?.tracking_reference || '')}">
        <p class="field__error" data-error-for="tracking_reference"></p></div>
      <div class="field"><label class="field__label" for="os-note">Note</label>
        <textarea class="textarea" id="os-note" name="note" rows="2" maxlength="500"></textarea>
        <p class="field__hint">Recorded in the status history. The customer is emailed about the status change.</p></div>`,
    saveLabel: 'Update order', pendingLabel: 'Updating',
    submit: (values) => api.post(orderStatusUrl(row), {
      status: values.status, note: (values.note || '').trim(), tracking_reference: (values.tracking_reference || '').trim(),
    }),
    success: 'Order updated.',
  });
}

/** Opens a print-ready receipt built from the server's receipt data. */
async function printReceipt(row) {
  // Open the window synchronously so pop-up blockers treat it as user-initiated.
  const win = window.open('', '_blank', 'width=860,height=900');
  if (!win) { toast('Allow pop-ups for this site to print receipts.', { type: 'danger' }); return; }
  win.document.write('<p style="font:14px system-ui;margin:32px">Preparing receipt…</p>');
  let data;
  try { data = await api.get(`/orders/admin/${encodeURIComponent(row.reference)}/receipt/`, { cache: false }); }
  catch (error) { win.close(); toast(error.userMessage, { type: 'danger' }); return; }
  const order = data.order || data;
  const business = data.business || {};
  const totals = order.totals || {};
  const currency = totals.currency || order.currency || 'NGN';
  const money = (value) => esc(formatMoney(value ?? 0, currency));
  const delivery = order.delivery || {};
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Receipt ${esc(order.reference)}</title>
  <style>
    body{font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#16131f;margin:32px auto;max-width:760px;padding:0 16px}
    h1{font-size:20px;margin:0 0 4px} h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#5b566b;margin:24px 0 6px}
    table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #e4e1ec;vertical-align:top}
    .num{text-align:right;white-space:nowrap} .muted{color:#5b566b} .totals td{border:0;padding:3px 6px} .totals tr:last-child td{font-weight:700;border-top:2px solid #16131f;padding-top:8px}
    .head{display:flex;justify-content:space-between;gap:24px;border-bottom:2px solid #16131f;padding-bottom:16px}
    @media print{body{margin:0 auto} .no-print{display:none}}
  </style></head><body>
  <div class="head"><div><h1>${esc(business.business_name || 'STARMOND TECHNOLOGY LIMITED')}</h1>
    <div class="muted">${esc(business.business_address || '')}</div>
    <div class="muted">${esc([business.contact_email, business.contact_phone].filter(Boolean).join(' · '))}</div></div>
    <div style="text-align:right"><strong>Receipt</strong><br>${esc(order.reference)}<br><span class="muted">${esc(formatDateTime(order.paid_at || order.placed_at))}</span></div></div>
  <h2>Delivered to</h2>
  <div>${esc(delivery.full_name || '')}<br>${esc([delivery.street, delivery.details].filter(Boolean).join(', '))}<br>${esc([delivery.city, delivery.state].filter(Boolean).join(', '))}<br>
    <span class="muted">${esc([order.contact?.email, delivery.phone || order.contact?.phone].filter(Boolean).join(' · '))}</span></div>
  <h2>Items</h2>
  <table><thead><tr><th>Item</th><th class="num">Unit price</th><th class="num">Qty</th><th class="num">Total</th></tr></thead><tbody>
    ${(order.items || []).map((item) => `<tr><td>${esc(item.product_name)}${item.variation_label ? `<br><span class="muted">${esc(item.variation_label)}</span>` : ''}<br><span class="muted">SKU ${esc(item.sku || '')}</span></td>
      <td class="num">${money(item.unit_price)}</td><td class="num">${esc(item.quantity)}</td><td class="num">${money(item.line_total)}</td></tr>`).join('')}
  </tbody></table>
  <table class="totals" style="margin-top:12px;margin-left:auto;width:320px">
    <tr><td>Subtotal</td><td class="num">${money(totals.subtotal)}</td></tr>
    ${Number(totals.discount) > 0 ? `<tr><td>Discount</td><td class="num">−${money(totals.discount)}</td></tr>` : ''}
    <tr><td>Delivery${delivery.method ? ` (${esc(delivery.method)})` : ''}</td><td class="num">${money(totals.shipping_fee)}</td></tr>
    ${Number(totals.refunded) > 0 ? `<tr><td>Refunded</td><td class="num">−${money(totals.refunded)}</td></tr>` : ''}
    <tr><td>Total</td><td class="num">${money(totals.total)}</td></tr>
  </table>
  <h2>Payment</h2>
  ${(data.payments || []).length ? `<table><tbody>${data.payments.map((p) => `<tr><td>${esc(titleCase(p.provider || ''))}${p.channel ? ` · ${esc(p.channel)}` : ''}</td><td>${esc(p.provider_reference || p.reference || '')}</td><td>${esc(p.verified_at ? formatDateTime(p.verified_at) : '')}</td><td class="num">${esc(formatMoney(p.amount, p.currency || currency))}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No successful payment is recorded for this order.</p>'}
  ${(data.refunds || []).length ? `<h2>Refunds</h2><table><tbody>${data.refunds.map((r) => `<tr><td>${esc(r.reference)}</td><td>${esc(r.processed_at ? formatDateTime(r.processed_at) : '')}</td><td class="num">${esc(formatMoney(r.amount, currency))}</td></tr>`).join('')}</tbody></table>` : ''}
  <p class="no-print" style="margin-top:24px"><button onclick="window.print()">Print</button></p>
  </body></html>`;
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
}

/* ============================================================================
   Payments, refunds, reviews
   ========================================================================== */

function openPaymentDialog(row) {
  openDialog({
    title: `Payment ${row.reference}`, sub: `Order ${row.order_reference || '—'}`,
    body: `<div class="stack">
      <div class="order-meta-grid">
        ${meta('Status', badge(PAY_TONES[row.status] || 'neutral', titleCase(row.status)))}
        ${meta('Amount', esc(formatMoney(row.amount, row.currency || 'NGN')))}
        ${meta('Order total', esc(row.order_total != null ? formatMoney(row.order_total, row.currency || 'NGN') : '—'))}
        ${meta('Channel', esc(row.channel || '—'))}
        ${meta('Provider', esc(titleCase(row.provider || '')))}
        ${meta('Provider reference', esc(row.provider_reference || '—'))}
        ${meta('Started', esc(row.initialized_at ? formatDateTime(row.initialized_at) : '—'))}
        ${meta('Verified', esc(row.verified_at ? formatDateTime(row.verified_at) : 'Not verified'))}
      </div>
      ${row.failure_reason ? `<div class="alert alert--danger"><span class="alert__body">${esc(row.failure_reason)}</span></div>` : ''}
      <p class="t-xs t-muted">A payment is only marked successful after the server confirms the amount and currency with Paystack.</p>
    </div>`,
  });
}

function refundDecision(action) {
  return (row, table) => {
    const approve = action === 'approve';
    formDialog({
      title: approve ? 'Approve refund' : 'Reject refund', sub: `${row.order_reference} · ${row.reference}`, table,
      fields: `<div class="panel"><p class="t-xs t-semibold t-upper">Customer’s reason</p><p class="t-sm" style="white-space:pre-wrap">${esc(row.reason || '—')}</p></div>
        ${approve ? `<div class="field"><label class="field__label" for="rf-amount">Amount to refund (NGN)</label>
          <input class="input" id="rf-amount" name="approved_amount" type="number" min="0.01" step="0.01" required value="${esc(row.requested_amount || '')}">
          <p class="field__hint">Requested: ${esc(formatMoney(row.requested_amount))}. The refund is sent to Paystack and cannot exceed what was paid.</p>
          <p class="field__error" data-error-for="approved_amount"></p></div>` : ''}
        <div class="field"><label class="field__label" for="rf-notes">${approve ? 'Notes' : 'Reason for rejecting'}</label>
          <textarea class="textarea" id="rf-notes" name="notes" rows="3" maxlength="1000" ${approve ? '' : 'required'}></textarea>
          <p class="field__error" data-error-for="notes"></p></div>`,
      saveLabel: approve ? 'Approve and refund' : 'Reject request', pendingLabel: 'Submitting',
      submit: (values) => api.post(`/refunds/admin/${row.id}/${action}/`, approve
        ? { approved_amount: values.approved_amount, notes: (values.notes || '').trim() }
        : { notes: (values.notes || '').trim() }),
      success: approve ? 'Refund approved.' : 'Refund request rejected.',
    });
  };
}

function reviewReject(row, table) {
  formDialog({
    title: 'Reject review', sub: row.product_name, table,
    fields: `<div class="panel"><p class="t-sm" style="white-space:pre-wrap">${esc(row.body || '')}</p></div>
      <div class="field"><label class="field__label" for="rv-note">Moderator note (internal)</label>
        <textarea class="textarea" id="rv-note" name="note" rows="2" maxlength="500"></textarea></div>`,
    saveLabel: 'Reject review',
    submit: (values) => api.post(`/reviews/admin/${row.id}/reject/`, { note: (values.note || '').trim() }),
    success: 'Review rejected.',
  });
}

/* ============================================================================
   Enquiries, email log, audit log
   ========================================================================== */

function openEnquiryDialog(row, table) {
  const mailto = `mailto:${encodeURIComponent(row.email)}?subject=${encodeURIComponent(`Re: ${row.subject || 'Your enquiry'}`)}`;
  formDialog({
    title: row.subject || 'Enquiry', sub: `${row.full_name} · ${row.email}${row.phone ? ` · ${row.phone}` : ''}`, size: 'default', table,
    fields: `<div class="panel"><p class="t-sm" style="white-space:pre-wrap">${esc(row.message || '')}</p></div>
      <p class="t-sm t-muted">Received ${esc(formatDateTime(row.created_at))}${row.order_reference ? ` · Order <strong>${esc(row.order_reference)}</strong>` : ''}${row.handled_by_email ? ` · Handled by ${esc(row.handled_by_email)}` : ''}</p>
      <p><a class="btn btn--secondary btn--sm" href="${esc(mailto)}">${icon('mail', { size: 'sm' })} Reply by email</a></p>
      <div class="field"><label class="field__label" for="en-status">Status</label>
        <select class="select" id="en-status" name="status">${['new', 'in_progress', 'resolved'].map((s) => `<option value="${s}" ${row.status === s ? 'selected' : ''}>${esc(titleCase(s))}</option>`).join('')}</select></div>
      <div class="field"><label class="field__label" for="en-note">Internal response note</label>
        <textarea class="textarea" id="en-note" name="response_note" rows="3" maxlength="2000" placeholder="What was done or said — visible to staff only">${esc(row.response_note || '')}</textarea>
        <p class="field__hint">Replies are sent from your own email client; this note records the outcome.</p></div>`,
    saveLabel: 'Save',
    submit: (values) => api.patch(`/notifications/enquiries/admin/${row.id}/`, { status: values.status, response_note: (values.response_note || '').trim() }),
    success: 'Enquiry updated.',
  });
}

function openEmailDialog(row) {
  openDialog({
    title: row.subject || 'Email', sub: `To ${row.recipient}`,
    body: `<div class="stack">
      <div class="order-meta-grid">
        ${meta('Status', badge({ sent: 'success', queued: 'warning', failed: 'danger' }[row.status] || 'neutral', titleCase(row.status)))}
        ${meta('Template', esc(row.template_key || '—'))}
        ${meta('Order', esc(row.order_reference || '—'))}
        ${meta('Attempts', esc(row.attempts ?? 0))}
        ${meta('Created', esc(formatDateTime(row.created_at)))}
        ${meta('Sent', esc(row.sent_at ? formatDateTime(row.sent_at) : 'Not sent'))}
      </div>
      ${row.last_error ? `<div class="alert alert--danger" role="alert"><span class="alert__body"><strong>Last error:</strong> ${esc(row.last_error)}</span></div>` : ''}
      <p class="t-xs t-muted">Message bodies are not stored in the log. Failed emails are retried by the background worker.</p>
    </div>`,
  });
}

function openAuditDialog(row) {
  openDialog({
    title: row.action, sub: `${row.actor_email || 'System'} · ${formatDateTime(row.created_at)}`, size: 'wide',
    body: `<div class="stack">
      <div class="order-meta-grid">
        ${meta('Record', esc([row.entity_type, row.entity_id].filter(Boolean).join(' #') || '—'))}
        ${meta('IP address', esc(row.ip_address || '—'))}
      </div>
      <div><p class="t-xs t-semibold t-upper" style="margin-bottom:.25rem">Recorded detail</p>
        <pre class="audit-diff">${esc(JSON.stringify(row.data ?? {}, null, 2))}</pre></div>
      <p class="t-meta">User agent: ${esc(row.user_agent || '—')}</p>
    </div>`,
  });
}

export default MODULES;
