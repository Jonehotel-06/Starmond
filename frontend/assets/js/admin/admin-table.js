/**
 * admin-table.js — configuration-driven CRUD engine for administration modules.
 *
 * One engine serves products, categories, orders, customers, payments, refunds,
 * discounts, promotions, reviews, enquiries, staff, audit logs and more. Each
 * module supplies a declarative config (endpoint, columns, filters, form
 * fields, permissions); the engine handles fetching, skeletons, pagination,
 * search, empty/error states, dialogs and mutations.
 *
 * It never computes business values. Money, stock and totals are rendered
 * exactly as the backend returns them.
 */

import api, { normalizeList, fieldErrorMap } from '../api.js';
import { can } from '../auth.js';
import {
  skeletons, resolveRegion, renderRegionError, emptyState, toast, openDialog,
  confirmDialog, withSubmit, formData, applyFormErrors, downloadBlob, announce,
} from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, debounce, formatMoney, formatDate, formatDateTime, formatNumber, titleCase, truncate } from '../utils.js';
import { mediaKeyControl, bindMediaKeyControls } from './media-field.js';
import { applyPermissions } from './admin-core.js';

const DEFAULT_PAGE_SIZE = 20;

export class AdminTable {
  /**
   * @param {HTMLElement} root element carrying [data-admin-module]
   * @param {object} config
   */
  constructor(root, config) {
    this.root = root;
    this.config = config;
    this.state = {
      page: 1,
      search: new URLSearchParams(location.search).get('q') || '',
      filters: Object.fromEntries((config.filters || [])
        .map((filter) => [filter.key, new URLSearchParams(location.search).get(filter.key)])
        .filter(([, value]) => value)),
      ordering: config.defaultOrdering || '',
      selected: new Set(),
      rows: [],
      count: 0,
    };
    this.controller = null;
    this.pageSize = config.pageSize || DEFAULT_PAGE_SIZE;
  }

  /** Identifier used in URLs for a row (orders use `reference`, CMS pages use `slug`). */
  rowId(row) { return row?.[this.config.idKey || 'id']; }
  findRow(id) { return this.state.rows.find((r) => String(this.rowId(r)) === String(id)); }
  detailUrl(row) { return `${this.config.endpoint}${encodeURIComponent(this.rowId(row))}/`; }

  /* ------------------------------------------------------------- mount -- */

  async mount() {
    this.tableRegion = this.root.querySelector('[data-module-table]');
    this.countNode = this.root.querySelector('[data-module-count]');
    this.paginationNode = this.root.querySelector('[data-module-pagination]');
    this.filtersNode = this.root.querySelector('[data-module-filters]');
    this.bulkNode = this.root.querySelector('[data-module-bulk]');

    this.renderFilters();
    this.bindToolbar();
    await this.load();
  }

  bindToolbar() {
    const search = this.root.querySelector('[data-module-search]');
    if (search && this.config.searchable === false) {
      // This endpoint has no text search — do not show a box that does nothing.
      search.closest('.data-panel__search')?.setAttribute('hidden', '');
      this.state.search = '';
    } else if (search) {
      search.value = this.state.search;
      search.addEventListener('input', debounce(() => {
        this.state.search = search.value.trim();
        this.state.page = 1;
        this.load();
      }, 350));
    }
    this.root.querySelector('[data-module-refresh]')?.addEventListener('click', () => this.load());

    const exportButton = this.root.querySelector('[data-module-export]');
    if (exportButton && this.config.exportable) {
      exportButton.hidden = false;
      exportButton.addEventListener('click', () => this.export());
    }

    const createButton = document.querySelector('[data-create]');
    if (createButton && this.config.form) {
      createButton.addEventListener('click', () => this.openForm());
    }

    this.root.addEventListener('click', (event) => this.onRootClick(event));
    this.root.addEventListener('change', (event) => {
      const checkbox = event.target.closest('[data-row-select]');
      if (checkbox) {
        const id = checkbox.dataset.rowSelect;
        if (checkbox.checked) this.state.selected.add(id); else this.state.selected.delete(id);
        this.renderBulkBar();
      }
      if (event.target.matches('[data-select-all]')) {
        const checked = event.target.checked;
        this.state.selected = checked ? new Set(this.state.rows.map((r) => String(this.rowId(r)))) : new Set();
        this.root.querySelectorAll('[data-row-select]').forEach((box) => { box.checked = checked; });
        this.renderBulkBar();
      }
    });
  }

