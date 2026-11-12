/**
 * Application state: session, cart and wishlist.
 *
 * The store holds *display* state only. Prices, totals, stock and permissions
 * always come from the backend response; nothing here recalculates money.
 */
import { auth, cart as cartApi, wishlist as wishlistApi } from './api.js';
import { CONFIG } from './env.js';
import { stored, store, forget } from './utils.js';

/* ------------------------------------------------------------------ events */
const listeners = new Map();
export const bus = {
  on(event, handler) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(handler);
    return () => listeners.get(event).delete(handler);
  },
  emit(event, detail) {
    (listeners.get(event) || []).forEach((fn) => {
      try { fn(detail); } catch (err) { console.error(`[store] listener for "${event}" failed`, err); }
    });
  }
};

/* ----------------------------------------------------------------- session */
const STAFF_ROLES = ['staff', 'manager', 'admin', 'owner', 'superadmin'];

export const session = {
  user: null,
  permissions: [],
  ready: false,

  get isAuthenticated() { return Boolean(this.user); },
  get isStaff() { return Boolean(this.user) && STAFF_ROLES.includes(String(this.user.role || '').toLowerCase()); },
  get displayName() {
    if (!this.user) return '';
    return this.user.first_name || this.user.name || this.user.email || 'Account';
  },

  /**
   * Permission-aware rendering only. The backend remains the authority: if it
   * returns no explicit permission list we render the controls and let the API
   * reject anything the account is not allowed to do.
   */
  can(permission) {
    if (!permission) return true;
    if (!this.user) return false;
    const role = String(this.user.role || '').toLowerCase();
    if (role === 'owner' || role === 'superadmin') return true;
    if (!this.permissions.length) return true;
    return this.permissions.includes(permission) || this.permissions.includes('*');
  },

  async init() {
    if (this.ready) return this.user;
    this.ready = true;
    try {
      await this.load();
    } catch {
      this.clear();
    }
    return this.user;
  },

  async load() {
    const me = await auth.me();
    this.user = me?.user || me;
    const perms = me?.permissions || this.user?.permissions || [];
    this.permissions = Array.isArray(perms) ? perms : [];
    bus.emit('session', this.user);
    return this.user;
  },

  async signIn(credentials) {
    const data = await auth.login(credentials);
    const { saveTokens } = await import('./api.js');
    saveTokens({ access: data?.access || data?.access_token, refresh: data?.refresh || data?.refresh_token });
    await this.load();
    await Promise.allSettled([cart.refresh(), wishlist.mergeLocal()]);
    return this.user;
  },

  async signOut() {
    await auth.logout();
    this.clear();
    cart.reset();
    await cart.refresh().catch(() => {});
    bus.emit('session', null);
  },

  clear() {
    import('./api.js').then(({ clearTokens }) => clearTokens());
    this.user = null;
    this.permissions = [];
  }
};

/* -------------------------------------------------------------------- cart */
export const cart = {
  state: { items: [], subtotal: null, discount_total: null, total: null, count: 0, currency: 'NGN', applied_discount: null, loading: false, error: null },

  reset() {
    this.state = { items: [], subtotal: null, discount_total: null, total: null, count: 0, currency: 'NGN', applied_discount: null, loading: false, error: null };
    bus.emit('cart', this.state);
  },

  async refresh() {
    this.state.loading = true;
    bus.emit('cart', this.state);
    try {
      const data = await cartApi.get();
      this.hydrate(data);
    } catch (err) {
      this.state.error = err;
      this.state.count = 0;
      bus.emit('cart', this.state);
      throw err;
    } finally {
      this.state.loading = false;
    }
    return this.state;
  },

  hydrate(data) {
    const items = data?.items || [];
    this.state = {
      items,
      subtotal: data?.subtotal ?? null,
      discount_total: data?.discount_total ?? null,
      total: data?.total ?? data?.subtotal ?? null,
      count: data?.item_count ?? data?.count ?? items.reduce((n, i) => n + (i.quantity || 0), 0),
      currency: data?.currency || 'NGN',
      applied_discount: data?.applied_discount || null,
      loading: false,
      error: null
    };
    bus.emit('cart', this.state);
    return this.state;
  },

  async add(payload) {
    const data = await cartApi.add(payload);
    if (data?.items) this.hydrate(data);
    else await this.refresh();
    return this.state;
  },

  async update(itemId, quantity) {
    const data = await cartApi.update(itemId, quantity);
    if (data?.items) this.hydrate(data);
    else await this.refresh();
    return this.state;
  },

  async remove(itemId) {
    const data = await cartApi.remove(itemId);
    if (data?.items) this.hydrate(data);
    else await this.refresh();
    return this.state;
  },

  async clear() {
    await cartApi.clear();
    await this.refresh();
    return this.state;
  }
};

