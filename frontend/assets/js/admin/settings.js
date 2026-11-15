/**
 * settings.js — business, homepage-hero and SEO settings forms.
 *
 *   business / homepage → GET|PATCH /api/cms/admin/settings/  body { values: {...} }   (settings.manage)
 *   seo                 → GET|PATCH /api/seo/settings/        body { ...keys }         (seo.manage)
 *
 * Field keys may be dotted ("homepage_hero.title"); the parent object is always
 * sent whole because the backend replaces top-level keys.
 * Images are stored as media storage keys (see media-field.js).
 */
import { initAdmin, guardPermission, applyPermissions } from './admin-core.js';
import api from '../api.js';
import { skeletons, resolveRegion, renderRegionError, toast, withSubmit, applyFormErrors } from '../ui.js';
import { hydrateIcons } from '../icons.js';
import { esc, $ } from '../utils.js';
import { mediaKeyControl, bindMediaKeyControls } from './media-field.js';

const CMS = { endpoint: '/cms/admin/settings/', permission: 'settings.manage', wrap: (values) => ({ values }) };

const SCHEMAS = {
  business: { ...CMS, sections: [
    { title: 'Identity', fields: [
      { key: 'business_name', label: 'Business name', required: true, full: true },
      { key: 'business_description', label: 'Business description', type: 'textarea', rows: 3 },
      { key: 'logo_key', label: 'Logo', type: 'mediakey', kind: 'logo' },
      { key: 'favicon_key', label: 'Favicon', type: 'mediakey', kind: 'logo' },
    ]},
    { title: 'Contact', fields: [
      { key: 'contact_email', label: 'Contact email', type: 'email' },
      { key: 'contact_phone', label: 'Phone number', type: 'tel' },
      { key: 'business_address', label: 'Business address', type: 'textarea', rows: 2 },
      { key: 'support_hours', label: 'Support hours', placeholder: 'Mon–Sat, 9am–6pm' },
    ]},
    { title: 'Social links', fields: [
      { key: 'social_links.facebook', label: 'Facebook URL', type: 'url' },
      { key: 'social_links.instagram', label: 'Instagram URL', type: 'url' },
      { key: 'social_links.x', label: 'X (Twitter) URL', type: 'url' },
      { key: 'social_links.whatsapp', label: 'WhatsApp link', type: 'url', placeholder: 'https://wa.me/234…' },
    ]},
    { title: 'Store', fields: [
      { key: 'currency', label: 'Currency', type: 'readonly', hint: 'Payments are taken in Naira; this cannot be changed here.' },
      { key: 'refund_window_days', label: 'Refund window (days)', type: 'number', min: 0, hint: 'How long after delivery a customer may request a refund.' },
    ]},
  ]},
  homepage: { ...CMS, sections: [
    { title: 'Hero', fields: [
      { key: 'homepage_hero.title', label: 'Headline', required: true, full: true },
      { key: 'homepage_hero.subtitle', label: 'Supporting text', type: 'textarea', rows: 2 },
      { key: 'homepage_hero.cta_label', label: 'Button label' },
      { key: 'homepage_hero.cta_url', label: 'Button link', placeholder: '/shop.html' },
      { key: 'homepage_hero.image_key', label: 'Hero image', type: 'mediakey', kind: 'banner' },
    ]},
    { title: 'Footer', fields: [
      { key: 'footer_text', label: 'Footer note', type: 'textarea', rows: 2 },
    ]},
  ]},
  seo: { endpoint: '/seo/settings/', permission: 'seo.manage', wrap: (values) => values, sections: [
    { title: 'Defaults', fields: [
      { key: 'default_title_template', label: 'Page title template', full: true, required: true, hint: 'Use {title} where the page name should appear.',
        validate: (v) => (String(v).includes('{title}') ? '' : 'The template must contain {title}.') },
      { key: 'default_meta_description', label: 'Default meta description', type: 'textarea', rows: 3 },
      { key: 'default_og_site_name', label: 'Site name for social sharing' },
      { key: 'canonical_base_url', label: 'Canonical site address', type: 'url', placeholder: 'https://www.your-domain.com' },
    ]},
    { title: 'Homepage', fields: [
      { key: 'homepage_seo_title', label: 'Homepage title', full: true },
      { key: 'homepage_seo_description', label: 'Homepage meta description', type: 'textarea', rows: 3 },
      { key: 'homepage_og_image_key', label: 'Social sharing image', type: 'mediakey', kind: 'banner' },
    ]},
    { title: 'Indexing', fields: [
      { key: 'robots_meta_default', label: 'Search engine indexing', type: 'select', options: [
        ['index, follow', 'Allow indexing (index, follow)'], ['noindex, nofollow', 'Block indexing (noindex, nofollow)'], ['noindex, follow', 'noindex, follow'], ['index, nofollow', 'index, nofollow']] },
      { key: 'enable_prerender', label: 'Serve pre-rendered pages to search engines', type: 'switch' },
    ]},
  ]},
};

const getPath = (object, path) => path.split('.').reduce((value, part) => (value == null ? undefined : value[part]), object);

