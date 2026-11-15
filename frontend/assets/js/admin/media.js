/**
 * media.js — media library with upload, alt-text editing and deletion.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api, { normalizeList } from '../api.js';
import {
  skeletons, resolveRegion, renderRegionError, emptyState, toast, openDialog,
  confirmDialog, withSubmit, formData, copyText,
} from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, debounce, formatNumber, formatDate } from '../utils.js';
import { can } from '../auth.js';

// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
// Backend: GET /api/media/assets/, POST /api/media/uploads/, PATCH /api/media/assets/{id}/,
// DELETE /api/media/assets/{id}/remove/ — all require media.manage.
if (await initAdmin() && guardPermission('media.manage')) {

  const root = $('[data-admin-module="media"]');
  const grid = $('[data-media-grid]');
  const state = { page: 1, search: '', kind: '', pageSize: 24 };
  const KINDS = [['product_image', 'Product image'], ['category_image', 'Category image'], ['banner', 'Banner'], ['logo', 'Logo'], ['other', 'Other']];

  async function load() {
    grid.setAttribute('aria-busy', 'true');
    grid.innerHTML = `<div class="image-picker" aria-hidden="true">${'<span class="sk sk--square"></span>'.repeat(12)}</div>`;
    try {
      const data = await api.get('/media/assets/', { params: { page: state.page, page_size: state.pageSize, search: state.search || undefined, kind: state.kind || undefined }, cache: false, dedupe: false });
      const list = normalizeList(data);
      $('[data-module-count]').textContent = `${formatNumber(list.count)} file${list.count === 1 ? '' : 's'}`;
      if (!list.results.length) {
        resolveRegion(grid, emptyState({
          title: state.search ? 'No media matches your search' : 'No media uploaded yet',
          text: 'Upload product, category and content imagery here. Alt text is required for accessibility and image SEO.',
          iconName: 'image',
          actionHtml: can('media.manage') ? '<button type="button" class="btn btn--primary btn--sm" data-media-upload-inline>Upload media</button>' : '',
        }));
        return;
      }
      resolveRegion(grid, `<div class="image-picker">${list.results.map((item) => `
        <figure class="media-tile">
          <img src="${esc(item.thumbnail_url || item.url)}" alt="${esc(item.alt_text || '')}" loading="lazy" decoding="async" width="200" height="200">
          <figcaption class="media-tile__name t-clamp-1">${esc(item.original_name || '')}</figcaption>
          <div class="media-tile__bar">
            <button type="button" class="row-action" style="background:rgba(255,255,255,.9)" data-media-copy="${esc(item.key || item.url)}" aria-label="Copy storage key (used by banners and settings)">${icon('copy', { size: 'sm' })}</button>
            ${can('media.manage') ? `<button type="button" class="row-action" style="background:rgba(255,255,255,.9)" data-media-edit="${esc(item.id)}" aria-label="Edit alt text">${icon('edit', { size: 'sm' })}</button>` : ''}
            ${can('media.manage') ? `<button type="button" class="row-action row-action--danger" style="background:rgba(255,255,255,.9)" data-media-delete="${esc(item.id)}" aria-label="Delete file">${icon('trash', { size: 'sm' })}</button>` : ''}
          </div>
        </figure>`).join('')}</div>`);
      grid.__items = list.results;
      renderPagination(list.count);
    } catch (error) {
      renderRegionError(grid, error, load, { title: 'Media library could not be loaded' });
    }
  }

  function renderPagination(count) {
    const nav = $('[data-module-pagination]');
    const pages = Math.max(1, Math.ceil(count / state.pageSize));
    if (pages <= 1) { nav.innerHTML = ''; return; }
    const around = [...new Set([1, pages, state.page - 1, state.page, state.page + 1])].filter((p) => p >= 1 && p <= pages).sort((x, y) => x - y);
    let last = 0;
    nav.innerHTML = around.map((p) => {
      const gap = last && p - last > 1 ? '<span class="pagination__gap">…</span>' : '';
      last = p;
      return `${gap}<button type="button" class="pagination__btn" data-media-page="${p}" ${state.page === p ? 'aria-current="page"' : ''}>${p}</button>`;
    }).join('');
  }

  function openUpload() {
    openDialog({
      title: 'Upload media',
      sub: 'Images are stored by the backend and served to the storefront.',
      body: `<form class="stack" id="upload-form" novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        <label class="dropzone" for="up-file">
          ${icon('upload', { size: 'xl' })}
          <span class="t-sm t-semibold">Choose images or drop them here</span>
          <span class="t-xs t-muted">JPEG, PNG or WebP. Files are validated and re-encoded by the server.</span>
          <input class="sr-only" id="up-file" name="files" type="file" accept="image/jpeg,image/png,image/webp" multiple required>
        </label>
        <div class="field">
          <label class="field__label" for="up-alt">Alt text <span class="field__req">*</span></label>
          <input class="input" id="up-alt" name="alt_text" required placeholder="Describe the image for screen readers and search engines">
          <p class="field__hint">Applied to every file in this upload. You can refine each one afterwards.</p>
          <p class="field__error" data-error-for="alt_text"></p>
        </div>
        <div class="field">
          <label class="field__label" for="up-kind">Used for</label>
          <select class="select" id="up-kind" name="kind">${KINDS.map(([value, label]) => `<option value="${value}" ${value === 'other' ? 'selected' : ''}>${label}</option>`).join('')}</select>
        </div>
      </form>`,
      footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-upload data-pending-label="Uploading">Upload</button>',
      onMount({ element, close }) {
        const form = element.querySelector('#upload-form');
        hydrateIcons(form);
        const zone = form.querySelector('.dropzone');
        ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.add('is-dragover'); }));
        ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.remove('is-dragover'); }));
        zone.addEventListener('drop', (e) => { form.elements.files.files = e.dataTransfer.files; });

        element.querySelector('[data-upload]').addEventListener('click', async (event) => {
          const files = [...(form.elements.files.files || [])];
          if (!files.length) { toast('Choose at least one image.', { type: 'warning' }); return; }
          const alt = form.elements.alt_text.value.trim();
          if (!alt) { toast('Alt text is required.', { type: 'warning' }); form.elements.alt_text.focus(); return; }
          try {
            await withSubmit(form, event.currentTarget, async () => {
              for (const file of files) {
                const fd = new FormData();
                fd.append('file', file);
                fd.append('alt_text', alt);
                fd.append('kind', form.elements.kind.value);
                await api.upload('/media/uploads/', fd);
              }
            });
            api.invalidate();
            close();
            toast(`${files.length} file${files.length === 1 ? '' : 's'} uploaded.`, { type: 'success' });
            load();
          } catch { /* rendered on form */ }
        });
      },
    });
  }

  document.addEventListener('click', async (event) => {
    if (event.target.closest('[data-media-upload], [data-media-upload-inline]')) { openUpload(); return; }

    const pageButton = event.target.closest('[data-media-page]');
    if (pageButton) { state.page = Number(pageButton.dataset.mediaPage); load(); return; }

    const copy = event.target.closest('[data-media-copy]');
    if (copy) { copyText(copy.dataset.mediaCopy, 'Storage key copied.'); return; }

    const edit = event.target.closest('[data-media-edit]');
    if (edit) {
      const item = (grid.__items || []).find((i) => String(i.id) === edit.dataset.mediaEdit);
      openDialog({
        title: 'Edit media details',
        size: 'narrow',
        body: `<form class="stack" id="media-form" novalidate>
          <div class="alert alert--danger" data-form-error hidden role="alert"></div>
          <img src="${esc(item.url)}" alt="" style="width:100%;border-radius:var(--radius-md)">
          <div class="field"><label class="field__label" for="md-alt">Alt text <span class="field__req">*</span></label>
            <input class="input" id="md-alt" name="alt_text" required value="${esc(item.alt_text || '')}"><p class="field__error" data-error-for="alt_text"></p></div>
          <p class="t-xs t-muted">${esc(item.original_name || '')} · ${esc(item.width || '?')}×${esc(item.height || '?')} · ${esc(formatNumber(Math.round((item.size_bytes || 0) / 1024)))} KB</p>
          ${item.key ? `<div class="field"><label class="field__label" for="md-key">Storage key</label><input class="input t-mono" id="md-key" value="${esc(item.key)}" readonly><p class="field__hint">Paste this where a banner or setting asks for an image key.</p></div>` : ''}
        </form>`,
        footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-save data-pending-label="Saving">Save</button>',
        onMount({ element, close }) {
          const form = element.querySelector('#media-form');
          element.querySelector('[data-save]').addEventListener('click', async (e) => {
            try {
              await withSubmit(form, e.currentTarget, () => api.patch(`/media/assets/${item.id}/`, { alt_text: form.elements.alt_text.value.trim() }));
              api.invalidate(); close(); toast('Media updated.', { type: 'success' }); load();
            } catch { /* rendered */ }
          });
        },
      });
      return;
    }

    const del = event.target.closest('[data-media-delete]');
    if (del) {
      const confirmed = await confirmDialog({
        title: 'Delete this file?', message: 'Products or pages still using it will show a missing image.', confirmLabel: 'Delete', tone: 'danger',
      });
      if (!confirmed) return;
      try { await api.delete(`/media/assets/${del.dataset.mediaDelete}/remove/`); api.invalidate(); toast('File deleted.', { type: 'success' }); load(); }
      catch (error) { toast(error.userMessage, { type: 'danger' }); }
    }
  });

  $('[data-module-search]')?.addEventListener('input', debounce((event) => {
    state.search = event.target.value.trim();
    state.page = 1;
    load();
  }, 350));
  $('[data-module-refresh]')?.addEventListener('click', load);

  load();
}
