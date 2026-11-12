/** Shared administration UI primitives: panels, tables, filters, modals, charts. */
import { esc, formatDate, formatDateTime, money, qs } from '../utils.js';
import { openModal, closeModal } from '../ui/modal.js';
import { toast } from '../ui/toast.js';

export function panel({ title, actions = '', body = '', footer = '', flush = false }) {
  return `<section class="panel">
    ${title ? `<header class="panel__head"><h2>${esc(title)}</h2>${actions ? `<div class="admin-actions">${actions}</div>` : ''}</header>` : ''}
    <div class="panel__body${flush ? ' panel__body--flush' : ''}">${body}</div>
    ${footer ? `<footer class="panel__foot">${footer}</footer>` : ''}
  </section>`;
}

export function kpi({ label, value, hint = '', brand = false }) {
  return `<article class="kpi${brand ? ' kpi--brand' : ''}">
    <p class="kpi__label">${esc(label)}</p>
    <p class="kpi__value">${value}</p>
    ${hint ? `<p class="kpi__hint">${esc(hint)}</p>` : ''}
  </article>`;
}

export function emptyRow(cols, message = 'Nothing to show yet.') {
  return `<tr><td colspan="${cols}"><div class="table-empty">${esc(message)}</div></td></tr>`;
}

export function loadingRow(cols) {
  return `<tr><td colspan="${cols}"><div class="skeleton" style="height:34px"></div></td></tr>`;
}

/**
 * Build a data table.
 * columns: [{ key, label, cell(row), num, wrap }]
 */