  renderFilters() {
    if (!this.filtersNode || !this.config.filters?.length) return;
    this.filtersNode.innerHTML = this.config.filters.map((filter) => {
      const id = `filter-${this.config.id}-${filter.key}`;
      if (filter.type === 'select') {
        return `<span><label class="sr-only" for="${id}">${esc(filter.label)}</label>
          <select class="select" id="${id}" data-filter-key="${esc(filter.key)}">
            <option value="">${esc(filter.placeholder || filter.label)}</option>
            ${(filter.options || []).map((option) => {
              const value = typeof option === 'object' ? option.value : option;
              const label = typeof option === 'object' ? option.label : titleCase(option);
              return `<option value="${esc(value)}">${esc(label)}</option>`;
            }).join('')}
          </select></span>`;
      }
      if (filter.type === 'date') {
        return `<span><label class="sr-only" for="${id}">${esc(filter.label)}</label>
          <input class="input input--sm" id="${id}" type="date" data-filter-key="${esc(filter.key)}" style="width:auto"></span>`;
      }
      return '';
    }).join('');

    // Async option sources (e.g. categories) are resolved from the API.
    this.config.filters.forEach(async (filter) => {
      if (!filter.source) return;
      const select = this.filtersNode.querySelector(`[data-filter-key="${CSS.escape(filter.key)}"]`);
      if (!select) return;
      try {
        const data = await api.get(filter.source, { params: filter.sourceParams || { page_size: 100 } });
        const list = normalizeList(data).results;
        select.insertAdjacentHTML('beforeend', list.map((item) => `<option value="${esc(item[filter.valueKey || 'id'])}">${esc(item[filter.labelKey || 'name'])}</option>`).join(''));
        if (this.state.filters[filter.key] != null) select.value = this.state.filters[filter.key];
      } catch { /* leave the "all" option only */ }
    });

    this.filtersNode.querySelectorAll('[data-filter-key]').forEach((input) => {
      // Deep links such as /admin/orders.html?status=pending_payment preset a filter.
      const preset = this.state.filters[input.dataset.filterKey];
      if (preset != null) input.value = preset;
      input.addEventListener('change', () => {
        const key = input.dataset.filterKey;
        if (input.value) this.state.filters[key] = input.value; else delete this.state.filters[key];
        this.state.page = 1;
        this.load();
      });
    });
  }

  /* -------------------------------------------------------------- load -- */

  params() {
    return {
      page: this.state.page,
      page_size: this.pageSize,
      [this.config.searchParam || 'search']: this.state.search || undefined,
      ordering: this.state.ordering || undefined,
      ...this.state.filters,
      ...(this.config.extraParams || {}),
    };
  }

  async load() {
    this.controller?.abort();
    this.controller = new AbortController();
    this.tableRegion.setAttribute('aria-busy', 'true');
    this.tableRegion.innerHTML = skeletons.table(8, Math.min(this.config.columns.length, 6));

    try {
      const data = await api.get(this.config.endpoint, { params: this.params(), signal: this.controller.signal, dedupe: false });
      const list = normalizeList(data);
      this.state.rows = list.results;
      this.state.count = list.count;
      this.render();
      announce(`${list.count} ${this.config.label || 'records'} loaded`);
    } catch (error) {
      if (error.isAborted) return;
      if (error.isForbidden) {
        resolveRegion(this.tableRegion, emptyState({
          title: 'You do not have permission to view this',
          text: 'Ask a super administrator to grant your role access to this module.',
          iconName: 'lock',
        }));
        return;
      }
      renderRegionError(this.tableRegion, error, () => this.load(), { title: `${this.config.label || 'Records'} could not be loaded` });
    }
  }

  /* ------------------------------------------------------------ render -- */

  render() {
    const { columns, label } = this.config;
    if (!this.state.rows.length) {
      resolveRegion(this.tableRegion, emptyState({
        title: this.state.search || Object.keys(this.state.filters).length
          ? `No ${label || 'records'} match your search`
          : `No ${label || 'records'} yet`,
        text: this.state.search ? 'Try a different search term or clear the filters.' : (this.config.emptyText || 'Records will appear here once they exist.'),
        iconName: this.config.emptyIcon || 'inbox',
        actionHtml: this.config.form && can(this.config.permissions?.create)
          ? `<button type="button" class="btn btn--primary btn--sm" data-create-inline>${icon('plus', { size: 'sm' })} ${esc(this.config.createLabel || 'Create')}</button>`
          : '',
      }));
      this.countNode.textContent = `0 ${label || 'records'}`;
      this.paginationNode.innerHTML = '';
      this.renderBulkBar();
      return;
    }

    const selectable = !!this.config.bulkActions?.length;
    const head = `<thead><tr>
      ${selectable ? '<th scope="col" style="width:36px"><label class="sr-only" for="select-all">Select all rows</label><input type="checkbox" id="select-all" data-select-all></th>' : ''}
      ${columns.map((column) => `<th scope="col" class="${column.numeric ? 'num' : ''}">${
        column.sortable
          ? `<button type="button" class="table__sortable" data-sort="${esc(column.sortKey || column.key)}">${esc(column.label)} ${icon('chevron-down', { size: 'sm' })}</button>`
          : esc(column.label)
      }</th>`).join('')}
      <th scope="col" class="num"><span class="sr-only">Actions</span></th>
    </tr></thead>`;

    const body = `<tbody>${this.state.rows.map((row) => `<tr data-row-id="${esc(this.rowId(row))}">
      ${selectable ? `<td data-label="Select"><input type="checkbox" data-row-select="${esc(this.rowId(row))}" aria-label="Select ${esc(this.rowLabel(row))}" ${this.state.selected.has(String(this.rowId(row))) ? 'checked' : ''}></td>` : ''}
      ${columns.map((column) => `<td data-label="${esc(column.label)}" class="${column.numeric ? 'num' : ''}">${this.renderCell(row, column)}</td>`).join('')}
      <td data-label="Actions" class="table__actions">${this.renderRowActions(row)}</td>
    </tr>`).join('')}</tbody>`;

    resolveRegion(this.tableRegion, `<div class="table-wrap"><table class="table table--responsive">
      <caption class="sr-only">${esc(label || 'Records')}</caption>${head}${body}
    </table></div>`);

    const from = (this.state.page - 1) * this.pageSize + 1;
    const to = Math.min(this.state.page * this.pageSize, this.state.count);
    this.countNode.textContent = `Showing ${from}–${to} of ${formatNumber(this.state.count)} ${label || 'records'}`;
    this.renderPagination();
    this.renderBulkBar();
    applyPermissions(this.tableRegion);
  }