function renderField(field, values) {
  const raw = getPath(values, field.key);
  const value = raw ?? '';
  const id = `s-${field.key.replace(/\./g, '-')}`;
  const full = field.full || ['textarea', 'mediakey'].includes(field.type);
  const label = `<label class="field__label" for="${id}">${esc(field.label)}${field.required ? ' <span class="field__req">*</span>' : ''}</label>`;
  const hint = field.hint ? `<p class="field__hint">${esc(field.hint)}</p>` : '';
  const error = `<p class="field__error" data-error-for="${esc(field.key)}"></p>`;
  const wrap = (control) => `<div class="field ${full ? 'form-grid__full' : ''}">${label}${control}${hint}${error}</div>`;
  const name = esc(field.key);
  switch (field.type) {
    case 'textarea':
      return wrap(`<textarea class="textarea" id="${id}" name="${name}" rows="${field.rows || 4}">${esc(value)}</textarea>`);
    case 'switch':
      return `<div class="field ${full ? 'form-grid__full' : ''}"><label class="switch"><input type="checkbox" id="${id}" name="${name}" ${raw ? 'checked' : ''}><span class="switch__track"></span><span>${esc(field.label)}</span></label>${hint}</div>`;
    case 'select': {
      const options = field.options.some(([v]) => v === value) || !value ? field.options : [[value, value], ...field.options];
      return wrap(`<select class="select" id="${id}" name="${name}">${options.map(([v, text]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select>`);
    }
    case 'mediakey':
      return wrap(mediaKeyControl({ id, name: field.key, value, kind: field.kind }));
    case 'readonly':
      return wrap(`<input class="input" id="${id}" value="${esc(value)}" readonly>`);
    case 'number':
      return wrap(`<input class="input" id="${id}" name="${name}" type="number" inputmode="numeric" step="1" ${field.min != null ? `min="${field.min}"` : ''} value="${esc(value)}">`);
    default:
      return wrap(`<input class="input" id="${id}" name="${name}" type="${['email', 'url', 'tel'].includes(field.type) ? field.type : 'text'}" value="${esc(value)}" ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''} ${field.required ? 'required' : ''}>`);
  }
}

if (await initAdmin()) {
  const holder = $('[data-admin-settings]');
  const schema = SCHEMAS[holder?.dataset.adminSettings];
  const fields = schema ? schema.sections.flatMap((section) => section.fields) : [];
  let original = {};

  const renderForm = (values) => `<form class="admin-form" data-settings-form novalidate>
      <div class="alert alert--danger" data-form-error hidden role="alert"></div>
      ${schema.sections.map((section) => `
        <div class="admin-form__section">
          <p class="admin-form__section-title">${esc(section.title)}</p>
          <div class="form-grid">${section.fields.map((field) => renderField(field, values)).join('')}</div>
        </div>`).join('')}
      <div class="admin-form__foot">
        <button type="button" class="btn btn--secondary" data-reset-settings>Discard changes</button>
        <button type="submit" class="btn btn--primary" data-pending-label="Saving" data-perm="${esc(schema.permission)}">Save changes</button>
      </div>
    </form>`;

  function collect(form) {
    const errors = {};
    const body = {};
    fields.forEach((field) => {
      if (field.type === 'readonly') return;
      const control = form.elements[field.key];
      if (!control) return;
      let value = field.type === 'switch' ? control.checked : control.value.trim();
      if (field.required && !value) errors[field.key] = `${field.label} is required.`;
      else if (field.type === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) errors[field.key] = 'Enter a valid email address.';
      else if (field.type === 'url' && value && !/^https?:\/\/\S+$/i.test(value)) errors[field.key] = 'Enter a full address starting with https://';
      else if (field.type === 'number' && value !== '' && (!/^\d+$/.test(value) || Number(value) < (field.min ?? 0))) errors[field.key] = 'Enter a whole number.';
      else if (field.validate && value) { const message = field.validate(value); if (message) errors[field.key] = message; }
      if (field.type === 'number' && value !== '') value = String(Number(value));
      const [top, child] = field.key.split('.');
      if (child) {
        // Send the whole parent object: the backend replaces top-level keys.
        body[top] = body[top] || { ...(original[top] || {}) };
        body[top][child] = value;
      } else {
        body[top] = value;
      }
    });
    return { errors, body };
  }

  function mount(values) {
    resolveRegion(holder, renderForm(values));
    hydrateIcons(holder);
    applyPermissions(holder);
    const form = holder.querySelector('[data-settings-form]');
    bindMediaKeyControls(form);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      applyFormErrors(form, {});
      const { errors, body } = collect(form);
      if (Object.keys(errors).length) {
        applyFormErrors(form, errors);
        form.elements[Object.keys(errors)[0]]?.focus();
        return;
      }
      try {
        const saved = await withSubmit(form, form.querySelector('button[type="submit"]'), () => api.patch(schema.endpoint, schema.wrap(body)));
        api.invalidate();
        original = saved || { ...original, ...body };
        toast('Settings saved. The storefront shows them on its next page load.', { type: 'success' });
        mount(original);
      } catch { /* shown on the form by withSubmit */ }
    });
    holder.querySelector('[data-reset-settings]').addEventListener('click', () => mount(original));
  }

  async function load() {
    holder.setAttribute('aria-busy', 'true');
    holder.innerHTML = skeletons.form(6);
    try {
      original = await api.get(schema.endpoint, { cache: false, dedupe: false });
      mount(original);
    } catch (error) {
      renderRegionError(holder, error, load, { title: 'Settings could not be loaded' });
    }
  }

  if (schema && guardPermission(schema.permission)) load();
}
