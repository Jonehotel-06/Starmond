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
if (await initAdmin()) {
  guardPermission('media.view');

  const root = $('[data-admin-module="media"]');
  const grid = $('[data-media-grid]');
  const state = { page: 1, search: '', pageSize: 24 };

  async function load() {
    grid.setAttribute('aria-busy', 'true');
    grid.innerHTML = `<div class="image-picker" aria-hidden="true">${'<span class="sk sk--square"></span>'.repeat(12)}</div>`;
    try {
      const data = await api.get('/admin/media/', { params: { page: state.page, page_size: state.pageSize, search: state.search || undefined } });
      const list = normalizeList(data);
      $('[data-module-count]').textContent = `${formatNumber(list.count)} file${list.count === 1 ? '' : 's'}`;
      if (!list.results.length) {
        resolveRegion(grid, emptyState({
          title: state.search ? 'No media matches your search' : 'No media uploaded yet',
          text: 'Upload product, category and content imagery here. Alt text is required for accessibility and image SEO.',
          iconName: 'image',
          actionHtml: can('media.create') ? '<button type="button" class="btn btn--primary btn--sm" data-media-upload-inline>Upload media</button>' : '',
        }));
        return;
      }
      resolveRegion(grid, `<div class="image-picker">${list.results.map((item) => `
        <figure class="media-tile">
          <img src="${esc(item.url || item.file)}" alt="${esc(item.alt_text || item.filename || '')}" loading="lazy" decoding="async" width="200" height="200">
          <figcaption class="media-tile__name t-clamp-1">${esc(item.filename || item.name || '')}</figcaption>
          <div class="media-tile__bar">
            <button type="button" class="row-action" style="background:rgba(255,255,255,.9)" data-media-copy="${esc(item.url || item.file)}" aria-label="Copy URL">${icon('copy', { size: 'sm' })}</button>
            ${can('media.update') ? `<button type="button" class="row-action" style="background:rgba(255,255,255,.9)" data-media-edit="${esc(item.id)}" aria-label="Edit alt text">${icon('edit', { size: 'sm' })}</button>` : ''}
            ${can('media.delete') ? `<button type="button" class="row-action row-action--danger" style="background:rgba(255,255,255,.9)" data-media-delete="${esc(item.id)}" aria-label="Delete file">${icon('trash', { size: 'sm' })}</button>` : ''}
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
    nav.innerHTML = Array.from({ length: Math.min(pages, 10) }, (_, i) => `<button type="button" class="pagination__btn" data-media-page="${i + 1}" ${state.page === i + 1 ? 'aria-current="page"' : ''}>${i + 1}</button>`).join('');
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
          <span class="t-xs t-muted">WebP, AVIF, JPEG or PNG. Optimised formats are preferred.</span>
          <input class="sr-only" id="up-file" name="files" type="file" accept="image/*" multiple required>
        </label>
        <div class="field">
          <label class="field__label" for="up-alt">Alt text <span class="field__req">*</span></label>
          <input class="input" id="up-alt" name="alt_text" required placeholder="Describe the image for screen readers and search engines">
          <p class="field__hint">Applied to every file in this upload. You can refine each one afterwards.</p>
          <p class="field__error" data-error-for="alt_text"></p>
        </div>
        <div class="field">
          <label class="field__label" for="up-folder">Folder</label>
          <input class="input" id="up-folder" name="folder" placeholder="products, categories, content">
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
                fd.append('folder', form.elements.folder.value.trim());
                await api.upload('/admin/media/', fd);
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
    if (copy) { copyText(copy.dataset.mediaCopy, 'Image URL copied.'); return; }

    const edit = event.target.closest('[data-media-edit]');
    if (edit) {
      const item = (grid.__items || []).find((i) => String(i.id) === edit.dataset.mediaEdit);
      openDialog({
        title: 'Edit media details',
        size: 'narrow',
        body: `<form class="stack" id="media-form" novalidate>
          <div class="alert alert--danger" data-form-error hidden role="alert"></div>
          <img src="${esc(item.url || item.file)}" alt="" style="width:100%;border-radius:var(--radius-md)">
          <div class="field"><label class="field__label" for="md-alt">Alt text <span class="field__req">*</span></label>
            <input class="input" id="md-alt" name="alt_text" required value="${esc(item.alt_text || '')}"><p class="field__error" data-error-for="alt_text"></p></div>
          <div class="field"><label class="field__label" for="md-caption">Caption</label>
            <input class="input" id="md-caption" name="caption" value="${esc(item.caption || '')}"></div>
        </form>`,
        footer: '<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button><button type="button" class="btn btn--primary" data-save data-pending-label="Saving">Save</button>',
        onMount({ element, close }) {
          const form = element.querySelector('#media-form');
          element.querySelector('[data-save]').addEventListener('click', async (e) => {
            try {
              await withSubmit(form, e.currentTarget, () => api.patch(`/admin/media/${item.id}/`, formData(form)));
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
      try { await api.delete(`/admin/media/${del.dataset.mediaDelete}/`); api.invalidate(); toast('File deleted.', { type: 'success' }); load(); }
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