  renderCell(row, column) {
    const value = column.key.split('.').reduce((acc, part) => (acc == null ? acc : acc[part]), row);
    switch (column.type) {
      case 'money':
        return value != null ? `<span class="price">${esc(formatMoney(value, row.currency || column.currency || 'NGN'))}</span>` : '<span class="cell-muted">—</span>';
      case 'number':
        return value != null ? esc(formatNumber(value)) : '<span class="cell-muted">—</span>';
      case 'date':
        return value ? esc(formatDate(value)) : '<span class="cell-muted">—</span>';
      case 'datetime':
        return value ? esc(formatDateTime(value)) : '<span class="cell-muted">—</span>';
      case 'status': {
        const tone = column.tones?.[value] || 'neutral';
        const text = column.labels?.[value] || titleCase(value || 'unknown');
        return `<span class="badge badge--${tone} badge--dot">${esc(text)}</span>`;
      }
      case 'boolean':
        return value
          ? `<span class="badge badge--success">${icon('check', { size: 'sm' })} ${esc(column.trueLabel || 'Yes')}</span>`
          : `<span class="badge badge--neutral">${esc(column.falseLabel || 'No')}</span>`;
      case 'image': {
        const url = column.resolve ? column.resolve(row) : value;
        return `<span class="table__cell-flex">${url
          ? `<img class="table__thumb" src="${esc(url)}" alt="" width="40" height="40" loading="lazy" decoding="async">`
          : `<span class="table__thumb" aria-hidden="true" style="display:inline-flex;align-items:center;justify-content:center;color:var(--color-border-strong)">${icon('image', { size: 'sm' })}</span>`}
          <span class="cell-stack"><span class="table__primary t-clamp-1">${esc(row[column.primaryKey || 'name'] || '')}</span>
          ${column.subKey ? `<span class="cell-muted t-clamp-1">${esc(row[column.subKey] || '')}</span>` : ''}</span></span>`;
      }
      case 'primary':
        return `<span class="cell-stack"><span class="table__primary">${esc(value ?? '—')}</span>${column.subKey ? `<span class="cell-muted">${esc(row[column.subKey] ?? '')}</span>` : ''}</span>`;
      case 'link':
        return value ? `<a href="${esc(column.href(row))}">${esc(value)}</a>` : '<span class="cell-muted">—</span>';
      case 'custom':
        return column.render(row);
      case 'truncate':
        return `<span class="t-clamp-2">${esc(truncate(String(value ?? ''), column.length || 90))}</span>`;
      default:
        return value === null || value === undefined || value === ''
          ? '<span class="cell-muted">—</span>'
          : esc(String(value));
    }
  }

  renderRowActions(row) {
    const actions = [];
    const perms = this.config.permissions || {};
    if (this.config.viewUrl) {
      actions.push(`<a class="row-action" href="${esc(this.config.viewUrl(row))}" aria-label="View ${esc(this.rowLabel(row))}">${icon('eye', { size: 'sm' })}</a>`);
    }
    if (this.config.form && can(perms.update)) {
      actions.push(`<button type="button" class="row-action" data-edit="${esc(this.rowId(row))}" data-perm="${esc(perms.update || '')}" aria-label="Edit ${esc(this.rowLabel(row))}">${icon('edit', { size: 'sm' })}</button>`);
    }
    (this.config.rowActions || []).forEach((action) => {
      if (action.when && !action.when(row)) return;
      if (action.perm && !can(action.perm)) return;
      actions.push(`<button type="button" class="row-action ${action.tone === 'danger' ? 'row-action--danger' : ''}" data-row-action="${esc(action.id)}" data-id="${esc(this.rowId(row))}" aria-label="${esc(action.label)} ${esc(this.rowLabel(row))}">${icon(action.icon, { size: 'sm' })}</button>`);
    });
    if (this.config.deletable && can(perms.delete)) {
      actions.push(`<button type="button" class="row-action row-action--danger" data-delete="${esc(this.rowId(row))}" data-perm="${esc(perms.delete || '')}" aria-label="${this.config.archiveLabel ? 'Archive' : 'Delete'} ${esc(this.rowLabel(row))}">${icon(this.config.archiveLabel ? 'archive' : 'trash', { size: 'sm' })}</button>`);
    }
    return `<span class="row-actions">${actions.join('')}</span>`;
  }