export function table({ columns, rows, emptyMessage = 'Nothing to show yet.', loading = false }) {
  const head = columns.map((c) => `<th scope="col"${c.num ? ' class="num"' : ''}>${esc(c.label)}</th>`).join('');
  if (loading) {
    return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr>${head}</tr></thead>
      <tbody>${loadingRow(columns.length)}</tbody></table></div>`;
  }
  const body = rows.length
    ? rows.map((row) => `<tr>${columns.map((c) => `<td${c.num ? ' class="num"' : ''}${c.wrap ? ' class="wrap"' : ''}>${c.cell(row)}</td>`).join('')}</tr>`).join('')
    : emptyRow(columns.length, emptyMessage);
  return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function toolbar(parts = []) {
  return `<div class="toolbar">${parts.join('')}</div>`;
}

export function searchField(id, placeholder = 'Search…') {
  return `<div class="toolbar__search">
    <svg class="icon" aria-hidden="true"><use href="#i-search"></use></svg>
    <label class="sr-only" for="${id}">${esc(placeholder)}</label>
    <input class="input" id="${id}" type="search" placeholder="${esc(placeholder)}" data-admin-search>
  </div>`;
}

export function selectField(id, options, { label = 'Filter', value = '' } = {}) {
  return `<label class="sr-only" for="${id}">${esc(label)}</label>
    <select class="input" id="${id}" data-admin-filter>
      ${options.map((o) => `<option value="${esc(o.value)}"${String(value) === String(o.value) ? ' selected' : ''}>${esc(o.label)}</option>`).join('')}
    </select>`;
}

export function pagerBar(pageData) {
  const { page = 1, pages = 1, count = 0 } = pageData || {};
  if (!pageData) return '';
  return `<span class="help-text">Page ${page} of ${pages} · ${count} record${count === 1 ? '' : 's'}</span>
    <span class="admin-actions">
      <button class="btn btn--outline btn--sm" type="button" data-admin-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>Previous</button>
      <button class="btn btn--outline btn--sm" type="button" data-admin-page="${page + 1}" ${page >= pages ? 'disabled' : ''}>Next</button>
    </span>`;
}

export function statusPill(status = '') {
  const value = String(status).toLowerCase();
  const map = {
    paid: 'pill--ok', delivered: 'pill--ok', active: 'pill--ok', approved: 'pill--ok', completed: 'pill--ok', confirmed: 'pill--ok',
    pending_payment: 'pill--warn', pending: 'pill--warn', processing: 'pill--warn', draft: 'pill--warn', review: 'pill--warn', initiated: 'pill--warn',
    shipped: 'pill--info', in_transit: 'pill--info',
    cancelled: 'pill--danger', failed: 'pill--danger', rejected: 'pill--danger', refunded: 'pill--danger', disabled: 'pill--danger'
  };
  return `<span class="pill ${map[value] || ''}">${esc(String(status || '—').replace(/_/g, ' '))}</span>`;
}

export function thumb(url, alt = '') {
  return url ? `<img class="thumb" src="${esc(url)}" alt="${esc(alt)}" width="34" height="34" loading="lazy">` : '<span class="thumb" aria-hidden="true"></span>';
}

/* ------------------------------------------------------------------- forms */
function fieldHtml(field, value) {
  const id = `fld-${field.name}`;
  const common = `id="${id}" name="${esc(field.name)}" ${field.required ? 'required' : ''} ${field.step ? `step="${field.step}"` : ''} ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}`;
  const label = `<label for="${id}">${esc(field.label)}${field.required ? ' <span class="req" aria-hidden="true">*</span>' : ''}</label>`;
  let control = '';
  if (field.type === 'select') {
    control = `<select class="input" ${common}>${(field.options || []).map((o) => `<option value="${esc(o.value)}"${String(value) === String(o.value) ? ' selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
  } else if (field.type === 'textarea') {
    control = `<textarea class="input" rows="${field.rows || 4}" ${common}>${esc(value ?? '')}</textarea>`;
  } else if (field.type === 'checkbox') {
    return `<label class="check field--full"><input type="checkbox" name="${esc(field.name)}" ${value ? 'checked' : ''}><span>${esc(field.label)}</span></label>`;
  } else {
    control = `<input class="input" type="${field.type || 'text'}" value="${esc(value ?? '')}" ${common}>`;
  }
  return `<div class="field${field.full ? ' field--full' : ''}">${label}${control}
    ${field.help ? `<p class="help-text">${esc(field.help)}</p>` : ''}
    <p class="field-error" data-error-for="${esc(field.name)}" hidden></p></div>`;
}

/**
 * Open a modal form.
 * fields: [{ name, label, type, required, options, help, full, rows, step }]
 * onSubmit(values, { close, setBusy, setFieldError, form }) — throw to keep it open.
 */
export function formModal({ title, fields, values = {}, submitLabel = 'Save', size = '', onSubmit, note = '' }) {
  const body = `<form class="admin-form" data-admin-form novalidate>
      ${note ? `<p class="help-text">${esc(note)}</p>` : ''}
      <div class="form-grid">${fields.map((f) => fieldHtml(f, values[f.name])).join('')}</div>
      <p class="form-error" data-form-error role="alert" hidden></p>
    </form>`;

  openModal({
    title,
    size,
    body,
    footer: `<button class="btn btn--ghost" type="button" data-form-cancel>Cancel</button>
             <button class="btn btn--primary" type="submit" form="" data-form-submit>${esc(submitLabel)}</button>`,
    onMount: ({ body: bodyEl, footer, close }) => {
      const form = bodyEl.querySelector('form');
      const submitBtn = footer.querySelector('[data-form-submit]');
      const errorEl = form.querySelector('[data-form-error]');
      footer.querySelector('[data-form-cancel]').addEventListener('click', close);

      const submit = async () => {
        errorEl.hidden = true;
        const data = new FormData(form);
        const out = {};
        fields.forEach((field) => {
          if (field.type === 'checkbox') out[field.name] = data.get(field.name) === 'on';
          else out[field.name] = data.get(field.name) ?? '';
        });
        let valid = true;
        fields.forEach((field) => {
          if (!field.required) return;
          if (field.type === 'checkbox') return;
          if (!String(out[field.name] || '').trim()) {
            setFieldError(field.name, `${field.label} is required.`);
            valid = false;
          }
        });
        if (!valid) return;
        submitBtn.disabled = true;
        try {
          await onSubmit(out, { close, form });
          close();
        } catch (err) {
          if (err?.fields) Object.entries(err.fields).forEach(([k, v]) => setFieldError(k, v));
          errorEl.textContent = err?.message || 'Could not save. Please try again.';
          errorEl.hidden = false;
        } finally {
          submitBtn.disabled = false;
        }
      };

      const setFieldError = (name, message) => {
        const slot = form.querySelector(`[data-error-for="${name}"]`);
        const input = form.querySelector(`[name="${name}"]`);
        if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false');
        if (slot) { slot.textContent = message || ''; slot.hidden = !message; }
      };

      submitBtn.addEventListener('click', submit);
      form.addEventListener('submit', (event) => { event.preventDefault(); submit(); });
    }
  });
}

/* ------------------------------------------------------------------ charts */
export function barChart(series, { labelKey = 'label', valueKey = 'value' } = {}) {
  if (!series?.length) return '<p class="help-text">No data for this period.</p>';
  const values = series.map((d) => Number(d[valueKey] ?? 0));
  const max = Math.max(...values, 1);
  /* Rendered with HTML/CSS rather than a stretched SVG so the labels keep a
     natural aspect ratio at every panel width. */
  const cols = series.map((d) => {
    const value = Number(d[valueKey] ?? 0);
    const pct = Math.max(value > 0 ? 1.5 : 0, (value / max) * 100);
    return `<div class="chart__col">
        <span class="chart__bar" style="height:${pct.toFixed(1)}%"
          role="img" aria-label="${esc(String(d[labelKey]))}: ${money(value)}"
          title="${esc(String(d[labelKey]))}: ${money(value)}"></span>
      </div>`;
  }).join('');
  const labels = series
    .map((d) => `<span>${esc(String(d[labelKey]).slice(0, 6))}</span>`)
    .join('');
  return `<div class="chart">
    <p class="chart__max">Peak ${money(max)}</p>
    <div class="chart__plot" role="img" aria-label="Bar chart of verified revenue across ${series.length} periods">${cols}</div>
    <div class="chart__labels" aria-hidden="true">${labels}</div>
  </div>`;
}

export function miniBarChart(series, { labelKey = 'label', valueKey = 'value' } = {}) {
  if (!series?.length) return '<p class="help-text">No data for this period.</p>';
  const max = Math.max(...series.map((d) => Number(d[valueKey] ?? 0)), 1);
  return `<ol style="list-style:none;padding:0;margin:0;display:grid;gap:.5rem">
    ${series.map((d) => {
      const value = Number(d[valueKey] ?? 0);
      const pct = Math.round((value / max) * 100);
      return `<li style="display:grid;grid-template-columns:110px 1fr 90px;gap:.5rem;align-items:center;font-size:.82rem">
        <span>${esc(d[labelKey])}</span>
        <span style="background:var(--bg-tint);border-radius:999px;height:8px;overflow:hidden">
          <span style="display:block;height:100%;width:${pct}%;background:var(--brand-600)"></span></span>
        <span style="text-align:right;font-variant-numeric:tabular-nums">${money(value)}</span>
      </li>`;
    }).join('')}
  </ol>`;
}

/* ----------------------------------------------------------------- export */
export function exportCsv(filename, columns, rows) {
  const head = columns.map((c) => `"${String(c.label).replace(/"/g, '""')}"`).join(',');
  const body = rows.map((row) => columns
    .map((c) => `"${String(c.value(row) ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([`${head}\n${body}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  toast(`Exported ${rows.length} row${rows.length === 1 ? '' : 's'} to ${filename}.`, { type: 'success' });
}

export { closeModal, formatDate, formatDateTime, money, qs };
