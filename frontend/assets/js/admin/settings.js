/**
 * settings.js — business settings, homepage, content and SEO configuration.
 * Each form reads the current values from the backend and PATCHes changes.
 * No setting is invented client-side.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api from '../api.js';
import { skeletons, resolveRegion, renderRegionError, toast, withSubmit, formData, applyFormErrors } from '../ui.js';
import { hydrateIcons } from '../icons.js';
import { esc, $ } from '../utils.js';
import { BUSINESS_NAME } from '../site.js';

// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await initAdmin()) {
  const holder = $('[data-admin-settings]');
  const kind = holder?.dataset.adminSettings;

  const SCHEMAS = {
    business: {
      endpoint: '/admin/settings/business/',
      permission: 'settings.update',
      sections: [
        { title: 'Identity', fields: [
          { key: 'name', label: 'Business name', default: BUSINESS_NAME, required: true, full: true },
          { key: 'description', label: 'Business description', type: 'textarea', rows: 3, full: true },
          { key: 'logo', label: 'Logo', type: 'image' },
          { key: 'favicon', label: 'Favicon', type: 'image' },
        ]},
        { title: 'Contact', fields: [
          { key: 'email', label: 'Contact email', type: 'email' },
          { key: 'phone', label: 'Phone number', type: 'tel' },
          { key: 'address', label: 'Business address', type: 'textarea', rows: 2, full: true },
          { key: 'support_hours', label: 'Support hours' },
        ]},
        { title: 'Store', fields: [
          { key: 'currency', label: 'Currency', type: 'select', options: ['NGN'], default: 'NGN', hint: 'The backend remains authoritative for every amount.' },
          { key: 'country', label: 'Primary market', default: 'Nigeria' },
          { key: 'social_facebook', label: 'Facebook URL', type: 'url' },
          { key: 'social_instagram', label: 'Instagram URL', type: 'url' },
          { key: 'social_twitter', label: 'X / Twitter URL', type: 'url' },
          { key: 'social_linkedin', label: 'LinkedIn URL', type: 'url' },
          { key: 'social_whatsapp', label: 'WhatsApp URL', type: 'url' },
        ]},
      ],
    },
    homepage: {
      endpoint: '/admin/settings/homepage/',
      permission: 'content.update',
      sections: [
        { title: 'Hero', fields: [
          { key: 'hero_eyebrow', label: 'Eyebrow text' },
          { key: 'hero_title', label: 'Hero headline', required: true, full: true },
          { key: 'hero_subtitle', label: 'Hero subheading', type: 'textarea', rows: 2, full: true },
          { key: 'hero_image', label: 'Hero image', type: 'image', full: true },
          { key: 'hero_image_alt', label: 'Hero image alt text', full: true },
          { key: 'hero_primary_label', label: 'Primary button label' },
          { key: 'hero_primary_url', label: 'Primary button URL' },
          { key: 'hero_secondary_label', label: 'Secondary button label' },
          { key: 'hero_secondary_url', label: 'Secondary button URL' },
        ]},
        { title: 'Sections', fields: [
          { key: 'show_categories', label: 'Show shop by category', type: 'switch', default: true },
          { key: 'show_featured', label: 'Show featured products', type: 'switch', default: true },
          { key: 'show_new_arrivals', label: 'Show new arrivals', type: 'switch', default: true },
          { key: 'show_best_sellers', label: 'Show best sellers', type: 'switch', default: true },
          { key: 'show_reviews', label: 'Show customer reviews', type: 'switch', default: true },
          { key: 'show_newsletter', label: 'Show newsletter signup', type: 'switch', default: true },
        ]},
        { title: 'Why shop with us', fields: [
          { key: 'trust_items_json', label: 'Trust items (JSON array)', type: 'textarea', rows: 6, full: true, hint: 'Array of {icon, title, text}. Only publish claims the business can substantiate.' },
        ]},
        { title: 'Footer', fields: [
          { key: 'footer_note', label: 'Footer note', type: 'textarea', rows: 2, full: true },
        ]},
      ],
    },
    content: {
      endpoint: '/admin/settings/content/',
      permission: 'content.update',
      sections: [
        { title: 'About', fields: [{ key: 'about_html', label: 'About us page', type: 'richtext' }] },
        { title: 'Policies', fields: [
          { key: 'privacy_html', label: 'Privacy policy', type: 'richtext' },
          { key: 'terms_html', label: 'Terms and conditions', type: 'richtext' },
          { key: 'shipping_html', label: 'Shipping policy', type: 'richtext' },
          { key: 'returns_html', label: 'Returns and refund policy', type: 'richtext' },
        ]},
        { title: 'Policy summaries', fields: [
          { key: 'shipping_summary', label: 'Shipping summary (shown on product pages)', type: 'textarea', rows: 2, full: true },
          { key: 'returns_summary', label: 'Returns summary (shown on product pages)', type: 'textarea', rows: 2, full: true },
        ]},
      ],
    },
    seo: {
      endpoint: '/admin/settings/seo/',
      permission: 'seo.update',
      sections: [
        { title: 'Defaults', fields: [
          { key: 'site_title', label: 'Default site title', full: true },
          { key: 'title_suffix', label: 'Title suffix', hint: 'Appended to page titles, e.g. " — Starmond Technology Limited".' },
          { key: 'meta_description', label: 'Default meta description', type: 'textarea', rows: 3, full: true },
          { key: 'canonical_domain', label: 'Canonical domain', type: 'url', hint: 'https://your-store-domain.example' },
        ]},
        { title: 'Social sharing', fields: [
          { key: 'og_image', label: 'Default social share image', type: 'image', full: true },
          { key: 'twitter_handle', label: 'X / Twitter handle' },
        ]},
        { title: 'Indexing', fields: [
          { key: 'allow_indexing', label: 'Allow search engine indexing', type: 'switch', default: true },
          { key: 'sitemap_enabled', label: 'Generate XML sitemap', type: 'switch', default: true },
          { key: 'robots_extra', label: 'Additional robots.txt directives', type: 'textarea', rows: 3, full: true },
          { key: 'verification_google', label: 'Google site verification token' },
          { key: 'verification_bing', label: 'Bing site verification token' },
        ]},
      ],
    },
  };

  const schema = SCHEMAS[kind];

  function renderForm(values) {
    return `<form class="admin-form" data-settings-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      ${schema.sections.map((section) => `
        <div class="admin-form__section">
          <p class="admin-form__section-title">${esc(section.title)}</p>
          <div class="form-grid">
            ${section.fields.map((field) => renderField(field, values)).join('')}
          </div>
        </div>`).join('')}
      <div class="admin-form__foot">
        <button type="button" class="btn btn--secondary" data-reset-settings>Reset</button>
        <button type="submit" class="btn btn--primary" data-pending-label="Saving" data-perm="${esc(schema.permission)}">Save changes</button>
      </div>
    </form>`;
  }

  function renderField(field, values) {
    const value = values?.[field.key] ?? field.default ?? '';
    const id = `s-${field.key}`;
    const full = field.full || ['textarea', 'richtext', 'image'].includes(field.type);
    const label = `<label class="field__label" for="${id}">${esc(field.label)}${field.required ? ' <span class="field__req">*</span>' : ''}</label>`;
    const hint = field.hint ? `<p class="field__hint">${esc(field.hint)}</p>` : '';
    const error = `<p class="field__error" data-error-for="${esc(field.key)}"></p>`;
    const wrap = (control) => `<div class="field ${full ? 'form-grid__full' : ''}">${label}${control}${hint}${error}</div>`;

    switch (field.type) {
      case 'textarea':
      case 'richtext':
        return wrap(`<textarea class="textarea" id="${id}" name="${esc(field.key)}" rows="${field.rows || 4}">${esc(value)}</textarea>`);
      case 'switch':
        return `<div class="field ${full ? 'form-grid__full' : ''}">
          <label class="switch"><input type="checkbox" id="${id}" name="${esc(field.key)}" ${value ? 'checked' : ''}><span class="switch__track"></span><span>${esc(field.label)}</span></label>${hint}</div>`;
      case 'select':
        return wrap(`<select class="select" id="${id}" name="${esc(field.key)}">${(field.options || []).map((option) => `<option value="${esc(option)}" ${String(value) === String(option) ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select>`);
      case 'image':
        return wrap(`<div class="stack stack--sm">
          ${value ? `<img src="${esc(value)}" alt="" width="140" height="80" style="object-fit:contain;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface-alt)">` : ''}
          <input class="input" id="${id}" name="${esc(field.key)}" type="file" accept="image/*"></div>`);
      default:
        return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="${field.type === 'email' ? 'email' : field.type === 'url' ? 'url' : field.type === 'tel' ? 'tel' : 'text'}" value="${esc(value)}" ${field.required ? 'required' : ''}>`);
    }
  }

  let original = null;

  async function load() {
    holder.setAttribute('aria-busy', 'true');
    holder.innerHTML = skeletons.form(6);
    try {
      original = await api.privateGet(schema.endpoint);
      resolveRegion(holder, renderForm(original));
      const { applyPermissions } = await import('./admin-core.js');
      applyPermissions(holder);
      bind();
    } catch (error) {
      renderRegionError(holder, error, load, { title: 'Settings could not be loaded' });
    }
  }

  function bind() {
    const form = holder.querySelector('[data-settings-form]');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const values = formData(form);
      const errors = {};
      schema.sections.forEach((section) => section.fields.forEach((field) => {
        if (field.required && !String(values[field.key] || '').trim()) errors[field.key] = `${field.label} is required.`;
        if (field.type === 'switch') values[field.key] = form.elements[field.key]?.checked ?? false;
      }));
      if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }

      const files = [];
      schema.sections.forEach((section) => section.fields.forEach((field) => {
        if (field.type !== 'image') return;
        const input = form.elements[field.key];
        if (input?.files?.length) { files.push({ key: field.key, file: input.files[0] }); delete values[field.key]; }
        else delete values[field.key];
      }));

      try {
        await withSubmit(form, form.querySelector('button[type="submit"]'), async () => {
          if (files.length) {
            const fd = new FormData();
            Object.entries(values).forEach(([key, value]) => fd.append(key, String(value)));
            files.forEach(({ key, file }) => fd.append(key, file));
            return api.upload(schema.endpoint, fd, { method: 'PATCH' });
          }
          return api.patch(schema.endpoint, values);
        });
        api.invalidate();
        toast('Settings saved. The storefront will pick them up on next load.', { type: 'success' });
        load();
      } catch { /* rendered on form */ }
    });

    holder.querySelector('[data-reset-settings]')?.addEventListener('click', () => {
      resolveRegion(holder, renderForm(original));
      bind();
    });
  }

  if (schema) {
    guardPermission(schema.permission.replace('.update', '.view'));
    load();
  }
}
