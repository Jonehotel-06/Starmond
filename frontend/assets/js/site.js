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
const SETTINGS_KEY = 'site_settings_v2';
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

/** CMS page slug (backend `Page.slug`) → key used by the static pages. */
export const PAGE_KEYS = Object.freeze({
  'about-us': 'about',
  'contact-us': 'contact',
  'privacy-policy': 'privacy',
  'terms-conditions': 'terms',
  'shipping-policy': 'shipping',
  'returns-refund-policy': 'returns',
  faq: 'faq',
});

const SOCIAL_ICONS = { facebook: 'facebook', instagram: 'instagram', x: 'twitter', twitter: 'twitter', whatsapp: 'message', tiktok: 'globe', youtube: 'globe', linkedin: 'globe' };

/** Backend BusinessSettings + published pages → the shape the shell renders. */
function mapSettings(raw, pages) {
  const social = Object.entries(raw.social_links || {})
    .filter(([, url]) => typeof url === 'string' && url.trim())
    .map(([name, url]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      // A bare WhatsApp number becomes a wa.me link.
      url: name === 'whatsapp' && /^\+?[\d\s-]{7,}$/.test(url) ? `https://wa.me/${url.replace(/[^\d]/g, '')}` : url,
      icon: SOCIAL_ICONS[name] || 'globe',
    }));
  const hero = raw.homepage_hero || {};
  const policies = {};
  pages.forEach((page) => {
    const key = PAGE_KEYS[page.slug] || page.slug;
    policies[key] = {
      title: page.title, slug: page.slug, body_html: page.body || '', excerpt: page.excerpt || '',
      updated_at: page.updated_at, seo: page.seo || null,
    };
  });
  return {
    business: {
      name: raw.business_name || BUSINESS_NAME,
      description: raw.business_description || '',
      email: raw.contact_email || '',
      phone: raw.contact_phone || '',
      address: raw.business_address || '',
      support_hours: raw.support_hours || '',
      logo_url: raw.logo_url || '',
      favicon_url: raw.favicon_url || '',
    },
    currency: raw.currency || 'NGN',
    footer_text: raw.footer_text || '',
    social,
    homepage: {
      hero: (hero.title || hero.subtitle || hero.image_url) ? {
        title: hero.title || '', subtitle: hero.subtitle || '', image_url: hero.image_url || '',
        primary_cta: hero.cta_url ? { label: hero.cta_label || 'Shop now', url: hero.cta_url === '/shop/' ? '/shop.html' : hero.cta_url } : null,
      } : null,
    },
    policies,
  };
}

let homepagePromise = null;
/** GET /cms/homepage/ — banners, sections and the curated product rows. */
export function getHomepage() {
  if (!homepagePromise) {
    homepagePromise = api.publicGet('/cms/homepage/').catch((error) => { homepagePromise = null; throw error; });
  }
  return homepagePromise;
}

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

  // GET /cms/settings/ (business identity) + GET /cms/pages/ (published pages).
  settingsPromise = Promise.all([
    api.publicGet('/cms/settings/'),
    api.publicGet('/cms/pages/').catch(() => []),
  ])
    .then(([raw, pages]) => {
      const data = mapSettings(raw || {}, Array.isArray(pages) ? pages : []);
      settingsValue = { ...EMPTY_SETTINGS, ...data, loaded: true };
      cacheStore.set(SETTINGS_KEY, { _ts: Date.now(), data });
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