  rowLabel(row) {
    return row?.[this.config.labelKey || 'name'] || row?.reference || row?.email || `#${this.rowId(row)}`;
  }

  renderPagination() {
    const pages = Math.max(1, Math.ceil(this.state.count / this.pageSize));
    if (pages <= 1) { this.paginationNode.innerHTML = ''; return; }
    const items = [];
    const add = (page, label, { current = false, disabled = false } = {}) => {
      items.push(disabled
        ? `<span class="pagination__btn" aria-disabled="true">${label}</span>`
        : `<button type="button" class="pagination__btn" data-page="${page}" ${current ? 'aria-current="page"' : ''}>${label}</button>`);
    };
    add(this.state.page - 1, icon('chevron-left', { size: 'sm' }), { disabled: this.state.page === 1 });
    const window_ = [...new Set([1, pages, this.state.page, this.state.page - 1, this.state.page + 1])]
      .filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b);
    let last = 0;
    window_.forEach((page) => {
      if (last && page - last > 1) items.push('<span class="pagination__gap">…</span>');
      add(page, String(page), { current: page === this.state.page });
      last = page;
    });
    add(this.state.page + 1, icon('chevron-right', { size: 'sm' }), { disabled: this.state.page === pages });
    this.paginationNode.innerHTML = items.join('');
    hydrateIcons(this.paginationNode);
  }

  renderBulkBar() {
    if (!this.bulkNode) return;
    const count = this.state.selected.size;
    if (!count || !this.config.bulkActions?.length) { this.bulkNode.hidden = true; this.bulkNode.innerHTML = ''; return; }
    this.bulkNode.hidden = false;
    this.bulkNode.innerHTML = `<div class="data-panel__bulk">
      <strong>${count} selected</strong>
      ${this.config.bulkActions.map((action) => `<button type="button" class="btn btn--sm ${action.tone === 'danger' ? 'btn--danger-soft' : 'btn--secondary'}" data-bulk="${esc(action.id)}" ${action.perm ? `data-perm="${esc(action.perm)}"` : ''}>${esc(action.label)}</button>`).join('')}
      <button type="button" class="link-btn" data-bulk-clear>Clear selection</button>
    </div>`;
    applyPermissions(this.bulkNode);
  }

  /* ------------------------------------------------------------ events -- */

  async onRootClick(event) {
    const pageButton = event.target.closest('[data-page]');
    if (pageButton) { this.state.page = Number(pageButton.dataset.page); this.load(); return; }

    const sortButton = event.target.closest('[data-sort]');
    if (sortButton) {
      const key = sortButton.dataset.sort;
      this.state.ordering = this.state.ordering === key ? `-${key}` : key;
      this.state.page = 1;
      this.load();
      return;
    }

    const editButton = event.target.closest('[data-edit]');
    if (editButton) {
      const row = this.findRow(editButton.dataset.edit);
      this.openForm(row);
      return;
    }

    if (event.target.closest('[data-create-inline]')) { this.openForm(); return; }

    const deleteButton = event.target.closest('[data-delete]');
    if (deleteButton) { await this.remove(deleteButton.dataset.delete); return; }

    const rowAction = event.target.closest('[data-row-action]');
    if (rowAction) {
      const action = (this.config.rowActions || []).find((a) => a.id === rowAction.dataset.rowAction);
      const row = this.findRow(rowAction.dataset.id);
      if (action?.handler) await action.handler(row, this);
      return;
    }

    const bulkButton = event.target.closest('[data-bulk]');
    if (bulkButton) { await this.runBulk(bulkButton.dataset.bulk); return; }

    if (event.target.closest('[data-bulk-clear]')) {
      this.state.selected.clear();
      this.root.querySelectorAll('[data-row-select]').forEach((box) => { box.checked = false; });
      this.renderBulkBar();
    }
  }

  async remove(id) {
    const row = this.findRow(id);
    if (!row) return;
    const archive = !!this.config.archiveLabel;
    const confirmed = await confirmDialog({
      title: archive ? `Archive ${this.rowLabel(row)}?` : `Delete ${this.rowLabel(row)}?`,
      message: archive
        ? 'Archived records are hidden from the storefront but retained for your records.'
        : (this.config.deleteMessage || 'This permanently removes the record. This cannot be undone.'),
      confirmLabel: archive ? 'Archive' : 'Delete',
      tone: 'danger',
    });
    if (!confirmed) return;
    try {
      let result;
      if (this.config.remove) result = await this.config.remove(row, this);
      else if (archive) result = await api.post(`${this.detailUrl(row)}archive/`, {});
      else result = await api.delete(this.detailUrl(row));
      api.invalidate();
      // The backend may soften a delete (e.g. archive a product with order history).
      toast(result?.message || (archive ? 'Record archived.' : 'Record deleted.'), { type: 'success' });
      this.state.selected.delete(String(id));
      this.load();
    } catch (error) {
      toast(error?.userMessage || 'The action could not be completed.', { type: 'danger' });
    }
  }

  /**
   * Bulk actions run the action's `run(row, table)` once per selected row.
   * The backend exposes no bulk endpoints, so each row is a normal audited
   * request and partial failures are reported honestly.
   */
  async runBulk(actionId) {
    const action = this.config.bulkActions.find((a) => a.id === actionId);
    if (!action?.run) return;
    const rows = [...this.state.selected].map((id) => this.findRow(id)).filter(Boolean);
    if (!rows.length) return;
    const confirmed = await confirmDialog({
      title: `${action.label} — ${rows.length} record${rows.length === 1 ? '' : 's'}?`,
      message: action.confirm || 'This applies the action to every selected record.',
      confirmLabel: action.label,
      tone: action.tone === 'danger' ? 'danger' : 'primary',
    });
    if (!confirmed) return;
    let done = 0;
    const failures = [];
    for (const row of rows) {
      try { await action.run(row, this); done += 1; }
      catch (error) { failures.push(`${this.rowLabel(row)}: ${error?.userMessage || 'failed'}`); }
    }
    api.invalidate();
    this.state.selected.clear();
    if (done) toast(`${done} record${done === 1 ? '' : 's'} updated.`, { type: 'success' });
    if (failures.length) {
      toast(`${failures.length} could not be updated. ${failures.slice(0, 2).join(' · ')}`, { type: 'danger', duration: 9000 });
    }
    this.load();
  }

  /**
   * CSV export of the CURRENT search/filter result. Rows are read page by page
   * from the list endpoint (the API caps a page at 100 rows) and the file is
   * built in the browser — nothing is fabricated or summarised.
   */
  async export() {
    const MAX_ROWS = 5000;
    try {
      toast('Preparing export…', { type: 'info', duration: 2500 });
      const rows = [];
      let page = 1;
      let total = Infinity;
      while (rows.length < total && rows.length < MAX_ROWS) {
        const data = await api.get(this.config.endpoint, { params: { ...this.params(), page, page_size: 100 }, dedupe: false, cache: false });
        const list = normalizeList(data);
        total = list.count;
        if (!list.results.length) break;
        rows.push(...list.results);
        page += 1;
      }
      if (!rows.length) { toast('There is nothing to export for the current filters.', { type: 'info' }); return; }
      const columns = this.config.exportColumns
        || this.config.columns.filter((c) => c.type !== 'custom').map((c) => ({ key: c.key, label: c.label }));
      const pick = (row, key) => key.split('.').reduce((acc, part) => (acc == null ? acc : acc[part]), row);
      const cell = (value) => {
        if (value === null || value === undefined) return '';
        let text = typeof value === 'object' ? JSON.stringify(value) : String(value);
        // Neutralise spreadsheet formula injection from user-supplied text.
        if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
        return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      };
      const lines = [columns.map((c) => cell(c.label)).join(',')];
      rows.forEach((row) => lines.push(columns.map((c) => cell(c.value ? c.value(row) : pick(row, c.key))).join(',')));
      const blob = new Blob(['\ufeff', lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      downloadBlob(blob, `${this.config.id}-${new Date().toISOString().slice(0, 10)}.csv`);
      toast(rows.length < total
        ? `Exported the first ${formatNumber(rows.length)} of ${formatNumber(total)} rows. Narrow the filters to export the rest.`
        : `Exported ${formatNumber(rows.length)} row${rows.length === 1 ? '' : 's'}.`, { type: 'success' });
    } catch (error) {
      toast(error?.userMessage || 'The export could not be completed.', { type: 'danger' });
    }
  }


  openForm(row = null) {
    const config = this.config;
    const isEdit = !!row;
    const fields = typeof config.form === 'function' ? config.form(row) : config.form;

    openDialog({
      title: isEdit ? `Edit ${config.singular || 'record'}` : (config.createLabel || `New ${config.singular || 'record'}`),
      sub: isEdit ? this.rowLabel(row) : (config.formHint || ''),
      size: 'wide',
      body: `<form class="admin-form" id="admin-entity-form" novalidate>
        <div class="alert alert--danger" data-form-error hidden role="alert"></div>
        ${renderFields(fields, row)}
      </form>`,
      footer: `<button type="button" class="btn btn--secondary" data-dialog-close>Cancel</button>
        <button type="button" class="btn btn--primary" data-save-entity data-pending-label="Saving">${isEdit ? 'Save changes' : 'Create'}</button>`,
      onMount: ({ element, close }) => {
        const form = element.querySelector('#admin-entity-form');
        hydrateIcons(form);
        bindFieldBehaviours(form, fields);
        element.querySelector('[data-save-entity]').addEventListener('click', async (event) => {
          const button = event.currentTarget;
          const values = collectValues(form, fields);
          const errors = validateFields(fields, values);
          if (Object.keys(errors).length) { applyFormErrors(form, errors); return; }
          try {
            await withSubmit(form, button, async () => {
              const prepared = preparePayload(fields, values, form);
              const files = prepared.files;
              let body = prepared.body;
              if (config.toPayload) body = await config.toPayload(body, { row, isEdit, values, form });
              // 1) Save the record as JSON (so nested/JSON fields keep their types).
              const saved = isEdit
                ? await api.patch(this.detailUrl(row), body)
                : await api.post(config.createEndpoint || config.endpoint, body);
              const target = saved && typeof saved === 'object' ? { ...(row || {}), ...saved } : row;
              // 2) Then send files. Modules with dedicated upload routes handle
              //    them in `afterSave`; otherwise they go to the record itself.
              if (config.afterSave) await config.afterSave(target, { files, values, form, isEdit, table: this });
              else if (files.length && target) {
                const fd = new FormData();
                files.forEach(({ name, file }) => fd.append(name, file));
                await api.upload(this.detailUrl(target), fd, { method: 'PATCH' });
              }
              return saved;
            });
            api.invalidate();
            close();
            toast(isEdit ? 'Changes saved.' : 'Created successfully.', { type: 'success' });
            this.load();
          } catch { /* withSubmit renders field errors */ }
        });
      },
    });
  }
}

/* ============================================================================
   Field rendering
   ========================================================================== */

const INVALID_JSON = Symbol('invalid-json');

/** ISO timestamp → value for <input type="datetime-local"> in the user's timezone. */
function toLocalInput(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function renderFields(fields, row) {
  const sections = new Map();
  fields.forEach((field) => {
    const section = field.section || 'Details';
    if (!sections.has(section)) sections.set(section, []);
    sections.get(section).push(field);
  });
  return [...sections.entries()].map(([section, items]) => `
    <div class="admin-form__section">
      <p class="admin-form__section-title">${esc(section)}</p>
      <div class="form-grid">${items.map((field) => renderField(field, row)).join('')}</div>
    </div>`).join('');
}

function currentValue(field, row) {
  if (!row) return field.default ?? '';
  const value = field.key.split('.').reduce((acc, part) => (acc == null ? acc : acc[part]), row);
  return value ?? field.default ?? '';
}

function renderField(field, row) {
  const value = currentValue(field, row);
  const id = `f-${field.key.replace(/\./g, '-')}`;
  const required = field.required ? '<span class="field__req" aria-hidden="true">*</span>' : '';
  const full = field.full || ['textarea', 'richtext', 'images', 'json', 'keyvalue', 'mediakey'].includes(field.type);
  const wrap = (control) => `<div class="field ${full ? 'form-grid__full' : ''}">
    <label class="field__label" for="${id}">${esc(field.label)} ${required}</label>
    ${control}
    ${field.hint ? `<p class="field__hint">${esc(field.hint)}</p>` : ''}
    <p class="field__error" data-error-for="${esc(field.key)}"></p>
  </div>`;

  switch (field.type) {
    case 'textarea':
      return wrap(`<textarea class="textarea" id="${id}" name="${esc(field.key)}" rows="${field.rows || 4}" ${field.required ? 'required' : ''} maxlength="${field.maxLength || 5000}">${esc(value)}</textarea>`);
    case 'richtext':
      return wrap(`<textarea class="textarea" id="${id}" name="${esc(field.key)}" rows="8" data-richtext>${esc(value)}</textarea>`);
    case 'number':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="number" value="${esc(value)}" ${field.min != null ? `min="${field.min}"` : ''} ${field.max != null ? `max="${field.max}"` : ''} ${field.step ? `step="${field.step}"` : ''} ${field.required ? 'required' : ''} inputmode="decimal">`);
    case 'money':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="number" min="0" step="0.01" value="${esc(value)}" ${field.required ? 'required' : ''} inputmode="decimal">`);
    case 'select':
      return wrap(`<select class="select" id="${id}" name="${esc(field.key)}" ${field.required ? 'required' : ''} ${field.source ? `data-selected="${esc((value && typeof value === 'object' ? value.id : value) ?? '')}" data-source="${esc(field.source)}" data-value-key="${esc(field.valueKey || 'id')}" data-label-key="${esc(field.labelKey || 'name')}"` : ''}>
        <option value="">${esc(field.placeholder || 'Select…')}</option>
        ${(field.options || []).map((option) => {
          const val = typeof option === 'object' ? option.value : option;
          const label = typeof option === 'object' ? option.label : titleCase(option);
          return `<option value="${esc(val)}" ${String(value) === String(val) ? 'selected' : ''}>${esc(label)}</option>`;
        }).join('')}
      </select>`);
    case 'checkbox':
    case 'switch':
      return `<div class="field ${full ? 'form-grid__full' : ''}">
        <label class="switch"><input type="checkbox" id="${id}" name="${esc(field.key)}" ${value ? 'checked' : ''}><span class="switch__track"></span><span>${esc(field.label)}</span></label>
        ${field.hint ? `<p class="field__hint">${esc(field.hint)}</p>` : ''}
      </div>`;
    case 'date':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="date" value="${esc(String(value).slice(0, 10))}" ${field.required ? 'required' : ''}>`);
    case 'datetime':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="datetime-local" value="${esc(toLocalInput(value))}" ${field.required ? 'required' : ''}>`);
    case 'image':
      return wrap(`<div class="stack stack--sm">
        ${value ? `<img src="${esc(value)}" alt="" width="120" height="120" style="border-radius:var(--radius-md);border:1px solid var(--color-border);object-fit:cover">` : ''}
        <input class="input" id="${id}" name="${esc(field.key)}" type="file" accept="image/*" data-file>
        ${field.altKey ? `<input class="input" name="${esc(field.altKey)}" type="text" placeholder="Descriptive alt text (required for accessibility)" value="${esc(row?.[field.altKey] || '')}">` : ''}
      </div>`);
    case 'images':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="file" accept="image/*" multiple data-file>
        <div class="image-picker" style="margin-top:.5rem">${(row?.images || []).map((image) => `<span class="image-picker__item"><img src="${esc(image.url || image)}" alt="${esc(image.alt || '')}" loading="lazy"></span>`).join('')}</div>`);
    case 'json':
      return wrap(`<textarea class="textarea t-mono" id="${id}" name="${esc(field.key)}" rows="${field.rows || 5}" spellcheck="false" placeholder="${esc(field.placeholder || '{ }')}">${esc(value === '' || value == null ? '' : JSON.stringify(value, null, 2))}</textarea>`);
    case 'keyvalue': {
      // {label: value} objects edited as one "Label: value" pair per line.
      const text = value && typeof value === 'object' ? Object.entries(value).map(([k, v]) => `${k}: ${v}`).join('\n') : '';
      return wrap(`<textarea class="textarea" id="${id}" name="${esc(field.key)}" rows="${field.rows || 5}" placeholder="${esc(field.placeholder || 'Label: value')}">${esc(text)}</textarea>`);
    }
    case 'checklist': {
      const selected = new Set((Array.isArray(value) ? value : []).map(String));
      const options = (field.options || []).map((option) => (typeof option === 'object' ? option : { value: option, label: option }));
      return `<fieldset class="field form-grid__full" data-checklist="${esc(field.key)}" ${field.source ? `data-checklist-source="${esc(field.source)}"` : ''} data-selected="${esc(JSON.stringify([...selected]))}">
        <legend class="field__label">${esc(field.label)} ${required}</legend>
        <div class="checklist">${options.map((option) => `<label class="checkbox"><input type="checkbox" value="${esc(option.value)}" ${selected.has(String(option.value)) ? 'checked' : ''}><span>${esc(option.label)}</span></label>`).join('')}</div>
        ${field.hint ? `<p class="field__hint">${esc(field.hint)}</p>` : ''}
        <p class="field__error" data-error-for="${esc(field.key)}"></p>
      </fieldset>`;
    }
    case 'mediakey':
      return wrap(mediaKeyControl({ id, name: field.key, value: value || '', previewUrl: row?.[field.previewKey] || '', kind: field.kind }));
    case 'idlist':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="text" inputmode="numeric" value="${esc(Array.isArray(value) ? value.join(', ') : '')}" placeholder="e.g. 12, 15, 31">`);
    case 'tags':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="text" value="${esc(Array.isArray(value) ? value.join(', ') : value)}" placeholder="Comma-separated">`);
    case 'readonly':
      return wrap(`<input class="input" id="${id}" value="${esc(value)}" disabled readonly>`);
    case 'password':
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="password" ${field.required ? 'required' : ''} autocomplete="new-password">`);
    default:
      return wrap(`<input class="input" id="${id}" name="${esc(field.key)}" type="${field.type === 'email' ? 'email' : field.type === 'tel' ? 'tel' : field.type === 'url' ? 'url' : 'text'}" value="${esc(value)}" ${field.required ? 'required' : ''} ${field.maxLength ? `maxlength="${field.maxLength}"` : ''} ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}>`);
  }
}

