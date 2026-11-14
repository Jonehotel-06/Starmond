/**
 * auth.js — backend-managed authentication state.
 *
 * The frontend NEVER decides who a user is or what they may do. It asks the
 * backend (`/auth/me/`) and mirrors the answer for interface presentation only.
 * Every protected request is still authorized server-side.
 *
 * Token handling:
 *   • session mode (default): Django httpOnly session cookie + CSRF header.
 *     No token is ever written to web storage.
 *   • jwt mode: access token kept in memory only; refresh happens through an
 *     httpOnly cookie. A page reload re-establishes state via /auth/refresh/.
 */

import api, { ApiError } from './api.js';
import { createStorage } from './utils.js';

const storage = createStorage('local');
const listeners = new Set();

/** Non-authoritative "a session may exist" flag. Never used to grant access. */
const SESSION_HINT = 'session_hint';
let inflight = null;

const state = {
  status: 'unknown',      // unknown | loading | authenticated | guest
  user: null,
  permissions: [],
  roles: [],
  isStaff: false,
};

export function getAuthState() { return { ...state }; }
export function getUser() { return state.user; }
export function isAuthenticated() { return state.status === 'authenticated' && !!state.user; }
export function isStaff() { return !!state.isStaff; }

/** Backend-granted permission check — presentation only, never security. */
export function can(permission) {
  if (!permission) return true;
  if (state.user?.is_superuser) return true;
  const perms = state.permissions || [];
  if (perms.includes('*') || perms.includes(permission)) return true;
  // Support "app.action_resource" style prefixes, e.g. "products.*".
  const [group] = String(permission).split('.');
  return perms.includes(`${group}.*`);
}

export function canAny(permissions = []) {
  return permissions.length === 0 || permissions.some((p) => can(p));
}

export function hasRole(role) { return (state.roles || []).includes(role); }

function setState(patch) {
  Object.assign(state, patch);
  listeners.forEach((fn) => { try { fn(getAuthState()); } catch (err) { console.error(err); } });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('starmond:auth-changed', { detail: getAuthState() }));
  }
}

export function onAuthChange(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function absorbUser(payload) {
  const user = payload?.user || payload || null;
  if (!user || (!user.id && !user.email && !user.pk)) return null;
  return {
    ...user,
    permissions: payload?.permissions || user.permissions || [],
    roles: payload?.roles || user.roles || [],
    is_staff: !!(payload?.is_staff ?? user.is_staff),
  };
}

/**
 * Establish auth state on page load. A 401 is normal for guests and is not
 * surfaced as an error.
 */
export async function initAuth({ force = false } = {}) {
  if (state.status === 'authenticated' && !force) return getAuthState();

  // Collapse concurrent callers (shell + page guard + admin core) into ONE
  // request. Without this a single page load fired /auth/me/ three times.
  if (inflight && !force) return inflight;
  if (inflight && force) { try { await inflight; } catch { /* proceed */ } }

  // Session hint: a local, non-authoritative flag that says "this browser has
  // signed in before". It only decides whether to SPEND a request asking the
  // backend who we are — it never grants access. Protected pages always probe
  // (force:true) so their state is authoritative regardless of the hint.
  if (!force && !storage.get(SESSION_HINT)) {
    setState({ status: 'guest', user: null, permissions: [], roles: [], isStaff: false });
    return getAuthState();
  }

  setState({ status: 'loading' });
  inflight = probeSession({ force }).finally(() => { inflight = null; });
  return inflight;
}

async function probeSession({ force }) {
  try {
    const data = await api.privateGet('/auth/me/');
    const user = absorbUser(data);
    if (!user) throw new ApiError('No user in response', { status: 401 });
    storage.set(SESSION_HINT, '1');
    setState({
      status: 'authenticated',
      user,
      permissions: user.permissions,
      roles: user.roles,
      isStaff: user.is_staff,
    });
  } catch (error) {
    if (error instanceof ApiError && (error.isAuth || error.isNotFound)) {
      // In JWT mode, attempt one silent refresh before declaring the user a guest.
      if ((api.authMode === 'jwt') && !force) {
        const refreshed = await api.tryRefresh();
        if (refreshed) return initAuth({ force: true });
      }
      storage.remove(SESSION_HINT);
      setState({ status: 'guest', user: null, permissions: [], roles: [], isStaff: false });
    } else {
      // Network/server failure: never claim the user is signed in, but keep the
      // hint so a later page can retry once connectivity returns.
      setState({ status: 'unknown', user: null, permissions: [], roles: [], isStaff: false });
    }
  }
  return getAuthState();
}

/** Merge the guest cart into the customer cart. Backend owns de-duplication. */
async function mergeGuestCart() {
  const token = storage.get('cart_token');
  if (!token) return null;
  try {
    const result = await api.post('/cart/merge/', { guest_cart_token: token });
    api.rotateCartToken();
    api.invalidate();
    return result;
  } catch (error) {
    // A merge failure must not block sign-in; surface it to the caller.
    console.warn('[auth] guest cart merge failed', error);
    return null;
  }
}

export async function login({ email, password, remember = false }) {
  const data = await api.post('/auth/login/', { email, password, remember });
  storage.set(SESSION_HINT, '1');
  if (data?.access || data?.access_token) api.setAccessToken(data.access || data.access_token);
  const user = absorbUser(data);
  if (user) {
    setState({ status: 'authenticated', user, permissions: user.permissions, roles: user.roles, isStaff: user.is_staff });
  } else {
    await initAuth({ force: true });
  }
  const merge = await mergeGuestCart();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('starmond:cart-changed', { detail: { reason: 'login' } }));
  }
  return { user: state.user, merge };
}

