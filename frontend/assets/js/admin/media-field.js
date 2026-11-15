/**
 * media-field.js — "image key" form control shared by admin forms.
 *
 * Banners, homepage sections and business/SEO settings store an image as a
 * storage key (not a URL). This control uploads the chosen file to
 * POST /api/media/uploads/ and writes the returned key into the field, so staff
 * never have to copy keys around by hand (they still can, from the media library).
 */
import api from '../api.js';
import { esc } from '../utils.js';

export function mediaKeyControl({ id, name, value = '', previewUrl = '', kind = 'other' }) {
  return `<div class="media-key" data-media-key data-kind="${esc(kind)}">
    <div class="media-key__preview" data-media-key-preview>${previewUrl ? `<img src="${esc(previewUrl)}" alt="">` : '<span class="t-xs t-muted">No image</span>'}</div>
    <div class="media-key__body">
      <input class="input" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload a new image" data-media-key-file>
      <input class="input t-mono" id="${esc(id)}" name="${esc(name)}" type="text" value="${esc(value)}" placeholder="Storage key (filled in after upload)" data-media-key-input>
      <div class="cluster cluster--sm">
        <span class="t-xs t-muted" data-media-key-status aria-live="polite"></span>
        <button type="button" class="link-btn" data-media-key-clear ${value ? '' : 'hidden'}>Remove image</button>
      </div>
    </div>
  </div>`;
}

export function bindMediaKeyControls(root) {
  root.querySelectorAll('[data-media-key]').forEach((box) => {
    if (box.dataset.bound) return;
    box.dataset.bound = '1';
    const input = box.querySelector('[data-media-key-input]');
    const file = box.querySelector('[data-media-key-file]');
    const status = box.querySelector('[data-media-key-status]');
    const preview = box.querySelector('[data-media-key-preview]');
    const clear = box.querySelector('[data-media-key-clear]');
    file.addEventListener('change', async () => {
      const chosen = file.files?.[0];
      if (!chosen) return;
      status.textContent = 'Uploading…';
      file.disabled = true;
      try {
        const fd = new FormData();
        fd.append('file', chosen);
        fd.append('kind', box.dataset.kind || 'other');
        fd.append('alt_text', chosen.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' '));
        const asset = await api.upload('/media/uploads/', fd);
        if (!asset?.key) throw new Error('The server did not return a storage key.');
        input.value = asset.key;
        preview.innerHTML = `<img src="${esc(asset.thumbnail_url || asset.url)}" alt="">`;
        status.textContent = 'Uploaded. Save the form to apply it.';
        clear.hidden = false;
      } catch (error) {
        status.textContent = error?.userMessage || error?.message || 'Upload failed.';
      } finally {
        file.disabled = false;
        file.value = '';
      }
    });
    clear.addEventListener('click', () => {
      input.value = '';
      preview.innerHTML = '<span class="t-xs t-muted">No image</span>';
      status.textContent = 'Image removed. Save the form to apply it.';
      clear.hidden = true;
    });
  });
}