function bindFieldBehaviours(form, fields) {
  bindMediaKeyControls(form);
  fields.forEach(async (field) => {
    if (!field.source) return;
    if (field.type === 'checklist') {
      const box = form.querySelector(`[data-checklist="${CSS.escape(field.key)}"]`);
      const holder = box?.querySelector('.checklist');
      if (!holder) return;
      try {
        const list = normalizeList(await api.get(field.source, { params: field.sourceParams || { page_size: 100 } })).results;
        const selected = new Set(JSON.parse(box.dataset.selected || '[]').map(String));
        const valueKey = field.valueKey || 'id';
        const labelKey = field.labelKey || 'name';
        const groups = new Map();
        list.forEach((item) => {
          const group = field.groupKey ? (item[field.groupKey] || 'Other') : '';
          if (!groups.has(group)) groups.set(group, []);
          groups.get(group).push(item);
        });
        holder.innerHTML = [...groups.entries()].map(([group, items]) => `
          ${group ? `<p class="checklist__group">${esc(titleCase(group))}</p>` : ''}
          ${items.map((item) => `<label class="checkbox"><input type="checkbox" value="${esc(item[valueKey])}" ${selected.has(String(item[valueKey])) ? 'checked' : ''}><span>${esc(item[labelKey])}</span></label>`).join('')}`).join('');
      } catch {
        holder.innerHTML = '<p class="field__hint">Options could not be loaded.</p>';
      }
      return;
    }
    const select = form.querySelector(`[name="${CSS.escape(field.key)}"]`);
    if (!select || select.tagName !== 'SELECT') return;
    try {
      const data = await api.get(field.source, { params: field.sourceParams || { page_size: 200 } });
      const list = normalizeList(data).results;
      const valueKey = field.valueKey || 'id';
      const labelKey = field.labelKey || 'name';
      const existing = select.dataset.selected || select.value;
      select.insertAdjacentHTML('beforeend', list.map((item) => `<option value="${esc(item[valueKey])}" ${String(existing) === String(item[valueKey]) ? 'selected' : ''}>${esc(item[labelKey])}</option>`).join(''));
    } catch {
      select.insertAdjacentHTML('beforeend', '<option value="" disabled>Options unavailable</option>');
    }
  });
}

