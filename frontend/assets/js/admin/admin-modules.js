/**
 * admin-modules.js — declarative configuration for every CRUD module.
 *
 * Each config maps to a documented REST resource (see docs/API_CONTRACT.md).
 * Endpoints are relative to the configured API base; nothing is hardcoded to a
 * host. If a backend endpoint is missing the module shows the API error rather
 * than inventing data.
 */

import api from '../api.js';
import { toast, confirmDialog, openDialog } from '../ui.js';
import { icon } from '../icons.js';
import { esc, formatMoney, formatDateTime } from '../utils.js';

const ORDER_STATUSES = ['pending_payment', 'paid', 'processing', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'completed', 'cancelled', 'refunded'];
const PAYMENT_STATUSES = ['pending', 'success', 'failed', 'abandoned', 'reversed', 'refunded', 'partially_refunded'];

const statusOptions = (values) => values.map((value) => ({ value, label: value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }));

export const MODULES = {
  /* ------------------------------------------------------------- products */
  products: {
    id: 'products', label: 'products', singular: 'product', createLabel: 'New product',
    endpoint: '/admin/products/', archiveLabel: 'archive', deletable: true, exportable: true,
    defaultOrdering: '-created_at', emptyIcon: 'package',
    emptyText: 'Create your first product to start selling.',
    permissions: { create: 'products.create', update: 'products.update', delete: 'products.archive' },
    viewUrl: (row) => `/products/${row.slug}/`,
    columns: [
      { key: 'name', label: 'Product', type: 'image', resolve: (r) => r.image_url || r.images?.[0]?.url, subKey: 'sku', sortable: true },
      { key: 'category.name', label: 'Category' },
      { key: 'price', label: 'Price', type: 'money', numeric: true, sortable: true },
      { key: 'stock_quantity', label: 'Stock', type: 'number', numeric: true, sortable: true },
      { key: 'status', label: 'Status', type: 'status', tones: { active: 'success', draft: 'neutral', archived: 'warning', out_of_stock: 'danger' } },
      { key: 'is_featured', label: 'Featured', type: 'boolean' },
    ],
    filters: [
      { key: 'category', label: 'All categories', type: 'select', source: '/categories/', valueKey: 'id', labelKey: 'name' },
      { key: 'status', label: 'All statuses', type: 'select', options: ['active', 'draft', 'archived'] },
      { key: 'stock', label: 'Any stock', type: 'select', options: [{ value: 'low', label: 'Low stock' }, { value: 'out', label: 'Out of stock' }, { value: 'in', label: 'In stock' }] },
    ],
    bulkActions: [
      { id: 'publish', label: 'Publish', perm: 'products.update' },
      { id: 'archive', label: 'Archive', tone: 'danger', perm: 'products.archive' },
      { id: 'feature', label: 'Feature', perm: 'products.update' },
    ],
    rowActions: [
      { id: 'inventory', label: 'Adjust stock', icon: 'clipboard', perm: 'inventory.update', handler: openStockDialog },
    ],
    form: [
      { key: 'name', label: 'Product name', required: true, section: 'Basics', full: true, maxLength: 200 },
      { key: 'slug', label: 'URL slug', section: 'Basics', hint: 'Leave blank to generate from the name.' },
      { key: 'sku', label: 'SKU', section: 'Basics', required: true },
      { key: 'category', label: 'Category', type: 'select', source: '/categories/', required: true, section: 'Basics' },
      { key: 'brand', label: 'Brand', type: 'select', source: '/brands/', section: 'Basics' },
      { key: 'short_description', label: 'Short description', type: 'textarea', rows: 2, section: 'Basics', full: true, maxLength: 300 },
      { key: 'description', label: 'Full description', type: 'richtext', section: 'Basics' },
      { key: 'price', label: 'Price (NGN)', type: 'money', required: true, section: 'Pricing & stock' },
      { key: 'compare_at_price', label: 'Compare-at price (NGN)', type: 'money', section: 'Pricing & stock', hint: 'Original price shown struck through when higher than the price.' },
      { key: 'cost_price', label: 'Cost price (NGN)', type: 'money', section: 'Pricing & stock' },
      { key: 'stock_quantity', label: 'Stock quantity', type: 'number', min: 0, section: 'Pricing & stock' },
      { key: 'low_stock_threshold', label: 'Low-stock threshold', type: 'number', min: 0, section: 'Pricing & stock' },
      { key: 'track_inventory', label: 'Track inventory', type: 'switch', default: true, section: 'Pricing & stock' },
      { key: 'allow_backorder', label: 'Allow backorder', type: 'switch', section: 'Pricing & stock' },
      { key: 'max_quantity_per_order', label: 'Max quantity per order', type: 'number', min: 1, section: 'Pricing & stock' },
      { key: 'image', label: 'Main image', type: 'image', altKey: 'image_alt', section: 'Media', full: true },
      { key: 'images', label: 'Additional images', type: 'images', section: 'Media' },
      { key: 'status', label: 'Status', type: 'select', options: ['draft', 'active', 'archived'], default: 'draft', section: 'Publishing' },
      { key: 'is_featured', label: 'Featured product', type: 'switch', section: 'Publishing' },
      { key: 'tags', label: 'Tags', type: 'tags', section: 'Publishing', full: true },
      { key: 'seo_title', label: 'SEO title', section: 'SEO', full: true, maxLength: 70 },
      { key: 'seo_description', label: 'SEO description', type: 'textarea', rows: 2, section: 'SEO', full: true, maxLength: 160 },
    ],
  },

  /* ----------------------------------------------------------- categories */
  categories: {
    id: 'categories', label: 'categories', singular: 'category', createLabel: 'New category',
    endpoint: '/admin/categories/', deletable: true, exportable: false, defaultOrdering: 'order',
    emptyIcon: 'folder', permissions: { create: 'categories.create', update: 'categories.update', delete: 'categories.delete' },
    extraParams: { top_level: 1 },
    viewUrl: (row) => `/shop/${row.slug}/`,
    columns: [
      { key: 'name', label: 'Category', type: 'image', resolve: (r) => r.image_url, subKey: 'slug', sortable: true },
      { key: 'product_count', label: 'Products', type: 'number', numeric: true },
      { key: 'order', label: 'Order', type: 'number', numeric: true, sortable: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'is_active', label: 'Any status', type: 'select', options: [{ value: '1', label: 'Active' }, { value: '0', label: 'Inactive' }] }],
    bulkActions: [{ id: 'activate', label: 'Activate', perm: 'categories.update' }, { id: 'deactivate', label: 'Deactivate', perm: 'categories.update' }],
    form: [
      { key: 'name', label: 'Category name', required: true, section: 'Details' },
      { key: 'slug', label: 'URL slug', section: 'Details' },
      { key: 'parent', label: 'Parent category', type: 'select', source: '/categories/', section: 'Details', hint: 'Leave empty for a top-level department.' },
      { key: 'order', label: 'Display order', type: 'number', min: 0, default: 0, section: 'Details' },
      { key: 'short_description', label: 'Short description', type: 'textarea', rows: 2, section: 'Details', full: true, maxLength: 200 },
      { key: 'description', label: 'Description', type: 'richtext', section: 'Details' },
      { key: 'image', label: 'Category image', type: 'image', altKey: 'image_alt', section: 'Media', full: true },
      { key: 'banner', label: 'Banner image', type: 'image', altKey: 'banner_alt', section: 'Media', full: true },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Publishing' },
      { key: 'seo_title', label: 'SEO title', section: 'SEO', full: true, maxLength: 70 },
      { key: 'seo_description', label: 'SEO description', type: 'textarea', rows: 2, section: 'SEO', full: true, maxLength: 160 },
    ],
  },

  /* -------------------------------------------------------- subcategories */
  subcategories: {
    id: 'subcategories', label: 'subcategories', singular: 'subcategory', createLabel: 'New subcategory',
    endpoint: '/admin/categories/', deletable: true, defaultOrdering: 'parent,order', emptyIcon: 'layers',
    extraParams: { has_parent: 1 },
    permissions: { create: 'categories.create', update: 'categories.update', delete: 'categories.delete' },
    columns: [
      { key: 'name', label: 'Subcategory', type: 'primary', subKey: 'slug', sortable: true },
      { key: 'parent.name', label: 'Parent' },
      { key: 'product_count', label: 'Products', type: 'number', numeric: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'parent', label: 'All parents', type: 'select', source: '/categories/', sourceParams: { top_level: 1, page_size: 100 } }],
    form: [
      { key: 'name', label: 'Subcategory name', required: true, section: 'Details' },
      { key: 'parent', label: 'Parent category', type: 'select', source: '/categories/', required: true, section: 'Details' },
      { key: 'slug', label: 'URL slug', section: 'Details' },
      { key: 'order', label: 'Display order', type: 'number', min: 0, section: 'Details' },
      { key: 'description', label: 'Description', type: 'richtext', section: 'Details' },
      { key: 'image', label: 'Image', type: 'image', altKey: 'image_alt', section: 'Media', full: true },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Publishing' },
    ],
  },

  /* ----------------------------------------------------------- variations */
  variations: {
    id: 'variations', label: 'variations', singular: 'variation', createLabel: 'New variation',
    endpoint: '/admin/variations/', deletable: true, emptyIcon: 'grid',
    permissions: { create: 'products.create', update: 'products.update', delete: 'products.delete' },
    columns: [
      { key: 'label', label: 'Variation', type: 'primary', subKey: 'sku', sortable: true },
      { key: 'product.name', label: 'Product' },
      { key: 'price', label: 'Price', type: 'money', numeric: true },
      { key: 'stock_quantity', label: 'Stock', type: 'number', numeric: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'product', label: 'All products', type: 'select', source: '/admin/products/', sourceParams: { page_size: 200 } }],
    form: [
      { key: 'product', label: 'Product', type: 'select', source: '/admin/products/', required: true, section: 'Variation', sourceParams: { page_size: 200 } },
      { key: 'sku', label: 'SKU', required: true, section: 'Variation' },
      { key: 'size', label: 'Size', section: 'Options' },
      { key: 'color', label: 'Colour', section: 'Options' },
      { key: 'material', label: 'Material', section: 'Options' },
      { key: 'custom_option', label: 'Other option', section: 'Options', hint: 'Any additional option value, e.g. 2.5mm.' },
      { key: 'price', label: 'Price override (NGN)', type: 'money', section: 'Pricing & stock', hint: 'Leave blank to inherit the product price.' },
      { key: 'stock_quantity', label: 'Stock quantity', type: 'number', min: 0, section: 'Pricing & stock' },
      { key: 'image', label: 'Variation image', type: 'image', altKey: 'image_alt', section: 'Media', full: true },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Publishing' },
    ],
  },

  /* ------------------------------------------------------------ inventory */
  inventory: {
    id: 'inventory', label: 'inventory records', singular: 'inventory record',
    endpoint: '/admin/inventory/', exportable: true, emptyIcon: 'clipboard', defaultOrdering: 'stock_quantity',
    permissions: { update: 'inventory.update' },
    columns: [
      { key: 'product.name', label: 'Product', type: 'primary', subKey: 'sku', sortable: true },
      { key: 'variation_label', label: 'Variation' },
      { key: 'stock_quantity', label: 'On hand', type: 'number', numeric: true, sortable: true },
      { key: 'reserved_quantity', label: 'Reserved', type: 'number', numeric: true },
      { key: 'available_quantity', label: 'Available', type: 'number', numeric: true },
      { key: 'stock_status', label: 'Status', type: 'status', tones: { in_stock: 'success', low_stock: 'warning', out_of_stock: 'danger', backorder: 'info' } },
    ],
    filters: [{ key: 'stock', label: 'All stock levels', type: 'select', options: [{ value: 'low', label: 'Low stock' }, { value: 'out', label: 'Out of stock' }, { value: 'in', label: 'In stock' }] }],
    rowActions: [{ id: 'adjust', label: 'Adjust stock', icon: 'edit', perm: 'inventory.update', handler: openStockDialog }],
    bulkActions: [{ id: 'restock', label: 'Bulk restock', perm: 'inventory.update' }],
  },

  /* --------------------------------------------------------------- orders */
  orders: {
    id: 'orders', label: 'orders', singular: 'order', endpoint: '/admin/orders/', exportable: true,
    defaultOrdering: '-created_at', emptyIcon: 'receipt',
    permissions: { update: 'orders.update' },
    labelKey: 'reference',
    viewUrl: (row) => `/admin/orders.html?ref=${encodeURIComponent(row.reference)}`,
    columns: [
      { key: 'reference', label: 'Reference', type: 'primary', subKey: 'created_at', sortable: true },
      { key: 'customer.email', label: 'Customer' },
      { key: 'total', label: 'Total', type: 'money', numeric: true, sortable: true },
      { key: 'payment_status', label: 'Payment', type: 'status', tones: { success: 'success', paid: 'success', pending: 'warning', failed: 'danger', abandoned: 'neutral', refunded: 'neutral' } },
      { key: 'fulfilment_status', label: 'Fulfilment', type: 'status', tones: { delivered: 'success', completed: 'success', shipped: 'info', processing: 'info', pending_payment: 'warning', cancelled: 'danger' } },
      { key: 'created_at', label: 'Placed', type: 'datetime', sortable: true },
    ],
    filters: [
      { key: 'payment_status', label: 'Any payment', type: 'select', options: statusOptions(PAYMENT_STATUSES) },
      { key: 'fulfilment_status', label: 'Any fulfilment', type: 'select', options: statusOptions(ORDER_STATUSES) },
      { key: 'date_from', label: 'From', type: 'date' },
      { key: 'date_to', label: 'To', type: 'date' },
    ],
    bulkActions: [{ id: 'mark_processing', label: 'Mark processing', perm: 'orders.update' }, { id: 'export_selected', label: 'Export selected', perm: 'orders.export' }],
    rowActions: [
      { id: 'view', label: 'View order', icon: 'eye', handler: openOrderDialog },
      { id: 'status', label: 'Update status', icon: 'truck', perm: 'orders.update', handler: openOrderStatusDialog },
    ],
  },

  /* ------------------------------------------------------------- payments */
  payments: {
    id: 'payments', label: 'payments', singular: 'payment', endpoint: '/admin/payments/', exportable: true,
    defaultOrdering: '-created_at', emptyIcon: 'credit-card', labelKey: 'reference',
    permissions: { update: 'payments.verify' },
    columns: [
      { key: 'reference', label: 'Reference', type: 'primary', subKey: 'order_reference', sortable: true },
      { key: 'customer_email', label: 'Customer' },
      { key: 'amount', label: 'Amount', type: 'money', numeric: true, sortable: true },
      { key: 'status', label: 'Status', type: 'status', tones: { success: 'success', pending: 'warning', failed: 'danger', abandoned: 'neutral', reversed: 'warning', refunded: 'info', partially_refunded: 'info' } },
      { key: 'channel', label: 'Channel' },
      { key: 'paid_at', label: 'Paid at', type: 'datetime', sortable: true },
    ],
    filters: [
      { key: 'status', label: 'Any status', type: 'select', options: statusOptions(PAYMENT_STATUSES) },
      { key: 'date_from', label: 'From', type: 'date' },
      { key: 'date_to', label: 'To', type: 'date' },
    ],
    rowActions: [{
      id: 'verify', label: 'Re-verify with Paystack', icon: 'refresh', perm: 'payments.verify',
      handler: async (row, table) => {
        try {
          const result = await api.post(`/admin/payments/${encodeURIComponent(row.reference)}/verify/`, {});
          toast(`Verification result: ${result.status || 'updated'}.`, { type: 'success' });
          table.load();
        } catch (error) { toast(error.userMessage, { type: 'danger' }); }
      },
    }],
  },

  /* -------------------------------------------------------------- refunds */
  refunds: {
    id: 'refunds', label: 'refund requests', singular: 'refund', endpoint: '/admin/refunds/', exportable: true,
    defaultOrdering: '-created_at', emptyIcon: 'undo', labelKey: 'reference',
    permissions: { update: 'refunds.process' },
    columns: [
      { key: 'order_reference', label: 'Order', type: 'primary', subKey: 'created_at' },
      { key: 'customer_email', label: 'Customer' },
      { key: 'amount', label: 'Amount', type: 'money', numeric: true },
      { key: 'reason', label: 'Reason', type: 'truncate' },
      { key: 'status', label: 'Status', type: 'status', tones: { pending: 'warning', approved: 'info', processing: 'info', completed: 'success', rejected: 'danger' } },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: ['pending', 'approved', 'processing', 'completed', 'rejected'] }],
    rowActions: [
      { id: 'approve', label: 'Approve refund', icon: 'check', perm: 'refunds.process', when: (r) => r.status === 'pending', handler: refundAction('approve') },
      { id: 'reject', label: 'Reject refund', icon: 'x', tone: 'danger', perm: 'refunds.process', when: (r) => r.status === 'pending', handler: refundAction('reject') },
    ],
  },

  /* ------------------------------------------------------------- delivery */
  delivery: {
    id: 'delivery', label: 'delivery methods', singular: 'delivery method', createLabel: 'New delivery method',
    endpoint: '/admin/delivery-methods/', deletable: true, emptyIcon: 'truck',
    permissions: { create: 'delivery.create', update: 'delivery.update', delete: 'delivery.delete' },
    columns: [
      { key: 'name', label: 'Method', type: 'primary', subKey: 'code', sortable: true },
      { key: 'fee', label: 'Base fee', type: 'money', numeric: true },
      { key: 'eta', label: 'Estimated time' },
      { key: 'is_pickup', label: 'Pickup', type: 'boolean' },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    form: [
      { key: 'name', label: 'Method name', required: true, section: 'Details' },
      { key: 'code', label: 'Code', required: true, section: 'Details', hint: 'Stable identifier, e.g. standard, express, pickup.' },
      { key: 'description', label: 'Customer-facing description', type: 'textarea', rows: 2, section: 'Details', full: true },
      { key: 'fee', label: 'Base fee (NGN)', type: 'money', required: true, section: 'Pricing' },
      { key: 'free_over', label: 'Free delivery over (NGN)', type: 'money', section: 'Pricing' },
      { key: 'eta', label: 'Estimated delivery time', section: 'Details', placeholder: '2–4 working days' },
      { key: 'is_pickup', label: 'This is a pickup option', type: 'switch', section: 'Details' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Details' },
    ],
  },

  /* ------------------------------------------------------- shipping zones */
  'shipping-zones': {
    id: 'shipping-zones', label: 'shipping zones', singular: 'shipping zone', createLabel: 'New zone',
    endpoint: '/admin/shipping-zones/', deletable: true, emptyIcon: 'map-pin',
    permissions: { create: 'delivery.create', update: 'delivery.update', delete: 'delivery.delete' },
    columns: [
      { key: 'name', label: 'Zone', type: 'primary', subKey: 'states_display', sortable: true },
      { key: 'rate', label: 'Rate', type: 'money', numeric: true },
      { key: 'delivery_method.name', label: 'Method' },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    form: [
      { key: 'name', label: 'Zone name', required: true, section: 'Zone' },
      { key: 'states', label: 'States covered', type: 'tags', required: true, section: 'Zone', full: true, hint: 'Comma-separated state names exactly as they appear at checkout.' },
      { key: 'delivery_method', label: 'Delivery method', type: 'select', source: '/admin/delivery-methods/', section: 'Zone' },
      { key: 'rate', label: 'Zone rate (NGN)', type: 'money', required: true, section: 'Zone' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Zone' },
    ],
  },

  /* ------------------------------------------------------------ customers */
  customers: {
    id: 'customers', label: 'customers', singular: 'customer', endpoint: '/admin/customers/', exportable: true,
    defaultOrdering: '-date_joined', emptyIcon: 'users', labelKey: 'email',
    permissions: { update: 'customers.update' },
    columns: [
      { key: 'email', label: 'Customer', type: 'primary', subKey: 'full_name', sortable: true },
      { key: 'phone', label: 'Phone' },
      { key: 'orders_count', label: 'Orders', type: 'number', numeric: true, sortable: true },
      { key: 'total_spent', label: 'Total spent', type: 'money', numeric: true, sortable: true },
      { key: 'date_joined', label: 'Joined', type: 'date', sortable: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'has_orders', label: 'All customers', type: 'select', options: [{ value: '1', label: 'With orders' }, { value: '0', label: 'Without orders' }] }],
    rowActions: [{ id: 'view', label: 'View customer', icon: 'eye', perm: 'customers.view', handler: openCustomerDialog }],
  },

  /* -------------------------------------------------------------- reviews */
  reviews: {
    id: 'reviews', label: 'reviews', singular: 'review', endpoint: '/admin/reviews/', deletable: true,
    defaultOrdering: '-created_at', emptyIcon: 'star',
    permissions: { update: 'reviews.moderate', delete: 'reviews.delete' },
    columns: [
      { key: 'product.name', label: 'Product', type: 'primary', subKey: 'display_name' },
      { key: 'rating', label: 'Rating', type: 'number', numeric: true, sortable: true },
      { key: 'title', label: 'Review', type: 'truncate' },
      { key: 'verified_purchase', label: 'Verified', type: 'boolean' },
      { key: 'is_approved', label: 'Approved', type: 'boolean' },
      { key: 'created_at', label: 'Submitted', type: 'date', sortable: true },
    ],
    filters: [{ key: 'is_approved', label: 'Any state', type: 'select', options: [{ value: '0', label: 'Awaiting moderation' }, { value: '1', label: 'Approved' }] }],
    bulkActions: [{ id: 'approve', label: 'Approve', perm: 'reviews.moderate' }, { id: 'unapprove', label: 'Unpublish', perm: 'reviews.moderate' }],
    rowActions: [
      { id: 'approve', label: 'Approve review', icon: 'check', perm: 'reviews.moderate', when: (r) => !r.is_approved, handler: reviewAction('approve') },
      { id: 'unapprove', label: 'Unpublish review', icon: 'eye-off', perm: 'reviews.moderate', when: (r) => r.is_approved, handler: reviewAction('unapprove') },
    ],
  },

  /* ------------------------------------------------------------ enquiries */
  enquiries: {
    id: 'enquiries', label: 'enquiries', singular: 'enquiry', endpoint: '/admin/enquiries/', deletable: true,
    defaultOrdering: '-created_at', emptyIcon: 'message', labelKey: 'subject',
    permissions: { update: 'enquiries.update', delete: 'enquiries.delete' },
    columns: [
      { key: 'name', label: 'From', type: 'primary', subKey: 'email' },
      { key: 'subject', label: 'Subject' },
      { key: 'order_reference', label: 'Order' },
      { key: 'status', label: 'Status', type: 'status', tones: { new: 'warning', in_progress: 'info', resolved: 'success', closed: 'neutral' } },
      { key: 'created_at', label: 'Received', type: 'datetime', sortable: true },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: ['new', 'in_progress', 'resolved', 'closed'] }],
    rowActions: [{ id: 'view', label: 'Read enquiry', icon: 'eye', handler: openEnquiryDialog }],
  },

  /* ----------------------------------------------------------- newsletter */
  newsletter: {
    id: 'newsletter', label: 'subscribers', singular: 'subscriber', endpoint: '/admin/newsletter/', deletable: true,
    exportable: true, defaultOrdering: '-created_at', emptyIcon: 'mail', labelKey: 'email',
    permissions: { delete: 'newsletter.delete' },
    columns: [
      { key: 'email', label: 'Email', type: 'primary', sortable: true },
      { key: 'status', label: 'Status', type: 'status', tones: { subscribed: 'success', pending: 'warning', unsubscribed: 'neutral' } },
      { key: 'consent_at', label: 'Consent given', type: 'datetime' },
      { key: 'source', label: 'Source' },
      { key: 'created_at', label: 'Added', type: 'date', sortable: true },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: ['subscribed', 'pending', 'unsubscribed'] }],
  },

  /* ------------------------------------------------------------ discounts */
  discounts: {
    id: 'discounts', label: 'discounts', singular: 'discount', createLabel: 'New discount',
    endpoint: '/admin/discounts/', deletable: true, emptyIcon: 'percent', labelKey: 'code',
    permissions: { create: 'discounts.create', update: 'discounts.update', delete: 'discounts.delete' },
    columns: [
      { key: 'code', label: 'Code', type: 'primary', subKey: 'name', sortable: true },
      { key: 'type', label: 'Type', type: 'status', tones: { percentage: 'primary', fixed: 'info' } },
      { key: 'value', label: 'Value', type: 'custom', render: (r) => (r.type === 'percentage' ? `${esc(r.value)}%` : esc(formatMoney(r.value, r.currency || 'NGN'))), numeric: true },
      { key: 'usage_count', label: 'Uses', type: 'number', numeric: true },
      { key: 'valid_to', label: 'Expires', type: 'date', sortable: true },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'is_active', label: 'Any status', type: 'select', options: [{ value: '1', label: 'Active' }, { value: '0', label: 'Inactive' }] }],
    form: [
      { key: 'code', label: 'Discount code', required: true, section: 'Code' },
      { key: 'name', label: 'Internal name', section: 'Code' },
      { key: 'type', label: 'Discount type', type: 'select', options: [{ value: 'percentage', label: 'Percentage' }, { value: 'fixed', label: 'Fixed amount' }], required: true, section: 'Value' },
      { key: 'value', label: 'Value', type: 'number', min: 0, step: '0.01', required: true, section: 'Value', hint: 'Percent for percentage discounts, NGN for fixed discounts.' },
      { key: 'max_discount_amount', label: 'Maximum discount (NGN)', type: 'money', section: 'Value' },
      { key: 'minimum_purchase', label: 'Minimum purchase (NGN)', type: 'money', section: 'Eligibility' },
      { key: 'scope', label: 'Applies to', type: 'select', options: [{ value: 'all', label: 'Entire order' }, { value: 'category', label: 'Specific categories' }, { value: 'product', label: 'Specific products' }], default: 'all', section: 'Eligibility' },
      { key: 'categories', label: 'Category ids', type: 'tags', section: 'Eligibility', hint: 'Only used when scope is categories.' },
      { key: 'products', label: 'Product ids', type: 'tags', section: 'Eligibility', hint: 'Only used when scope is products.' },
      { key: 'usage_limit', label: 'Total usage limit', type: 'number', min: 0, section: 'Limits' },
      { key: 'per_customer_limit', label: 'Per-customer limit', type: 'number', min: 0, section: 'Limits' },
      { key: 'valid_from', label: 'Valid from', type: 'datetime', section: 'Schedule' },
      { key: 'valid_to', label: 'Valid to', type: 'datetime', section: 'Schedule' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Schedule' },
    ],
  },

  /* ----------------------------------------------------------- promotions */
  promotions: {
    id: 'promotions', label: 'promotions', singular: 'promotion', createLabel: 'New promotion',
    endpoint: '/admin/promotions/', deletable: true, emptyIcon: 'tag',
    permissions: { create: 'promotions.create', update: 'promotions.update', delete: 'promotions.delete' },
    columns: [
      { key: 'title', label: 'Promotion', type: 'image', resolve: (r) => r.image_url, subKey: 'placement', sortable: true },
      { key: 'placement', label: 'Placement' },
      { key: 'starts_at', label: 'Starts', type: 'datetime', sortable: true },
      { key: 'ends_at', label: 'Ends', type: 'datetime' },
      { key: 'is_active', label: 'Active', type: 'boolean' },
    ],
    filters: [{ key: 'placement', label: 'Any placement', type: 'select', options: ['home_banner', 'home_secondary', 'category_banner', 'announcement'] }],
    form: [
      { key: 'title', label: 'Title', required: true, section: 'Content', full: true },
      { key: 'eyebrow', label: 'Eyebrow text', section: 'Content' },
      { key: 'description', label: 'Description', type: 'textarea', rows: 3, section: 'Content', full: true },
      { key: 'cta_label', label: 'Button label', section: 'Content' },
      { key: 'cta_url', label: 'Button URL', type: 'url', section: 'Content' },
      { key: 'terms', label: 'Terms shown to customers', type: 'textarea', rows: 2, section: 'Content', full: true },
      { key: 'image', label: 'Banner image', type: 'image', altKey: 'image_alt', section: 'Media', full: true },
      { key: 'placement', label: 'Placement', type: 'select', options: ['home_banner', 'home_secondary', 'category_banner', 'announcement'], required: true, section: 'Scheduling' },
      { key: 'starts_at', label: 'Starts at', type: 'datetime', section: 'Scheduling' },
      { key: 'ends_at', label: 'Ends at', type: 'datetime', section: 'Scheduling' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Scheduling' },
    ],
  },

  /* -------------------------------------------------------- notifications */
  notifications: {
    id: 'notifications', label: 'notification templates', singular: 'template',
    endpoint: '/admin/notification-templates/', emptyIcon: 'bell', labelKey: 'event',
    permissions: { update: 'notifications.update' },
    columns: [
      { key: 'event', label: 'Event', type: 'primary', subKey: 'name', sortable: true },
      { key: 'channel', label: 'Channel', type: 'status', tones: { email: 'info', sms: 'primary', in_app: 'neutral' } },
      { key: 'subject', label: 'Subject', type: 'truncate' },
      { key: 'is_active', label: 'Enabled', type: 'boolean' },
    ],
    form: [
      { key: 'subject', label: 'Email subject', required: true, section: 'Template', full: true },
      { key: 'body_html', label: 'Email body (HTML)', type: 'richtext', section: 'Template' },
      { key: 'body_text', label: 'Plain-text fallback', type: 'textarea', rows: 4, section: 'Template' },
      { key: 'is_active', label: 'Enabled', type: 'switch', default: true, section: 'Template' },
    ],
  },

  /* ----------------------------------------------------------- email logs */
  'email-logs': {
    id: 'email-logs', label: 'email log entries', singular: 'email', endpoint: '/admin/email-logs/',
    exportable: true, defaultOrdering: '-created_at', emptyIcon: 'send', labelKey: 'subject',
    permissions: {},
    columns: [
      { key: 'recipient', label: 'Recipient', type: 'primary', subKey: 'template' },
      { key: 'subject', label: 'Subject', type: 'truncate' },
      { key: 'status', label: 'Status', type: 'status', tones: { sent: 'success', delivered: 'success', queued: 'warning', failed: 'danger', bounced: 'danger' } },
      { key: 'created_at', label: 'Sent', type: 'datetime', sortable: true },
    ],
    filters: [{ key: 'status', label: 'Any status', type: 'select', options: ['queued', 'sent', 'delivered', 'failed', 'bounced'] }],
    rowActions: [{ id: 'view', label: 'View email', icon: 'eye', handler: openEmailDialog }],
  },

  /* ---------------------------------------------------------------- staff */
  staff: {
    id: 'staff', label: 'staff accounts', singular: 'staff member', createLabel: 'Invite staff',
    endpoint: '/admin/staff/', emptyIcon: 'shield', labelKey: 'email',
    permissions: { create: 'staff.create', update: 'staff.update', delete: 'staff.delete' },
    deletable: true,
    columns: [
      { key: 'email', label: 'Staff member', type: 'primary', subKey: 'full_name', sortable: true },
      { key: 'role', label: 'Role', type: 'status', tones: { super_admin: 'primary', manager: 'info', product_manager: 'info', inventory_manager: 'info', order_manager: 'info', customer_support: 'neutral', accountant: 'warning' } },
      { key: 'is_active', label: 'Active', type: 'boolean' },
      { key: 'last_login', label: 'Last sign-in', type: 'datetime', sortable: true },
    ],
    filters: [{ key: 'role', label: 'All roles', type: 'select', options: ['super_admin', 'manager', 'product_manager', 'inventory_manager', 'order_manager', 'customer_support', 'accountant'] }],
    form: [
      { key: 'email', label: 'Email address', type: 'email', required: true, section: 'Account' },
      { key: 'first_name', label: 'First name', section: 'Account' },
      { key: 'last_name', label: 'Last name', section: 'Account' },
      { key: 'role', label: 'Role', type: 'select', required: true, section: 'Permissions', options: [
        { value: 'manager', label: 'Manager' },
        { value: 'product_manager', label: 'Product manager' },
        { value: 'inventory_manager', label: 'Inventory manager' },
        { value: 'order_manager', label: 'Order manager' },
        { value: 'customer_support', label: 'Customer support' },
        { value: 'accountant', label: 'Accountant' },
        { value: 'super_admin', label: 'Super administrator' },
      ], hint: 'Permissions are enforced by the backend. The interface only reflects them.' },
      { key: 'is_active', label: 'Active', type: 'switch', default: true, section: 'Account' },
    ],
  },

  /* ----------------------------------------------------------- audit logs */
  'audit-logs': {
    id: 'audit-logs', label: 'audit entries', singular: 'audit entry', endpoint: '/admin/audit-logs/',
    exportable: true, defaultOrdering: '-created_at', emptyIcon: 'eye', permissions: {},
    columns: [
      { key: 'actor_email', label: 'User', type: 'primary', subKey: 'ip_address' },
      { key: 'action', label: 'Action', type: 'status', tones: { create: 'success', update: 'info', delete: 'danger', login: 'neutral', refund: 'warning' } },
      { key: 'resource', label: 'Resource' },
      { key: 'summary', label: 'Summary', type: 'truncate' },
      { key: 'created_at', label: 'When', type: 'datetime', sortable: true },
    ],
    filters: [
      { key: 'action', label: 'Any action', type: 'select', options: ['create', 'update', 'delete', 'login', 'refund', 'export'] },
      { key: 'date_from', label: 'From', type: 'date' },
      { key: 'date_to', label: 'To', type: 'date' },
    ],
    rowActions: [{ id: 'view', label: 'View change detail', icon: 'eye', handler: openAuditDialog }],
  },
};

/* ============================================================================
   Row-action dialogs
   ========================================================================== */

async function openStockDialog(row, table) {
  openDialog({
    title: 'Adjust stock',
    sub: row.product?.name || row.name || row.sku,
    size: 'narrow',
    body: `<form class="stack" id="stock-form" novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <p class="t-sm t-muted">Current on hand: <strong>${esc(row.stock_quantity ?? 0)}</strong>. Enter a positive number to add stock or a negative number to remove it.</p>
      <div class="field"><label class="field__label" for="st-delta">Adjustment</label>
        <input class="input" id="st-delta" name="delta" type="number" required step="1" placeholder="e.g. 10 or -2"></div>
      <div class="field"><label class="field__label" for="st-reason">Reason</label>
        <select class="select" id="st-reason" name="reason">
          <option value="restock">Restock</option><option value="correction">Stock correction</option>
          <option value="damage">Damaged / written off</option><option value="return">Customer return</option>
        </select></div>
      <div class="field"><label class="field__label" for="st-note">Note</label><textarea class="textarea" id="st-note" name="note" rows="2"></textarea></div>
    </form>`,
    footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-save data-pending-label="Saving">Apply adjustment</button>',
    onMount({ element, close }) {
      const form = element.querySelector('#stock-form');
      element.querySelector('[data-save]').addEventListener('click', async (event) => {
        const values = Object.fromEntries(new FormData(form).entries());
        try {
          const { withSubmit } = await import('../ui.js');
          await withSubmit(form, event.currentTarget, () => api.post('/admin/inventory/adjust/', {
            product: row.product?.id ?? row.product ?? row.id,
            variation: row.variation?.id ?? row.variation ?? null,
            delta: Number(values.delta), reason: values.reason, note: values.note,
          }));
          api.invalidate();
          close();
          toast('Stock adjusted.', { type: 'success' });
          table.load();
        } catch { /* rendered on form */ }
      });
    },
  });
}

async function openOrderDialog(row) {
  const dlg = openDialog({
    title: `Order ${row.reference}`,
    size: 'wide',
    body: '<div class="stack" aria-hidden="true"><span class="sk sk--text sk--w-70"></span><span class="sk sk--text sk--w-50"></span><span class="sk sk--input"></span></div>',
  });
  try {
    const order = await api.get(`/admin/orders/${encodeURIComponent(row.reference)}/`);
    const { renderOrderDetail } = await import('../orders.js');
    dlg.body.innerHTML = renderOrderDetail(order);
    const { hydrateIcons } = await import('../icons.js');
    hydrateIcons(dlg.body);
  } catch (error) {
    dlg.body.innerHTML = `<div class="alert alert--danger"><span class="alert__body">${esc(error.userMessage)}</span></div>`;
  }
}

async function openOrderStatusDialog(row, table) {
  openDialog({
    title: 'Update order status',
    sub: row.reference,
    size: 'narrow',
    body: `<form class="stack" id="status-form" novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      <div class="field"><label class="field__label" for="os-status">Fulfilment status</label>
        <select class="select" id="os-status" name="status">${ORDER_STATUSES.map((s) => `<option value="${s}" ${row.fulfilment_status === s ? 'selected' : ''}>${s.replace(/_/g, ' ')}</option>`).join('')}</select></div>
      <div class="field"><label class="field__label" for="os-tracking">Tracking number</label>
        <input class="input" id="os-tracking" name="tracking_number" value="${esc(row.tracking_number || '')}"></div>
      <div class="field"><label class="field__label" for="os-note">Customer-visible note</label>
        <textarea class="textarea" id="os-note" name="note" rows="2"></textarea></div>
      <label class="checkbox"><input type="checkbox" name="notify_customer" checked><span>Email the customer about this update</span></label>
    </form>`,
    footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-save data-pending-label="Updating">Update order</button>',
    onMount({ element, close }) {
      const form = element.querySelector('#status-form');
      element.querySelector('[data-save]').addEventListener('click', async (event) => {
        const values = Object.fromEntries(new FormData(form).entries());
        values.notify_customer = form.elements.notify_customer.checked;
        try {
          const { withSubmit } = await import('../ui.js');
          await withSubmit(form, event.currentTarget, () => api.post(`/admin/orders/${encodeURIComponent(row.reference)}/status/`, values));
          close();
          toast('Order updated.', { type: 'success' });
          table.load();
        } catch { /* rendered on form */ }
      });
    },
  });
}

function refundAction(action) {
  return async (row, table) => {
    const confirmed = await confirmDialog({
      title: `${action === 'approve' ? 'Approve' : 'Reject'} this refund?`,
      message: action === 'approve'
        ? 'Approving queues the refund with the payment provider. The backend performs the actual refund.'
        : 'The customer will be notified that the request was rejected.',
      confirmLabel: action === 'approve' ? 'Approve' : 'Reject',
      tone: action === 'approve' ? 'primary' : 'danger',
    });
    if (!confirmed) return;
    try {
      await api.post(`/admin/refunds/${encodeURIComponent(row.id)}/${action}/`, {});
      toast(`Refund ${action === 'approve' ? 'approved' : 'rejected'}.`, { type: 'success' });
      table.load();
    } catch (error) { toast(error.userMessage, { type: 'danger' }); }
  };
}

function reviewAction(action) {
  return async (row, table) => {
    try {
      await api.post(`/admin/reviews/${encodeURIComponent(row.id)}/${action}/`, {});
      api.invalidate();
      toast(action === 'approve' ? 'Review published.' : 'Review unpublished.', { type: 'success' });
      table.load();
    } catch (error) { toast(error.userMessage, { type: 'danger' }); }
  };
}

async function openCustomerDialog(row) {
  const dlg = openDialog({
    title: row.full_name || row.email,
    sub: row.email,
    size: 'wide',
    body: '<div class="stack" aria-hidden="true"><span class="sk sk--text sk--w-60"></span><span class="sk sk--input"></span></div>',
  });
  try {
    const data = await api.get(`/admin/customers/${encodeURIComponent(row.id)}/`);
    const orders = data.recent_orders || [];
    dlg.body.innerHTML = `<div class="stack stack--lg">
      <div class="order-meta-grid">
        <div><span class="order-meta__label">Phone</span><span class="order-meta__value">${esc(data.phone || '—')}</span></div>
        <div><span class="order-meta__label">Orders</span><span class="order-meta__value">${esc(data.orders_count ?? 0)}</span></div>
        <div><span class="order-meta__label">Total spent</span><span class="order-meta__value">${esc(formatMoney(data.total_spent ?? 0))}</span></div>
        <div><span class="order-meta__label">Joined</span><span class="order-meta__value">${esc(formatDateTime(data.date_joined))}</span></div>
      </div>
      ${orders.length ? `<div><h3 class="t-sm t-semibold" style="margin-bottom:.5rem">Recent orders</h3>
        <table class="table"><thead><tr><th>Reference</th><th>Status</th><th class="num">Total</th></tr></thead>
        <tbody>${orders.map((o) => `<tr><td>${esc(o.reference)}</td><td>${esc(o.fulfilment_status || o.status || '')}</td><td class="num">${esc(formatMoney(o.total))}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="t-sm t-muted">No orders recorded for this customer.</p>'}
    </div>`;
  } catch (error) {
    dlg.body.innerHTML = `<div class="alert alert--danger"><span class="alert__body">${esc(error.userMessage)}</span></div>`;
  }
}

async function openEnquiryDialog(row, table) {
  openDialog({
    title: row.subject || 'Enquiry',
    sub: `${row.name} · ${row.email}`,
    body: `<div class="stack stack--lg">
      <div class="panel"><p class="t-sm" style="white-space:pre-wrap">${esc(row.message || '')}</p></div>
      ${row.order_reference ? `<p class="t-sm t-muted">Order reference: <strong>${esc(row.order_reference)}</strong></p>` : ''}
      <form class="stack" id="reply-form" novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <div class="field"><label class="field__label" for="en-reply">Reply</label>
          <textarea class="textarea" id="en-reply" name="reply" rows="4" required placeholder="Write a reply to send by email"></textarea></div>
        <div class="field"><label class="field__label" for="en-status">Status</label>
          <select class="select" id="en-status" name="status">
            ${['new', 'in_progress', 'resolved', 'closed'].map((s) => `<option value="${s}" ${row.status === s ? 'selected' : ''}>${s.replace(/_/g, ' ')}</option>`).join('')}
          </select></div>
      </form>
    </div>`,
    footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Close</button><button type="button" class="btn btn--primary" data-send data-pending-label="Sending">Send reply</button>',
    onMount({ element, close }) {
      const form = element.querySelector('#reply-form');
      element.querySelector('[data-send]').addEventListener('click', async (event) => {
        const values = Object.fromEntries(new FormData(form).entries());
        try {
          const { withSubmit } = await import('../ui.js');
          await withSubmit(form, event.currentTarget, () => api.post(`/admin/enquiries/${encodeURIComponent(row.id)}/reply/`, values));
          close();
          toast('Reply sent.', { type: 'success' });
          table.load();
        } catch { /* rendered on form */ }
      });
    },
  });
}

async function openEmailDialog(row) {
  const dlg = openDialog({
    title: row.subject || 'Email',
    sub: `To ${row.recipient}`,
    size: 'wide',
    body: '<div class="stack" aria-hidden="true"><span class="sk sk--text sk--w-80"></span><span class="sk sk--input"></span></div>',
  });
  try {
    const data = await api.get(`/admin/email-logs/${encodeURIComponent(row.id)}/`);
    const { sanitizeHtml } = await import('../utils.js');
    dlg.body.innerHTML = `<div class="stack">
      <div class="cluster cluster--sm">
        <span class="badge badge--${data.status === 'failed' ? 'danger' : 'success'}">${esc(data.status)}</span>
        <span class="t-meta">${esc(formatDateTime(data.created_at))}</span>
      </div>
      ${data.error ? `<div class="alert alert--danger"><span class="alert__body">${esc(data.error)}</span></div>` : ''}
      <div class="panel">${data.body_html ? sanitizeHtml(data.body_html) : `<pre>${esc(data.body_text || '')}</pre>`}</div>
    </div>`;
  } catch (error) {
    dlg.body.innerHTML = `<div class="alert alert--danger"><span class="alert__body">${esc(error.userMessage)}</span></div>`;
  }
}

async function openAuditDialog(row) {
  openDialog({
    title: `${row.action} · ${row.resource || ''}`,
    sub: `${row.actor_email || 'system'} · ${formatDateTime(row.created_at)}`,
    size: 'wide',
    body: `<div class="stack">
      <p class="t-sm">${esc(row.summary || '')}</p>
      <div><p class="t-xs t-semibold t-upper" style="margin-bottom:.25rem">Change detail</p>
        <pre class="audit-diff">${esc(JSON.stringify(row.changes ?? row.detail ?? {}, null, 2))}</pre></div>
      <p class="t-meta">IP: ${esc(row.ip_address || '—')} · User agent: ${esc(row.user_agent || '—')}</p>
    </div>`,
  });
}

export default MODULES;