export async function register(payload) {
  const data = await api.post('/auth/register/', payload);
  if (absorbUser(data)) storage.set(SESSION_HINT, '1');
  // Some backends auto-login on register; adopt the session if one was created.
  const user = absorbUser(data);
  if (user) {
    if (data?.access) api.setAccessToken(data.access);
    setState({ status: 'authenticated', user, permissions: user.permissions, roles: user.roles, isStaff: user.is_staff });
    await mergeGuestCart();
  }
  return data;
}

export async function logout() {
  try { await api.post('/auth/logout/', {}); } catch { /* local sign-out still proceeds */ }
  api.clearAccessToken();
  storage.remove(SESSION_HINT);
  api.rotateCartToken();
  api.invalidate();
  setState({ status: 'guest', user: null, permissions: [], roles: [], isStaff: false });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('starmond:cart-changed', { detail: { reason: 'logout' } }));
  }
}

export const verifyEmail = (token) => api.post('/auth/verify-email/', { token });
export const resendVerification = (email) => api.post('/auth/verify-email/resend/', { email });
export const requestPasswordReset = (email) => api.post('/auth/password/reset/', { email });
export const confirmPasswordReset = (payload) => api.post('/auth/password/reset/confirm/', payload);
export const changePassword = (payload) => api.post('/auth/password/change/', payload);

export async function updateProfile(payload) {
  const data = await api.patch('/auth/me/', payload);
  const user = absorbUser(data);
  if (user) setState({ user, permissions: user.permissions, roles: user.roles, isStaff: user.is_staff });
  return data;
}

export async function updateNotificationPreferences(payload) {
  return api.patch('/auth/me/notification-preferences/', payload);
}

/* ---------------------------------------------------------------- guards -- */

/**
 * Client-side route guard. This is UX only — it redirects to sign-in so the
 * shopper is not shown an empty private page. The backend still enforces access
 * on every single request.
 */
export async function requireAuth({ redirect = true, next } = {}) {
  await initAuth({ force: true });
  if (isAuthenticated()) return true;
  if (redirect && typeof window !== 'undefined') {
    const target = next || window.location.pathname + window.location.search;
    window.location.assign(`/login.html?next=${encodeURIComponent(target)}`);
  }
  return false;
}

export async function requirePermission(permission, { redirect = true } = {}) {
  const ok = await requireAuth({ redirect });
  if (!ok) return false;
  if (can(permission)) return true;
  if (redirect && typeof window !== 'undefined') window.location.assign('/403.html');
  return false;
}

/** Safe post-login redirect target: same-origin paths only. */
export function safeNext(value, fallback = '/account.html') {
  if (!value) return fallback;
  const raw = String(value);
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')) return fallback;
  return raw;
}

// React to a 401 raised anywhere in the app.
api.on('unauthorized', () => {
  storage.remove(SESSION_HINT);
  if (state.status === 'authenticated') {
    setState({ status: 'guest', user: null, permissions: [], roles: [], isStaff: false });
  }
});

export default { initAuth, login, register, logout, can, isAuthenticated, getUser, onAuthChange };
