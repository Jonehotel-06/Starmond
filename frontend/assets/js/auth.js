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
import { mergeGuestCart } from './cart.js';

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
  // Backend UserSerializer: {id, email, full_name, phone, is_email_verified,
  // date_joined, role, is_staff_user, is_superuser, permissions[]}.
  // Permissions are for UI gating only; the API re-checks every request.
  const role = user.role && typeof user.role === 'object' ? user.role.name : user.role;
  return {
    ...user,
    permissions: Array.isArray(user.permissions) ? user.permissions : [],
    roles: role ? [role] : [],
    is_staff: !!(user.is_staff_user ?? user.is_staff),
    is_superuser: !!user.is_superuser,
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
      api.clearAccessToken();
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
/* ============================================================================
   Session actions
   ========================================================================== */

function adoptSession(data, reason) {
  // Django rotates the CSRF token whenever the session changes.
  api.resetCsrf();
  api.invalidate();
  if (data?.auth_token) api.setAccessToken(data.auth_token);
  const user = absorbUser(data);
  if (!user) return null;
  storage.set(SESSION_HINT, '1');
  Object.assign(state, {
    status: 'authenticated', user, permissions: user.permissions, roles: user.roles, isStaff: user.is_staff,
  });
  listeners.forEach((fn) => { try { fn(getAuthState()); } catch (err) { console.error(err); } });
  // `reason: 'login'` tells cart.js to merge the guest cart into the account.
  window.dispatchEvent(new CustomEvent('starmond:auth-changed', { detail: { ...getAuthState(), reason } }));
  return user;
}

/** POST /auth/login/ {email, password} → {user, auth_token} */
export async function login({ email, password }) {
  const data = await api.post('/auth/login/', { email: String(email).trim(), password });
  const user = adoptSession(data, 'login');
  if (!user) await initAuth({ force: true });
  // Fold the guest cart into the account cart before the page navigates away.
  await mergeGuestCart();
  return { user: state.user };
}

/**
 * POST /auth/register/ {email, full_name, phone, password} → {user_id}.
 * Registration does not sign the customer in: the address must be verified
 * from the emailed link first.
 */
export async function register({ email, full_name, phone = '', password }) {
  return api.post('/auth/register/', { email: String(email).trim(), full_name, phone, password });
}

export async function logout() {
  try { await api.post('/auth/logout/', {}); } catch { /* local sign-out still proceeds */ }
  api.clearAccessToken();
  api.clearCartToken();
  api.resetCsrf();
  storage.remove(SESSION_HINT);
  api.invalidate();
  setState({ status: 'guest', user: null, permissions: [], roles: [], isStaff: false });
}

export const verifyEmail = (token) => api.post('/auth/verify-email/', { token });
export const resendVerification = (email) => api.post('/auth/resend-verification/', { email });
export const requestPasswordReset = (email) => api.post('/auth/password/reset/request/', { email });
/** {uid, token, new_password} — uid and token come from the emailed link. */
export const confirmPasswordReset = ({ uid, token, new_password }) =>
  api.post('/auth/password/reset/confirm/', { uid, token, new_password });
/** {current_password, new_password} */
export const changePassword = ({ current_password, new_password }) =>
  api.post('/auth/password/change/', { current_password, new_password });

/** PATCH /auth/me/ {full_name, phone} */
export async function updateProfile(payload) {
  const data = await api.patch('/auth/me/', payload);
  const user = absorbUser(data);
  if (user) setState({ user, permissions: user.permissions, roles: user.roles, isStaff: user.is_staff });
  return data;
}

/** Customer profile (GET/PATCH /customers/profile/): default delivery details
 *  and the three notification switches. */
export const getCustomerProfile = () => api.privateGet('/customers/profile/');
export const updateCustomerProfile = (payload) => api.patch('/customers/profile/', payload);
export const updateNotificationPreferences = (payload) => updateCustomerProfile(payload);

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
