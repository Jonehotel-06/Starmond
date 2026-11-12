/**
 * ============================================================================
 * DEMO DATA LAYER — NOT PRODUCTION CODE, NOT REAL BUSINESS INFORMATION.
 * ============================================================================
 *
 * This module is imported only when no API base URL is configured (see
 * assets/js/env.js → IS_DEMO) or when a page is opened with ?demo=1. It exists
 * so the interface can be reviewed end-to-end without a backend, exactly as the
 * delivery brief allows for design review — never to simulate a live business.
 *
 * Rules this module follows deliberately:
 *  - It is never loaded on a configured production host.
 *  - Payment verification NEVER returns success: a demo payment cannot claim a
 *    customer's money was received.
 *  - Every figure it returns is sample data, and every screen that shows it also
 *    shows the demo banner.
 *  - Turning on the real API makes this file unreachable.
 */
import { CONFIG } from '../env.js';

const LATENCY = 160;
const MOCK_USER_KEY = 'starmond_mock_user';
const MOCK_DB_KEY = 'starmond_mock_db_v1';

const CATEGORIES = [
  { id: 1, name: 'Laptops & Computing', slug: 'laptops-computing', icon: 'laptop', description: 'Business laptops, creator machines, desktops and monitors with genuine warranties.', product_count: 4 },
  { id: 2, name: 'Phones & Tablets', slug: 'phones-tablets', icon: 'phone', description: 'Smartphones and tablets with verified specifications and current Naira pricing.', product_count: 3 },
  { id: 3, name: 'Audio & Headphones', slug: 'audio-headphones', icon: 'headphones', description: 'Headphones, earbuds, speakers and studio gear.', product_count: 3 },
  { id: 4, name: 'Wearables & Smart Devices', slug: 'wearables-smart-devices', icon: 'watch', description: 'Smartwatches, fitness bands and everyday smart devices.', product_count: 1 },
  { id: 5, name: 'Power & Charging', slug: 'power-charging', icon: 'battery', description: 'Power banks, chargers, inverters and surge protection.', product_count: 2 },
  { id: 6, name: 'Accessories & Cables', slug: 'accessories-cables', icon: 'cable', description: 'Cables, adapters, hubs, keyboards and mice.', product_count: 2 },
  { id: 7, name: 'Networking & Smart Home', slug: 'networking-smart-home', icon: 'wifi', description: 'Routers, mesh Wi-Fi, switches and smart home kits.', product_count: 2 }
];

const IMG = 'assets/img/products/';

function cat(id) { return CATEGORIES.find((c) => c.id === id); }

const RAW_PRODUCTS = [
  ['laptop-1', 'Ultrabook Pro 14 (Intel Core i7, 16GB, 512GB SSD)', 1, 'Starmond', 1185000, 1299000, 6, 'laptop-1', ['Silver', 'Space Grey'], true],
  ['laptop-2', 'Business Book 15 (Core i5, 8GB, 512GB SSD)', 1, 'Starmond', 745000, null, 11, 'laptop-2', ['Black'], true],
  ['laptop-3', 'Creator Station 16 (Ryzen 7, 32GB, 1TB, RTX)', 1, 'Starmond', 1980000, 2140000, 3, 'laptop-3', ['Graphite'], false],
  ['laptop-monitor', '27" QHD IPS Monitor with USB-C Hub', 1, 'VueTech', 289000, 315000, 9, 'laptop-2', [], false],
  ['phone-1', 'Aurora X6 5G (256GB)', 2, 'Aurora', 895000, 949000, 14, 'phone-1', ['Midnight', 'Lavender'], true],
  ['phone-2', 'Aurora Lite 4 (128GB)', 2, 'Aurora', 285000, null, 22, 'phone-2', ['Blue', 'Black'], false],
  ['phone-3', 'Aurora Tab 11 (Wi-Fi, 128GB)', 2, 'Aurora', 465000, 499000, 5, 'phone-3', ['Grey'], false],
  ['audio-1', 'Studio ANC Over-Ear Bluetooth Headphones', 3, 'Sonora', 178000, 199000, 8, 'audio-1', ['Black', 'Ivory'], true],
  ['audio-2', 'Everyday Buds — True Wireless Earbuds', 3, 'Sonora', 42000, 49000, 40, 'audio-2', ['White', 'Black'], false],
  ['audio-3', 'Desk Speaker Mini with Bluetooth 5.3', 3, 'Sonora', 68000, null, 0, 'audio-3', [], false],
  ['watch-1', 'Pulse Watch S2 (GPS, 7-day battery)', 4, 'Pulse', 128000, 145000, 12, 'watch-1', ['Black', 'Rose'], false],
  ['power-1', 'VoltCore 20,000mAh Power Bank (65W PD)', 5, 'VoltCore', 64000, 72000, 26, 'power-1', [], true],
  ['power-2', 'SurgeGuard 8-Way Surge Protector', 5, 'VoltCore', 28500, null, 4, 'power-2', [], false],
  ['cable-1', 'USB-C Braided Fast-Charge Cable (2m)', 6, 'VoltCore', 12500, 15000, 60, 'cable-1', ['1m', '2m'], false],
  ['cable-2', '7-in-1 USB-C Hub (HDMI, SD, PD 100W)', 6, 'VueTech', 47500, null, 15, 'cable-2', [], false],
  ['net-1', 'MeshHome Wi-Fi 6 System (3 pack)', 7, 'Netic', 398000, 445000, 5, 'net-1', [], true],
  ['net-2', 'NanoRouter AX1800 Dual Band', 7, 'Netic', 96000, 108000, 18, 'net-2', [], false]
];