/* ---------------------------------------------------------------- wishlist */
export const wishlist = {
  ids: new Set(),
  items: [],
  loaded: false,

  init() {
    const local = stored(CONFIG.WISHLIST_KEY, []);
    this.items = Array.isArray(local) ? local : [];
    this.ids = new Set(this.items.map((item) => Number(item.id ?? item.product_id)).filter(Boolean));
    bus.emit('wishlist', this.items);
  },

  has(productId) { return this.ids.has(Number(productId)); },
  get count() { return this.ids.size; },

  persistLocal() {
    store(CONFIG.WISHLIST_KEY, this.items);
    bus.emit('wishlist', this.items);
  },

  async refresh() {
    if (!session.isAuthenticated) { this.init(); this.loaded = true; return this.items; }
    try {
      const data = await wishlistApi.list();
      this.items = data;
      this.ids = new Set(data.map((row) => Number(row.product?.id ?? row.product_id ?? row.id)));
      this.loaded = true;
      bus.emit('wishlist', this.items);
    } catch (err) {
      if (!err?.isAuth) this.init();
    }
    return this.items;
  },

  /** Push any guest wishlist to the backend once the customer signs in. */
  async mergeLocal() {
    const local = stored(CONFIG.WISHLIST_KEY, []);
    const ids = (Array.isArray(local) ? local : []).map((i) => Number(i.id ?? i.product_id)).filter(Boolean);
    if (!ids.length || !session.isAuthenticated) { await this.refresh(); return; }
    try {
      await wishlistApi.merge(ids);
      forget(CONFIG.WISHLIST_KEY);
    } catch { /* merge is best-effort; the local list stays usable */ }
    await this.refresh();
  },

  async toggle(product) {
    const id = Number(product.id);
    if (!id) return { added: false };
    if (session.isAuthenticated) {
      if (this.ids.has(id)) {
        const row = this.items.find((i) => Number(i.product?.id ?? i.product_id ?? i.id) === id);
        const remoteId = row?.id ?? id;
        await wishlistApi.remove(remoteId);
        this.ids.delete(id);
        this.items = this.items.filter((i) => Number(i.product?.id ?? i.product_id ?? i.id) !== id);
        bus.emit('wishlist', this.items);
        return { added: false };
      }
      await wishlistApi.add(id);
      await this.refresh();
      return { added: true };
    }
    if (this.ids.has(id)) {
      this.ids.delete(id);
      this.items = this.items.filter((i) => Number(i.id ?? i.product_id) !== id);
      this.persistLocal();
      return { added: false };
    }
    this.ids.add(id);
    this.items.push({
      id,
      product_id: id,
      name: product.name,
      slug: product.slug,
      price: product.price,
      compare_at_price: product.compare_at_price,
      primary_image: product.primary_image,
      in_stock: product.in_stock,
      stock_quantity: product.stock_quantity,
      brand: product.brand
    });
    this.persistLocal();
    return { added: true };
  },

  async clear() {
    this.ids.clear();
    this.items = [];
    forget(CONFIG.WISHLIST_KEY);
    bus.emit('wishlist', this.items);
  }
};

/** Boot both stores in parallel; safe to call from every page. */
export async function initStores() {
  wishlist.init();
  const tasks = [session.init(), cart.refresh().catch(() => null)];
  await Promise.allSettled(tasks);
  if (session.isAuthenticated) await wishlist.refresh();
  return { session: session.user, cart: cart.state };
}