function collectValues(form, fields) {
  const values = formData(form);
  fields.forEach((field) => {
    if (field.type === 'checkbox' || field.type === 'switch') values[field.key] = !!form.elements[field.key]?.checked;
    if (field.type === 'tags') values[field.key] = String(values[field.key] || '').split(',').map((s) => s.trim()).filter(Boolean);
    if (field.type === 'number') {
      const empty = values[field.key] === '' || values[field.key] == null;
      // Columns that cannot be NULL declare `emptyValue` (their server default).
      values[field.key] = empty ? (field.emptyValue ?? (typeof field.default === 'number' ? field.default : null)) : Number(values[field.key]);
    }
    // Money stays a decimal string so no precision is lost in transit.
    if (field.type === 'money') values[field.key] = values[field.key] === '' || values[field.key] == null ? null : String(values[field.key]).trim();
    if (field.type === 'datetime') values[field.key] = values[field.key] ? new Date(values[field.key]).toISOString() : null;
    if (field.type === 'date' && !values[field.key]) values[field.key] = null;
    if (field.type === 'select' && field.nullable && values[field.key] === '') values[field.key] = null;
    if (field.type === 'idlist') {
      values[field.key] = String(values[field.key] || '').split(/[\s,]+/).filter(Boolean).map((part) => (/^\d+$/.test(part) ? Number(part) : NaN));
    }
    if (field.type === 'checklist') {
      values[field.key] = [...form.querySelectorAll(`[data-checklist="${CSS.escape(field.key)}"] input:checked`)]
        .map((input) => (field.numeric ? Number(input.value) : input.value));
    }
    if (field.type === 'keyvalue') {
      values[field.key] = Object.fromEntries(String(values[field.key] || '').split('\n')
        .map((line) => line.split(/:(.*)/s).slice(0, 2).map((part) => (part || '').trim()))
        .filter(([key, val]) => key && val));
    }
    if (field.type === 'json') {
      const raw = String(values[field.key] || '').trim();
      if (!raw) values[field.key] = field.emptyValue ?? null;
      else {
        try { values[field.key] = JSON.parse(raw); }
        catch { values[field.key] = INVALID_JSON; }
      }
    }
  });
  return values;
}