const PRODUCTS = RAW_PRODUCTS.map(([slugBase, name, catId, brand, price, compare, stock, img, colours], index) => {
  const category = cat(catId);
  const slug = slugBase;
  return {
    id: index + 1,
    name,
    slug,
    sku: `STM-${String(index + 1).padStart(4, '0')}`,
    brand,
    category: { id: category.id, name: category.name, slug: category.slug },
    price,
    compare_at_price: compare,
    currency: 'NGN',
    stock_quantity: stock,
    in_stock: stock > 0,
    reorder_level: 5,
    primary_image: IMG + img + '.svg',
    images: [IMG + img + '.svg', IMG + img + '.svg'],
    rating_average: [4.6, 4.4, 4.8, 4.2, 4.7, 4.1, 4.5, 4.6, 4.3, 4.0, 4.4, 4.7, 4.2, 4.5, 4.6, 4.8, 4.3][index] || 4.4,
    review_count: [12, 8, 21, 4, 33, 17, 6, 24, 41, 3, 9, 15, 2, 11, 5, 7, 4][index] || 0,
    short_description: `${name} — sample catalogue entry for interface review.`,
    description: `<p>This is a sample description used for interface review only. It is not a real product listing and must not be treated as business information.</p><p>The live storefront renders this section from the backend's product description field, including specification tables, warranty terms and delivery notes supplied by the catalogue team.</p>`,
    specifications: {
      Brand: brand,
      Category: category.name,
      Warranty: '12 months (sample)',
      'Supplier reference': `SUP-${1000 + index}`
    },
    options: colours.length ? [{ name: 'Colour', values: colours }] : [],
    variants: colours.length
      ? colours.map((colour, i) => ({
        id: (index + 1) * 100 + i,
        name: colour,
        attributes: { Colour: colour },
        price,
        stock_quantity: Math.max(0, stock - i),
        in_stock: Math.max(0, stock - i) > 0
      }))
      : [],
    is_featured: ['laptop-1', 'phone-1', 'audio-1', 'power-1', 'net-1', 'laptop-2'].includes(slugBase),
    is_new: index < 4,
    is_active: true,
    created_at: new Date(Date.now() - index * 86400000 * 3).toISOString()
  };
});

const SEED_ORDERS = [
  {
    id: 1001, order_number: 'STM-000001', created_at: new Date(Date.now() - 86400000 * 6).toISOString(),
    status: 'delivered', payment_status: 'paid', email: 'customer@example.com',
    customer_name: 'Demo Customer', phone: '08030000000',
    items: [
      { product: PRODUCTS[7], quantity: 1, unit_price: 178000, line_total: 178000 },
      { product: PRODUCTS[13], quantity: 2, unit_price: 12500, line_total: 25000 }
    ],
    subtotal: 203000, discount_total: 0, shipping_total: 3500, total: 206500,
    shipping_address: { first_name: 'Demo', last_name: 'Customer', line1: '12 Sample Road', city: 'Enugu', state: 'Enugu', phone: '08030000000' },
    shipping_method: { name: 'Standard delivery', eta: '2–3 working days' },
    payment: { reference: 'DEMO-PAY-000001', status: 'paid', channel: 'card' },
    can_cancel: false,
    status_history: [
      { status: 'pending_payment', created_at: new Date(Date.now() - 86400000 * 6).toISOString() },
      { status: 'paid', created_at: new Date(Date.now() - 86400000 * 6 + 3600000).toISOString() },
      { status: 'processing', created_at: new Date(Date.now() - 86400000 * 5).toISOString() },
      { status: 'shipped', created_at: new Date(Date.now() - 86400000 * 4).toISOString() },
      { status: 'delivered', created_at: new Date(Date.now() - 86400000 * 2).toISOString() }
    ]
  },
  {
    id: 1002, order_number: 'STM-000002', created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
    status: 'processing', payment_status: 'paid', email: 'customer@example.com',
    customer_name: 'Demo Customer', phone: '08030000000',
    items: [{ product: PRODUCTS[4], quantity: 1, unit_price: 895000, line_total: 895000 }],
    subtotal: 895000, discount_total: 0, shipping_total: 0, total: 895000,
    shipping_address: { first_name: 'Demo', last_name: 'Customer', line1: '12 Sample Road', city: 'Enugu', state: 'Enugu', phone: '08030000000' },
    shipping_method: { name: 'Free delivery (order above threshold)', eta: '1–2 working days' },
    payment: { reference: 'DEMO-PAY-000002', status: 'paid', channel: 'transfer' },
    can_cancel: true,
    status_history: [
      { status: 'pending_payment', created_at: new Date(Date.now() - 86400000 * 2).toISOString() },
      { status: 'paid', created_at: new Date(Date.now() - 86400000 * 2 + 1800000).toISOString() },
      { status: 'processing', created_at: new Date(Date.now() - 86400000).toISOString() }
    ]
  },
  {
    id: 1003, order_number: 'STM-000003', created_at: new Date(Date.now() - 3600000 * 5).toISOString(),
    status: 'pending_payment', payment_status: 'pending_payment', email: 'customer@example.com',
    customer_name: 'Demo Customer', phone: '08030000000',
    items: [{ product: PRODUCTS[13], quantity: 1, unit_price: 12500, line_total: 12500 }],
    subtotal: 12500, discount_total: 0, shipping_total: 2500, total: 15000,
    shipping_address: { first_name: 'Demo', last_name: 'Customer', line1: '12 Sample Road', city: 'Enugu', state: 'Enugu', phone: '08030000000' },
    shipping_method: { name: 'Standard delivery', eta: '2–3 working days' },
    payment: { reference: '', status: 'pending_payment', channel: '' },
    can_cancel: true,
    status_history: [{ status: 'pending_payment', created_at: new Date(Date.now() - 3600000 * 5).toISOString() }]
  }
];

const DEMO_USERS = {
  'customer@example.com': { id: 501, email: 'customer@example.com', password: 'Customer123!', first_name: 'Demo', last_name: 'Customer', phone: '08030000000', role: 'customer', permissions: [], is_staff: false },
  'owner@starmond.demo': { id: 1, email: 'owner@starmond.demo', password: 'Owner123!', first_name: 'Business', last_name: 'Owner', phone: '08030000001', role: 'owner', permissions: ['*'], is_staff: true }
};

