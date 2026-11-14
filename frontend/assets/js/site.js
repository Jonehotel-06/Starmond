/**
 * site.js — backend-managed website settings and CMS content.
 *
 * Editable business content is NEVER hardcoded across pages. The only local
 * constant is the legal business name, used as a fallback identity string while
 * settings load or if the settings endpoint is unreachable.
 *
 * Trust claims, contact details, social links, hero copy, promotional banners
 * and policy bodies all come from the administrator via the API. If the API
 * does not supply them, the corresponding section is hidden rather than
 * filled with invented marketing copy.
 */

import api from './api.js';
import { createStorage, esc, isSafeUrl } from './utils.js';

export const BUSINESS_NAME = 'STARMOND TECHNOLOGY LIMITED';

const cacheStore = createStorage('session');
const SETTINGS_KEY = 'site_settings';
const SETTINGS_TTL_MS = 5 * 60 * 1000;

let settingsPromise = null;
let settingsValue = null;

const EMPTY_SETTINGS = Object.freeze({
  business: { name: BUSINESS_NAME },
  homepage: {},
  seo: {},
  contact: {},
  social: [],
  policies: {},
  loaded: false,
});

/**
 * Public website settings. Cached for the session; a failure resolves to a
 * minimal identity object rather than throwing, so the shell always renders.
 */
export async function getSettings({ force = false } = {}) {
  if (settingsValue && !force) return settingsValue;
  if (settingsPromise && !force) return settingsPromise;

  if (!force) {
    const cached = cacheStore.get(SETTINGS_KEY);
    if (cached && cached._ts && Date.now() - cached._ts < SETTINGS_TTL_MS) {
      settingsValue = { ...EMPTY_SETTINGS, ...cached.data, loaded: true };
      return settingsValue;
    }
  }

  settingsPromise = api.publicGet('/settings/public/')
    .then((data) => {
      settingsValue = { ...EMPTY_SETTINGS, ...(data || {}), loaded: true };
      cacheStore.set(SETTINGS_KEY, { _ts: Date.now(), data: data || {} });
      return settingsValue;
    })
    .catch(() => {
      settingsValue = { ...EMPTY_SETTINGS, loaded: false };
      return settingsValue;
    })
    .finally(() => { settingsPromise = null; });

  return settingsPromise;
}

/** Apply business identity to the shell: name, contact, social, favicon. */
export function applyBusinessIdentity(settings) {
  const business = settings?.business || {};
  const name = business.name || BUSINESS_NAME;

  document.querySelectorAll('[data-business-name]').forEach((node) => { node.textContent = name; });
  document.querySelectorAll('[data-business-description]').forEach((node) => {
    if (business.description) node.textContent = business.description;
    else node.hidden = true;
  });
  document.querySelectorAll('[data-business-email]').forEach((node) => {
    if (business.email) { node.textContent = business.email; node.href = `mailto:${esc(business.email)}`; node.closest('[data-contact-row]')?.removeAttribute('hidden'); }
    else node.closest('[data-contact-row]')?.setAttribute('hidden', '');
  });
  document.querySelectorAll('[data-business-phone]').forEach((node) => {
    if (business.phone) { node.textContent = business.phone; node.href = `tel:${String(business.phone).replace(/\s+/g, '')}`; node.closest('[data-contact-row]')?.removeAttribute('hidden'); }
    else node.closest('[data-contact-row]')?.setAttribute('hidden', '');
  });
  document.querySelectorAll('[data-business-address]').forEach((node) => {
    if (business.address) { node.textContent = business.address; node.closest('[data-contact-row]')?.removeAttribute('hidden'); }
    else node.closest('[data-contact-row]')?.setAttribute('hidden', '');
  });

  if (business.logo_url) {
    document.querySelectorAll('[data-business-logo]').forEach((img) => {
      img.src = business.logo_url;
      img.alt = `${name} logo`;
    });
  }
  if (business.favicon_url) {
    const link = document.querySelector('link[rel="icon"]');
    if (link) link.href = business.favicon_url;
  }

  const socialWrap = document.querySelector('[data-social-links]');
  if (socialWrap) {
    const links = Array.isArray(settings?.social) ? settings.social : [];
    const valid = links.filter((s) => s?.url && isSafeUrl(s.url));
    if (!valid.length) {
      socialWrap.hidden = true;
    } else {
      socialWrap.hidden = false;
      socialWrap.innerHTML = valid.map((s) => `
        <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(s.name || s.platform || 'Social profile')}">
          <i data-icon="${esc(s.icon || 'globe')}"></i>
        </a>`).join('');
    }
  }

  const year = document.querySelector('[data-current-year]');
  if (year) year.textContent = String(new Date().getFullYear());
}

/**
 * Render a CMS-managed policy/info page body.
 * Shows an honest "not published yet" state when the admin has not supplied it.
 */
export function renderPolicyContent(container, settings, key, { title }) {
  const page = settings?.policies?.[key];
  if (!container) return;
  if (!settings?.loaded) {
    container.innerHTML = `<div class="alert alert--warning">
      <span class="alert__icon"><i data-icon="alert-triangle"></i></span>
      <div class="alert__body"><span class="alert__title">Content unavailable</span>
      <span>We could not load this page from the store. Please refresh, or contact us for the current ${esc(title.toLowerCase())}.</span></div>
    </div>`;
    return;
  }
  if (!page?.body_html) {
    container.innerHTML = `<div class="state state--flat">
      <span class="state__icon"><i data-icon="file-text"></i></span>
      <p class="state__title">This page has not been published yet</p>
      <p class="state__text">The ${esc(title.toLowerCase())} for ${esc(settings?.business?.name || BUSINESS_NAME)} is being prepared. Please contact customer care for assistance in the meantime.</p>
      <div class="state__actions"><a class="btn btn--secondary btn--sm" href="/contact.html">Contact us</a></div>
    </div>`;
    return;
  }
  // sanitizeHtml is applied by the caller module that owns DOM injection.
  container.dataset.cmsBody = key;
  container.innerHTML = page.body_html;
  if (page.updated_at) {
    const stamp = document.createElement('p');
    stamp.className = 't-meta';
    stamp.style.marginTop = 'var(--space-8)';
    stamp.textContent = `Last updated: ${new Date(page.updated_at).toLocaleDateString('en-NG', { day: 'numeric', month: 'long', year: 'numeric' })}`;
    container.appendChild(stamp);
  }
}

export default { getSettings, applyBusinessIdentity, BUSINESS_NAME };