function validateFields(fields, values) {
  const errors = {};
  fields.forEach((field) => {
    if (values[field.key] === INVALID_JSON) { errors[field.key] = `${field.label} must be valid JSON.`; return; }
    if (field.type === 'idlist' && values[field.key].some(Number.isNaN)) { errors[field.key] = `${field.label}: use whole numbers separated by commas.`; return; }
    if (field.validate) {
      const message = field.validate(values[field.key], values);
      if (message) { errors[field.key] = message; return; }
    }
    if (!field.required) return;
    const value = values[field.key];
    if (value === '' || value === null || value === undefined || (Array.isArray(value) && !value.length)) {
      errors[field.key] = `${field.label} is required.`;
    }
  });
  return errors;
}

function preparePayload(fields, values, form) {
  const body = {};
  const files = [];
  fields.forEach((field) => {
    if (field.readonly || field.type === 'readonly') return;
    if (field.type === 'image' || field.type === 'images') {
      const input = form.querySelector(`[name="${CSS.escape(field.key)}"]`);
      [...(input?.files || [])].forEach((file) => files.push({ name: field.type === 'images' ? (field.uploadKey || 'images') : field.key, file }));
      if (field.altKey) body[field.altKey] = values[field.altKey] || '';
      return;
    }
    if (!(field.key in values)) return;
    body[field.key] = values[field.key];
  });
  return { body, files };
}

export default AdminTable;