/* ------------------------------------------------------------------ storage */
function loadDb() {
  try {
    const raw = localStorage.getItem(MOCK_DB_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  const seed = {
    cartToken: `demo-cart-${Math.random().toString(36).slice(2, 10)}`,
    cartItems: [],
    wishlist: [],
    orders: SEED_ORDERS,
    products: PRODUCTS,
    categories: CATEGORIES,
    addresses: [
      { id: 1, label: 'Home', recipient_name: 'Demo Customer', phone: '08030000000', line1: '12 Sample Road', city: 'Enugu', state: 'Enugu', is_default: true }
    ],
    notifications: [
      { id: 1, title: 'Order delivered', message: 'Order STM-000001 was delivered. Thanks for shopping with us.', is_read: true, created_at: new Date(Date.now() - 86400000 * 2).toISOString() },
      { id: 2, title: 'Payment confirmed', message: 'We verified your payment for order STM-000002.', is_read: false, created_at: new Date(Date.now() - 86400000).toISOString() }
    ],
    preferences: { order_updates: true, promotions: false, price_drops: true },
    reviews: [
      { id: 1, product_id: 1, product: PRODUCTS[0], customer_name: 'Demo Customer', rating: 5, title: 'Exactly as described', body: 'Sample review used for interface review only.', created_at: new Date(Date.now() - 86400000 * 9).toISOString(), status: 'approved', is_approved: true, is_verified_purchase: true },
      { id: 2, product_id: 1, product: PRODUCTS[0], customer_name: 'Another Customer', rating: 4, title: 'Good, but check the ports', body: 'Second sample review for layout review.', created_at: new Date(Date.now() - 86400000 * 4).toISOString(), status: 'approved', is_approved: true, is_verified_purchase: true },
      { id: 3, product_id: 2, product: PRODUCTS[1], customer_name: 'Sample Reviewer', rating: 5, title: 'Awaiting moderation', body: 'This review is pending so the moderation queue can be reviewed.', created_at: new Date(Date.now() - 3600000 * 8).toISOString(), status: 'pending', is_approved: false, is_verified_purchase: true }
    ],
    discounts: [
      { id: 1, code: 'WELCOME10', type: 'percentage', value: 10, minimum_order_amount: 50000, usage_limit: 100, usage_count: 12, starts_at: '2026-01-01', ends_at: '2026-12-31', is_active: true },
      { id: 2, code: 'ENUGU5K', type: 'fixed', value: 5000, minimum_order_amount: 100000, usage_limit: null, usage_count: 4, starts_at: '2026-06-01', ends_at: '2026-12-31', is_active: true }
    ],
    customers: [
      { id: 501, first_name: 'Demo', last_name: 'Customer', email: 'customer@example.com', phone: '08030000000', order_count: 3, total_spent: 1116500, date_joined: new Date(Date.now() - 86400000 * 40).toISOString(), addresses: [] },
      { id: 502, first_name: 'Sample', last_name: 'Buyer', email: 'sample.buyer@example.com', phone: '08030000002', order_count: 1, total_spent: 128000, date_joined: new Date(Date.now() - 86400000 * 18).toISOString(), addresses: [] }
    ],
    content: [
      { id: 1, key: 'home_hero', title: 'Homepage hero', subtitle: 'Technology you can trust', body: 'Hero copy managed from the dashboard.', is_active: true, updated_at: new Date().toISOString() },
      { id: 2, key: 'delivery_notice', title: 'Delivery notice banner', subtitle: '', body: 'Nationwide delivery across Nigeria.', is_active: true, updated_at: new Date().toISOString() },
      { id: 3, key: 'about_intro', title: 'About page introduction', subtitle: '', body: 'About page opening paragraph.', is_active: true, updated_at: new Date().toISOString() }
    ],
    settings: {
      business_name: 'STARMOND TECHNOLOGY LIMITED',
      support_email: 'support@starmondtechnology.com',
      support_phone: '+234 000 000 0000',
      currency: 'NGN',
      free_shipping_threshold: 750000,
      tax_rate: 7.5,
      low_stock_threshold: 5,
      order_prefix: 'STM',
      paystack_mode: 'test',
      maintenance_mode: false
    },
    seo: {
      default_title: 'STARMOND TECHNOLOGY LIMITED | Technology in Nigeria',
      default_description: 'Laptops, phones, audio, power and networking products with verified stock and nationwide delivery.',
      default_og_image: 'assets/img/og-default.png',
      analytics_id: '',
      search_console_verification: '',
      robots_policy: 'index',
      pages: []
    },
    staff: [
      { id: 1, first_name: 'Business', last_name: 'Owner', email: 'owner@starmond.demo', role: 'owner', is_active: true, last_login: new Date().toISOString() },
      { id: 2, first_name: 'Sample', last_name: 'Manager', email: 'manager@starmond.demo', role: 'manager', is_active: true, last_login: new Date(Date.now() - 86400000 * 3).toISOString() }
    ],
    roles: [
      { role: 'owner', permissions: ['*'] },
      { role: 'admin', permissions: ['products.view', 'products.edit', 'orders.view', 'orders.edit', 'refunds.view', 'reports.view', 'customers.view'] },
      { role: 'manager', permissions: ['products.view', 'orders.view', 'orders.edit', 'reports.view'] },
      { role: 'staff', permissions: ['orders.view'] }
    ],
    refunds: [],
    supportMessages: []
  };
  saveDb(seed);
  return seed;
}

function saveDb(db) {
  try { localStorage.setItem(MOCK_DB_KEY, JSON.stringify(db)); } catch { /* ignore */ }
}

const db = loadDb();
const persist = () => saveDb(db);

class MockError extends Error {
  constructor(message, status = 400, fields = null) {
    super(message);
    this.status = status;
    this.fields = fields;
    this.name = 'ApiError';
  }
}

function session_user() {
  try { return JSON.parse(localStorage.getItem(MOCK_USER_KEY) || 'null'); } catch { return null; }
}

function requireStaff() {
  const user = session_user();
  if (!user) throw new MockError('Sign in with a staff account to use the dashboard.', 401);
  if (!user.is_staff) throw new MockError('This account does not have staff access.', 403);
  return user;
}

function paginate(items, params = {}, fallbackSize = 20) {
  const page = Number(params.page || 1);
  const size = Number(params.page_size || fallbackSize);
  const start = (page - 1) * size;
  return {
    count: items.length,
    page,
    page_size: size,
    num_pages: Math.max(1, Math.ceil(items.length / size)),
    next: page * size < items.length ? page + 1 : null,
    previous: page > 1 ? page - 1 : null,
    results: items.slice(start, start + size)
  };
}

const delay = (value) => new Promise((resolve) => setTimeout(() => resolve(value), LATENCY));

/* --------------------------------------------------------------- cart maths
   The demo cart mirrors what a backend would return. These figures are sample
   data produced by this mock only; the real backend owns the calculation. */
function cartPayload() {
  const items = db.cartItems.map((item) => {
    const product = db.products.find((p) => p.id === item.product_id);
    const variant = (product?.variants || []).find((v) => v.id === item.variant_id) || null;
    const unit = variant?.price ?? product?.price ?? 0;
    return {
      id: item.id,
      product,
      variant,
      quantity: item.quantity,
      unit_price: unit,
      line_total: unit * item.quantity,
      available_stock: variant?.stock_quantity ?? product?.stock_quantity ?? 0,
      is_available: product?.in_stock !== false
    };
  });
  const subtotal = items.reduce((sum, i) => sum + i.line_total, 0);
  const discount = db.appliedDiscount
    ? (db.appliedDiscount.type === 'percentage'
      ? Math.round(subtotal * (db.appliedDiscount.value / 100))
      : Math.min(subtotal, db.appliedDiscount.value))
    : 0;
  return {
    id: 'demo-cart',
    items,
    item_count: items.reduce((n, i) => n + i.quantity, 0),
    subtotal,
    discount_total: discount,
    applied_discount: db.appliedDiscount ? { code: db.appliedDiscount.code } : null,
    total: subtotal - discount,
    currency: 'NGN'
  };
}

const SHIPPING_METHODS = [
  { id: 1, name: 'Standard delivery', fee: 3500, eta: '2–3 working days', description: 'Nationwide courier', is_default: true },
  { id: 2, name: 'Express delivery', fee: 7500, eta: '1–2 working days', description: 'Priority handling' },
  { id: 3, name: 'Enugu pickup', fee: 0, eta: 'Ready in 2 hours', description: 'Collect from our Enugu office' }
];

function shippingFeeFor(methodId, state) {
  const method = SHIPPING_METHODS.find((m) => String(m.id) === String(methodId)) || SHIPPING_METHODS[0];
  const fee = state === 'Enugu' && method.id === 1 ? 2500 : method.fee;
  return { method, fee };
}

function findProduct(idOrSlug) {
  return db.products.find((p) => String(p.slug) === String(idOrSlug) || String(p.id) === String(idOrSlug));
}

/* Requirements filter/sort/search as the documented contract specifies. */
function filterProducts(params = {}) {
  let items = db.products.filter((p) => p.is_active !== false);

  const categories = [].concat(params.category || []).filter(Boolean);
  if (categories.length) {
    items = items.filter((p) => categories.includes(p.category.slug) || categories.includes(String(p.category.id)));
  }
  const brands = [].concat(params.brand || []).filter(Boolean);
  if (brands.length) items = items.filter((p) => brands.includes(p.brand));

  if (params.q) {
    const term = String(params.q).toLowerCase();
    items = items.filter((p) => `${p.name} ${p.brand} ${p.sku} ${p.category.name}`.toLowerCase().includes(term));
  }
  if (params.min_price) items = items.filter((p) => Number(p.price) >= Number(params.min_price));
  if (params.max_price) items = items.filter((p) => Number(p.price) <= Number(params.max_price));
  if (params.in_stock) items = items.filter((p) => p.in_stock);
  if (params.on_sale) items = items.filter((p) => p.compare_at_price && Number(p.compare_at_price) > Number(p.price));
  if (params.featured) items = items.filter((p) => p.is_featured);

  const ordering = params.ordering || '-created_at';
  const desc = ordering.startsWith('-');
  const key = ordering.replace(/^-/, '');
  items = [...items].sort((a, b) => {
    let av = a[key];
    let bv = b[key];
    if (key === 'category') { av = a.category.name; bv = b.category.name; }
    if (key === 'discount_percentage') {
      av = a.compare_at_price ? (a.compare_at_price - a.price) / a.compare_at_price : 0;
      bv = b.compare_at_price ? (b.compare_at_price - b.price) / b.compare_at_price : 0;
    }
    if (typeof av === 'string') return desc ? bv.localeCompare(av) : av.localeCompare(bv);
    return desc ? Number(bv || 0) - Number(av || 0) : Number(av || 0) - Number(bv || 0);
  });
  return items;
}

/* ------------------------------------------------------------------- routes */
export async function handleMockRequest(method, path, options = {}) {
  const params = options.params || {};
  const body = options.body || {};
  const clean = path.replace(/\/+$/, '') + '/';

  try {
    /* ---- catalog ---- */
    if (method === 'GET' && clean === '/catalog/categories/') {
      return delay(paginate(db.categories, { page_size: 100 }));
    }
    if (method === 'GET' && clean === '/catalog/facets/') {
      const scope = params.category ? db.products.filter((p) => p.category.slug === params.category) : db.products;
      const counts = {};
      scope.forEach((p) => { counts[p.brand] = (counts[p.brand] || 0) + 1; });
      return delay({
        brands: Object.entries(counts).map(([value, count]) => ({ value, count })),
        price: { min: Math.min(...scope.map((p) => p.price)), max: Math.max(...scope.map((p) => p.price)) }
      });
    }
    if (method === 'GET' && clean === '/catalog/search/suggest/') {
      const term = String(params.q || '').toLowerCase();
      if (!term) return delay([]);
      return delay(filterProducts({ q: term }).slice(0, 6).map((p) => ({
        id: p.id, name: p.name, slug: p.slug, price: p.price, primary_image: p.primary_image, category: p.category
      })));
    }
    if (method === 'GET' && clean === '/catalog/products/') {
      return delay(paginate(filterProducts(params), params, CONFIG.PRODUCTS_PER_PAGE));
    }
    const productMatch = clean.match(/^\/catalog\/products\/([^/]+)\/(related\/)?$/);
    if (method === 'GET' && productMatch) {
      const product = findProduct(productMatch[1]);
      if (!product) throw new MockError('Product not found.', 404);
      if (productMatch[2]) {
        const related = db.products
          .filter((p) => p.id !== product.id && (p.category.id === product.category.id || p.brand === product.brand))
          .slice(0, 4);
        return delay(related);
      }
      return delay(product);
    }
    const reviewMatch = clean.match(/^\/catalog\/products\/([^/]+)\/reviews\/$/);
    if (reviewMatch) {
      const product = findProduct(reviewMatch[1]);
      if (!product) throw new MockError('Product not found.', 404);
      if (method === 'GET') {
        const items = db.reviews.filter((r) => r.product_id === product.id && r.status === 'approved');
        return delay(paginate(items, params, 10));
      }
      if (method === 'POST') {
        if (!session_user()) throw new MockError('Sign in to write a review.', 401);
        if (!Number(body.rating)) throw new MockError('Choose a rating.', 400, { rating: 'A rating is required.' });
        const review = {
          id: Date.now(),
          product_id: product.id,
          product,
          customer_name: [session_user().first_name, session_user().last_name].filter(Boolean).join(' ') || 'Customer',
          rating: Number(body.rating),
          title: String(body.title || '').slice(0, 120),
          body: String(body.body || '').slice(0, 2000),
          created_at: new Date().toISOString(),
          status: 'pending',
          is_approved: false
        };
        db.reviews.unshift(review);
        persist();
        return delay({ ...review, detail: 'Your review is awaiting moderation.' });
      }
    }

    /* ---- cart ---- */
    if (clean === '/cart/' && method === 'GET') return delay(cartPayload());
    if (clean === '/cart/' && method === 'DELETE') {
      db.cartItems = [];
      db.appliedDiscount = null;
      persist();
      return delay(cartPayload());
    }
    if (clean === '/cart/items/' && method === 'POST') {
      const product = db.products.find((p) => Number(p.id) === Number(body.product_id));
      if (!product) throw new MockError('That product is no longer available.', 404);
      if (product.in_stock === false) throw new MockError('That product is out of stock.', 409);
      const variantId = body.variant_id ? Number(body.variant_id) : null;
      const existing = db.cartItems.find((i) => i.product_id === product.id && (i.variant_id || null) === variantId);
      const quantity = Math.max(1, Number(body.quantity) || 1);
      if (existing) existing.quantity += quantity;
      else db.cartItems.push({ id: Date.now(), product_id: product.id, variant_id: variantId, quantity });
      persist();
      return delay(cartPayload());
    }
    const cartItemMatch = clean.match(/^\/cart\/items\/([^/]+)\/$/);
    if (cartItemMatch) {
      const id = cartItemMatch[1];
      const item = db.cartItems.find((i) => String(i.id) === String(id));
      if (!item) throw new MockError('That cart item no longer exists.', 404);
      if (method === 'PATCH') {
        item.quantity = Math.max(1, Number(body.quantity) || 1);
        persist();
        return delay(cartPayload());
      }
      if (method === 'DELETE') {
        db.cartItems = db.cartItems.filter((i) => String(i.id) !== String(id));
        persist();
        return delay(cartPayload());
      }
    }
    if (clean === '/cart/merge/' && method === 'POST') return delay(cartPayload());

    /* ---- wishlist (signed-in only) ---- */
    if (clean === '/wishlist/' && method === 'GET') {
      if (!session_user()) throw new MockError('Sign in required.', 401);
      return delay(paginate(db.wishlist, { page_size: 100 }));
    }
    if (clean === '/wishlist/' && method === 'POST') {
      if (!session_user()) throw new MockError('Sign in required.', 401);
      const product = db.products.find((p) => Number(p.id) === Number(body.product_id));
      if (!product) throw new MockError('Product not found.', 404);
      if (!db.wishlist.some((w) => w.product_id === product.id)) {
        db.wishlist.push({ id: Date.now(), product_id: product.id, product });
        persist();
      }
      return delay({ detail: 'Saved.' });
    }
    const wishMatch = clean.match(/^\/wishlist\/([^/]+)\/$/);
    if (wishMatch && method === 'DELETE') {
      db.wishlist = db.wishlist.filter((w) => String(w.id) !== String(wishMatch[1]) && String(w.product_id) !== String(wishMatch[1]));
      persist();
      return delay({ detail: 'Removed.' });
    }
    if (clean === '/wishlist/merge/' && method === 'POST') return delay({ detail: 'Merged.' });

    /* ---- auth ---- */
    if (clean === '/auth/login/' && method === 'POST') {
      const user = DEMO_USERS[String(body.email || '').toLowerCase()];
      if (!user || user.password !== body.password) {
        throw new MockError('Those credentials were not accepted.', 401);
      }
      const { password, ...safe } = user;
      localStorage.setItem(MOCK_USER_KEY, JSON.stringify(safe));
      return delay({ access: `demo-access-${Date.now()}`, refresh: 'demo-refresh', user: safe });
    }
    if (clean === '/auth/refresh/' && method === 'POST') {
      return delay({ access: `demo-access-${Date.now()}` });
    }
    if (clean === '/auth/logout/' && method === 'POST') {
      localStorage.removeItem(MOCK_USER_KEY);
      return delay({ detail: 'Signed out.' });
    }
    if (clean === '/auth/me/' && method === 'GET') {
      const user = session_user();
      if (!user) throw new MockError('Not authenticated.', 401);
      return delay({ ...user, permissions: user.permissions || [] });
    }
    if (clean === '/auth/register/' && method === 'POST') {
      if (!body.email) throw new MockError('Enter an email address.', 400, { email: 'This field is required.' });
      return delay({ detail: 'Demo mode: accounts are not created. Use the demo sign-in details shown on the sign-in page.' });
    }
    if (clean.startsWith('/auth/password/')) {
      return delay({ detail: 'Demo mode: password email is not sent because no mail server is connected.' });
    }

    /* ---- checkout ---- */
    if (clean === '/checkout/shipping-methods/' && method === 'GET') {
      return delay(SHIPPING_METHODS.map((m) => ({ ...m, fee: shippingFeeFor(m.id, params.state).fee })));
    }
    if (clean === '/checkout/buy-now/' && method === 'POST') {
      const product = db.products.find((p) => Number(p.id) === Number(body.product_id));
      if (!product) throw new MockError('Product not found.', 404);
      const variant = (product.variants || []).find((v) => Number(v.id) === Number(body.variant_id)) || null;
      const quantity = Math.max(1, Number(body.quantity) || 1);
      const unit = variant?.price ?? product.price;
      return delay({
        buy_now_token: `demo-buy-now-${Date.now()}`,
        line_items: [{ product, variant, quantity, unit_price: unit, line_total: unit * quantity }],
        subtotal: unit * quantity
      });
    }
    if (clean === '/checkout/coupon/' && method === 'POST') {
      const code = String(body.code || '').toUpperCase();
      const discount = db.discounts.find((d) => d.code === code && d.is_active);
      if (!discount) {
        return delay({ valid: false, message: 'That code is not valid.', discount_total: 0 });
      }
      const payload = body.mode === 'buy_now' ? { subtotal: body.subtotal || 0 } : cartPayload();
      const subtotal = payload.subtotal || 0;
      if (discount.minimum_order_amount && subtotal < discount.minimum_order_amount) {
        return delay({ valid: false, message: `Spend at least ₦${discount.minimum_order_amount.toLocaleString()} to use this code.`, discount_total: 0 });
      }
      const amount = discount.type === 'percentage'
        ? Math.round(subtotal * (discount.value / 100))
        : Math.min(subtotal, discount.value);
      if (body.mode !== 'buy_now') { db.appliedDiscount = discount; persist(); }
      return delay({ valid: true, code, discount_total: amount, message: `Code ${code} applied.` });
    }
    if (clean === '/checkout/session/' && method === 'POST') {
      const items = body.mode === 'buy_now'
        ? []
        : cartPayload().items;
      const cartForTotals = cartPayload();
      const subtotal = body.mode === 'buy_now'
        ? Number(body.subtotal || 0)
        : cartForTotals.subtotal;
      const discountForOrder = body.mode === 'buy_now' ? 0 : (cartForTotals.discount_total || 0);
      const { method: chosenMethod, fee: shippingFeeRaw } = shippingFeeFor(
        body.shipping_method, body.shipping_address?.state
      );
      const shippingFee = shippingFeeRaw || 0;
      const order = {
        id: Date.now(),
        order_number: `STM-${String(db.orders.length + 4).padStart(6, '0')}`,
        created_at: new Date().toISOString(),
        status: 'pending_payment',
        payment_status: 'pending_payment',
        email: body.email,
        customer_name: `${body.shipping_address?.first_name || ''} ${body.shipping_address?.last_name || ''}`.trim(),
        phone: body.phone,
        items,
        subtotal,
        discount_total: discountForOrder,
        shipping_total: shippingFee,
        total: subtotal - discountForOrder + shippingFee,
        shipping_address: body.shipping_address,
        shipping_method: chosenMethod,
        delivery_notes: body.delivery_notes || '',
        payment: { reference: '', status: 'pending_payment' },
        can_cancel: true,
        status_history: [{ status: 'pending_payment', created_at: new Date().toISOString() }]
      };
      db.orders.unshift(order);
      db.cartItems = [];
      db.appliedDiscount = null;
      persist();
      return delay({ order_id: order.id, order_number: order.order_number, totals: { total: order.total } });
    }

    /* ---- payments ---- */
    if (clean === '/payments/initialize/' && method === 'POST') {
      const order = db.orders.find((o) => String(o.id) === String(body.order_id));
      if (!order) throw new MockError('Order not found.', 404);
      return delay({
        authorization_url: `payment-callback.html?reference=DEMO-${order.order_number}`,
        reference: `DEMO-${order.order_number}`,
        access_code: 'demo'
      });
    }
    if (clean === '/payments/verify/' && method === 'GET') {
      return delay({
        status: 'pending',
        detail: 'Demo mode: no payment provider is connected, so payment verification is disabled. A real deployment verifies the reference with Paystack on the backend before any order is marked as paid.',
        reference: params.reference || ''
      });
    }

    /* ---- orders ---- */
    if (clean === '/orders/' && method === 'GET') {
      if (!session_user()) throw new MockError('Sign in required.', 401);
      const filtered = params.status
        ? db.orders.filter((o) => o.status === params.status)
        : db.orders;
      return delay(paginate(filtered, params, 10));
    }
    if (clean === '/orders/track/' && method === 'GET') {
      const order = db.orders.find((o) =>
        String(o.order_number).toLowerCase() === String(params.order_number || '').toLowerCase()
        && String(o.email).toLowerCase() === String(params.email || '').toLowerCase());
      if (!order) throw new MockError('No order matches those details.', 404);
      return delay({ order });
    }
    const orderMatch = clean.match(/^\/orders\/([^/]+)\/(cancel\/)?$/);
    if (orderMatch) {
      const order = db.orders.find((o) => String(o.order_number) === String(orderMatch[1]) || String(o.id) === String(orderMatch[1]));
      if (!order) throw new MockError('Order not found.', 404);
      if (orderMatch[2] && method === 'POST') {
        order.status = 'cancelled';
        order.can_cancel = false;
        order.status_history.push({ status: 'cancelled', created_at: new Date().toISOString() });
        persist();
        return delay({ detail: 'Order cancelled.' });
      }
      if (method === 'GET') return delay(order);
    }

    /* ---- account ---- */
    if (clean === '/account/profile/' && method === 'PATCH') {
      const user = session_user();
      if (!user) throw new MockError('Sign in required.', 401);
      const updated = { ...user, ...body };
      localStorage.setItem(MOCK_USER_KEY, JSON.stringify(updated));
      return delay(updated);
    }
    if (clean === '/account/addresses/' && method === 'GET') {
      if (!session_user()) throw new MockError('Sign in required.', 401);
      return delay(db.addresses);
    }
    if (clean === '/account/addresses/' && method === 'POST') {
      const address = { id: Date.now(), ...body };
      if (address.is_default) db.addresses = db.addresses.map((a) => ({ ...a, is_default: false }));
      db.addresses.push(address);
      persist();
      return delay(address);
    }
    const addressMatch = clean.match(/^\/account\/addresses\/([^/]+)\/$/);
    if (addressMatch) {
      const id = addressMatch[1];
      if (method === 'PATCH') {
        db.addresses = db.addresses.map((a) => (String(a.id) === String(id) ? { ...a, ...body } : (body.is_default ? { ...a, is_default: false } : a)));
        persist();
        return delay(db.addresses.find((a) => String(a.id) === String(id)));
      }
      if (method === 'DELETE') {
        db.addresses = db.addresses.filter((a) => String(a.id) !== String(id));
        persist();
        return delay({ detail: 'Address removed.' });
      }
    }
    if (clean === '/account/notifications/' && method === 'GET') {
      if (!session_user()) throw new MockError('Sign in required.', 401);
      return delay(db.notifications);
    }
    const notifRead = clean.match(/^\/account\/notifications\/([^/]+)\/read\/$/);
    if (notifRead && method === 'POST') {
      const note = db.notifications.find((n) => String(n.id) === String(notifRead[1]));
      if (note) note.is_read = true;
      persist();
      return delay({ detail: 'Marked read.' });
    }
    if (clean === '/account/notifications/read-all/' && method === 'POST') {
      db.notifications = db.notifications.map((n) => ({ ...n, is_read: true }));
      persist();
      return delay({ detail: 'All read.' });
    }
    if (clean === '/account/notifications/preferences/' && method === 'GET') return delay(db.preferences);
    if (clean === '/account/notifications/preferences/' && method === 'PATCH') {
      db.preferences = { ...db.preferences, ...body };
      persist();
      return delay(db.preferences);
    }
    if (clean === '/support/messages/' && method === 'POST') {
      db.supportMessages.push({ ...body, created_at: new Date().toISOString() });
      persist();
      return delay({ detail: 'Message received (demo mode: nothing was emailed).' });
    }

    /* ---- admin ---- */
    if (clean.startsWith('/admin/')) {
      return handleAdmin(method, clean, params, body);
    }

    throw new MockError(`Demo mode has no handler for ${method} ${clean}. Configure API_BASE_URL to use the real backend.`, 404);
  } catch (err) {
    if (err instanceof MockError) throw err;
    throw new MockError(err?.message || 'Demo data error.', 500);
  }
}

function handleAdmin(method, clean, params, body) {
  requireStaff();
  const path = clean.replace(/^\/admin/, '');

  if (path === '/dashboard/summary/' && method === 'GET') {
    const paid = db.orders.filter((o) => o.payment_status === 'paid');
    const revenue = paid.reduce((sum, o) => sum + o.total, 0);
    const series = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(Date.now() - (6 - i) * 86400000);
      const label = d.toLocaleDateString('en-NG', { weekday: 'short' });
      const total = paid
        .filter((o) => new Date(o.created_at).toDateString() === d.toDateString())
        .reduce((sum, o) => sum + o.total, 0);
      return { label, total };
    });
    return delay({
      totals: {
        revenue_30d: revenue,
        orders_30d: db.orders.length,
        pending_orders: db.orders.filter((o) => ['paid', 'processing'].includes(o.status)).length,
        customers: db.customers.length,
        new_customers_30d: 1,
        pending_payments: db.orders.filter((o) => o.payment_status === 'pending_payment').length,
        low_stock: db.products.filter((p) => p.stock_quantity <= (p.reorder_level || 5)).length
      },
      sales_series: series,
      recent_orders: db.orders.slice(0, 5),
      low_stock: db.products.filter((p) => p.stock_quantity <= (p.reorder_level || 5))
        .map((p) => ({ id: p.id, name: p.name, sku: p.sku, stock_quantity: p.stock_quantity, reorder_level: p.reorder_level }))
    });
  }

  if (path === '/inventory/' && method === 'GET') {
    let rows = db.products.map((p) => ({
      id: p.id, name: p.name, sku: p.sku, stock_quantity: p.stock_quantity,
      reserved_quantity: 0, reorder_level: p.reorder_level, updated_at: p.created_at
    }));
    if (params.search) rows = rows.filter((r) => `${r.name} ${r.sku}`.toLowerCase().includes(String(params.search).toLowerCase()));
    if (params.filter === 'low') rows = rows.filter((r) => r.stock_quantity <= (r.reorder_level || 5));
    if (params.filter === 'out') rows = rows.filter((r) => r.stock_quantity <= 0);
    return delay(paginate(rows, params, 20));
  }
  const inventoryAdjust = path.match(/^\/inventory\/([^/]+)\/adjust\/$/);
  if (inventoryAdjust && method === 'POST') {
    const product = db.products.find((p) => String(p.id) === String(inventoryAdjust[1]));
    if (!product) throw new MockError('Product not found.', 404);
    const qty = Number(body.quantity) || 0;
    if (body.mode === 'set') product.stock_quantity = Math.max(0, qty);
    if (body.mode === 'add') product.stock_quantity += qty;
    if (body.mode === 'remove') product.stock_quantity = Math.max(0, product.stock_quantity - qty);
    product.in_stock = product.stock_quantity > 0;
    persist();
    return delay({ detail: 'Stock adjusted.' });
  }

  if (path === '/reports/overview/' && method === 'GET') {
    const start = params.start ? new Date(params.start) : new Date(Date.now() - 29 * 86400000);
    const end = params.end ? new Date(params.end) : new Date();
    const orders = db.orders.filter((o) => {
      const d = new Date(o.created_at);
      return d >= start && d <= new Date(end.getTime() + 86400000);
    });
    const paid = orders.filter((o) => o.payment_status === 'paid');
    const revenue = paid.reduce((sum, o) => sum + o.total, 0);
    const units = paid.reduce((sum, o) => sum + o.items.reduce((n, i) => n + i.quantity, 0), 0);
    const byCategory = {};
    paid.forEach((o) => o.items.forEach((item) => {
      const key = item.product?.category?.name || 'Other';
      byCategory[key] = (byCategory[key] || 0) + (item.line_total || 0);
    }));
    const topProducts = {};
    paid.forEach((o) => o.items.forEach((item) => {
      const key = item.product?.name || 'Item';
      topProducts[key] = topProducts[key] || { name: key, sku: item.product?.sku, units: 0, revenue: 0 };
      topProducts[key].units += item.quantity;
      topProducts[key].revenue += item.line_total || 0;
    }));
    return delay({
      summary: {
        revenue,
        orders: orders.length,
        units,
        average_order_value: paid.length ? Math.round(revenue / paid.length) : 0,
        refunds: 0,
        discounts: paid.reduce((sum, o) => sum + (o.discount_total || 0), 0)
      },
      series: Array.from({ length: 7 }, (_, i) => {
        const d = new Date(start.getTime() + i * (end - start) / 6);
        const total = paid
          .filter((o) => new Date(o.created_at).toDateString() === d.toDateString())
          .reduce((sum, o) => sum + o.total, 0);
        return { label: d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short' }), total };
      }),
      by_category: Object.entries(byCategory).map(([category, value]) => ({ category, revenue: value })),
      top_products: Object.values(topProducts).sort((a, b) => b.revenue - a.revenue)
    });
  }

  if (path === '/refunds/' && method === 'GET') return delay(paginate(db.refunds, params, 20));
  if (path === '/refunds/' && method === 'POST') {
    const refund = {
      id: Date.now(), order_number: body.order_number, amount: Number(body.amount),
      reason: body.reason, status: 'pending',
      created_at: new Date().toISOString(), processed_at: null
    };
    db.refunds.unshift(refund);
    persist();
    return delay(refund);
  }
  if (path === '/settings/' && method === 'GET') return delay(db.settings);
  if (path === '/settings/' && method === 'PATCH') {
    db.settings = { ...db.settings, ...body };
    persist();
    return delay(db.settings);
  }
  if (path === '/seo/' && method === 'GET') return delay(db.seo);
  if (path === '/seo/' && method === 'PATCH') {
    db.seo = { ...db.seo, ...body };
    persist();
    return delay(db.seo);
  }
  if (path === '/staff/' && method === 'GET') return delay({ ...paginate(db.staff, params, 20), roles: db.roles });
  if (path === '/staff/' && method === 'POST') {
    const member = { id: Date.now(), first_name: body.first_name || '', last_name: body.last_name || '', email: body.email, role: body.role || 'staff', is_active: false, last_login: null };
    db.staff.push(member);
    persist();
    return delay({ ...member, detail: 'Demo mode: invitation recorded locally, no email sent.' });
  }
  if (path === '/content/' && method === 'GET') return delay(paginate(db.content, params, 20));
  const contentPatch = path.match(/^\/content\/([^/]+)\/$/);
  if (contentPatch && method === 'PATCH') {
    db.content = db.content.map((c) => (String(c.id) === String(contentPatch[1]) ? { ...c, ...body, updated_at: new Date().toISOString() } : c));
    persist();
    return delay({ detail: 'Content saved.' });
  }
  if (path === '/notifications/' && method === 'POST') {
    const note = { id: Date.now(), title: body.title, message: body.message, audience: body.audience, recipient_count: body.audience === 'single' ? 1 : db.customers.length, created_at: new Date().toISOString() };
    db.notifications.unshift({ id: note.id, title: note.title, message: note.message, is_read: false, created_at: note.created_at });
    db.sentNotifications = [note, ...(db.sentNotifications || [])];
    persist();
    return delay(note);
  }
  if (path === '/notifications/' && method === 'GET') return delay(paginate(db.sentNotifications || [], params, 15));

  if (path === '/orders/' && method === 'GET') {
    let rows = db.orders;
    if (params.status) rows = rows.filter((o) => o.status === params.status);
    if (params.search) {
      const term = String(params.search).toLowerCase();
      rows = rows.filter((o) => `${o.order_number} ${o.email} ${o.customer_name}`.toLowerCase().includes(term));
    }
    return delay(paginate(rows, params, 20));
  }
  const orderStatus = path.match(/^\/orders\/([^/]+)\/status\/$/);
  if (orderStatus && method === 'POST') {
    const order = db.orders.find((o) => String(o.id) === String(orderStatus[1]));
    if (!order) throw new MockError('Order not found.', 404);
    order.status = body.status;
    order.status_history.push({ status: body.status, created_at: new Date().toISOString() });
    persist();
    return delay({ detail: `Status updated to ${body.status}.` });
  }
  const verifyPayment = path.match(/^\/payments\/([^/]+)\/verify\/$/);
  if (verifyPayment && method === 'POST') {
    throw new MockError('Demo mode: payments cannot be verified because no payment provider is connected.', 400);
  }

  /* generic CRUD over the in-memory collections */
  const generic = {
    products: 'products',
    categories: 'categories',
    discounts: 'discounts',
    customers: 'customers',
    reviews: 'reviews',
    payments: 'payments',
    orders: 'orders'
  };

  if (generic[path.split('/')[1]]) {
    const key = generic[path.split('/')[1]];
    if (key === 'payments') {
      const rows = db.orders.filter((o) => o.payment_status === 'paid').map((o) => ({
        id: o.id, reference: o.payment?.reference || `DEMO-${o.order_number}`,
        order_number: o.order_number, amount: o.total, currency: 'NGN',
        channel: o.payment?.channel || 'card', status: o.payment_status,
        paid_at: o.status_history.find((h) => h.status === 'paid')?.created_at || o.created_at
      }));
      return delay(paginate(rows, params, 20));
    }
    let collection = db[key] || [];
    if (key === 'customers' && params.search) {
      const term = String(params.search).toLowerCase();
      collection = collection.filter((c) => `${c.first_name} ${c.last_name} ${c.email} ${c.phone}`.toLowerCase().includes(term));
    }
    if (key === 'reviews' && params.status) {
      collection = collection.filter((r) => (r.status || 'pending') === params.status);
    }
    if (key === 'products' && params.search) {
      const term = String(params.search).toLowerCase();
      collection = collection.filter((p) => `${p.name} ${p.sku} ${p.brand}`.toLowerCase().includes(term));
    }
    if (key === 'products' && params.category) {
      collection = collection.filter((p) => String(p.category?.id) === String(params.category));
    }

    const idMatch = path.match(/^\/[a-z]+\/([^/]+)\/$/);
    if (method === 'GET' && !idMatch) return delay(paginate(collection, params, 20));
    if (method === 'GET' && idMatch) {
      const row = collection.find((r) => String(r.id) === String(idMatch[1]));
      if (!row) throw new MockError('Record not found.', 404);
      return delay(row);
    }
    if (method === 'POST' && !idMatch) {
      const row = { id: Date.now(), ...body, created_at: new Date().toISOString() };
      if (key === 'products') {
        const category = db.categories.find((c) => String(c.id) === String(body.category)) || db.categories[0];
        Object.assign(row, {
          category: { id: category.id, name: category.name, slug: category.slug },
          slug: String(body.name || 'product').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
          in_stock: Number(body.stock_quantity) > 0,
          primary_image: body.image_url || '',
          images: body.image_url ? [body.image_url] : [],
          options: [], variants: [], rating_average: 0, review_count: 0
        });
      }
      db[key] = [row, ...(db[key] || [])];
      persist();
      return delay(row);
    }
    if (method === 'PATCH' && idMatch) {
      db[key] = (db[key] || []).map((r) => (String(r.id) === String(idMatch[1]) ? { ...r, ...body } : r));
      persist();
      return delay((db[key] || []).find((r) => String(r.id) === String(idMatch[1])));
    }
    if (method === 'DELETE' && idMatch) {
      db[key] = (db[key] || []).filter((r) => String(r.id) !== String(idMatch[1]));
      persist();
      return delay({ detail: 'Deleted.' });
    }
  }

  const actionMatch = path.match(/^\/reviews\/([^/]+)\/(approve|reject)\/$/);
  if (actionMatch && method === 'POST') {
    db.reviews = db.reviews.map((r) => (String(r.id) === String(actionMatch[1])
      ? { ...r, status: actionMatch[2] === 'approve' ? 'approved' : 'rejected', is_approved: actionMatch[2] === 'approve' }
      : r));
    persist();
    return delay({ detail: `Review ${actionMatch[2]}d.` });
  }

  throw new MockError(`Demo mode has no admin handler for ${method} ${path}.`, 404);
}
