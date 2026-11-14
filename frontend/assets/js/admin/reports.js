/**
 * reports.js — financial reporting interface.
 * All figures and exports are produced by the backend reporting service.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api, { normalizeList } from '../api.js';
import { skeletons, resolveRegion, renderRegionError, emptyState, toast, formData, downloadBlob } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, formatNumber, formatDate } from '../utils.js';
import { lineChart, barList } from './charts.js';

// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await initAdmin()) {
  guardPermission('reports.view');

  const form = $('[data-report-filters]');

  function currentFilters() {
    const values = form ? formData(form) : {};
    const params = {};
    if (values.date_from) params.date_from = values.date_from;
    if (values.date_to) params.date_to = values.date_to;
    params.group_by = values.group_by || 'month';
    if (values.category) params.category = values.category;
    return params;
  }

  async function loadCategories() {
    const select = $('#rp-category');
    if (!select) return;
    try {
      const data = await api.get('/categories/', { params: { page_size: 200 } });
      normalizeList(data).results.forEach((category) => {
        select.insertAdjacentHTML('beforeend', `<option value="${esc(category.id)}">${esc(category.name)}</option>`);
      });
    } catch { /* leave "All categories" */ }
  }

  async function loadSummary(params) {
    const region = $('[data-report-summary]');
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.statGrid(8);
    try {
      const data = await api.privateGet('/admin/reports/financial/', { params });
      const currency = data.currency || 'NGN';
      const cards = [
        ['Gross sales', data.gross_sales, 'chart'],
        ['Net sales', data.net_sales, 'trending-up'],
        ['Refunds', data.refunds_total, 'undo'],
        ['Discounts given', data.discounts_total, 'percent'],
        ['Shipping revenue', data.shipping_revenue, 'truck'],
        ['Product sales', data.product_sales, 'package'],
        ['Average order value', data.average_order_value, 'receipt'],
        ['Orders paid', data.orders_paid, 'check-circle', true],
      ];
      resolveRegion(region, `<div class="admin-stats">${cards.map(([label, value, iconName, isCount]) => `
        <div class="stat-card">
          <div class="stat-card__head"><span class="stat-card__label">${esc(label)}</span><span class="stat-card__icon">${icon(iconName, { size: 'sm' })}</span></div>
          <span class="stat-card__value">${value == null ? '—' : esc(isCount ? formatNumber(value) : formatMoney(value, currency))}</span>
        </div>`).join('')}</div>`);
    } catch (error) {
      renderRegionError(region, error, () => loadSummary(params), { title: 'Financial summary unavailable' });
    }
  }

  async function loadChart(params) {
    const region = $('[data-report-chart]');
    region.innerHTML = skeletons.chart();
    try {
      const data = await api.privateGet('/admin/reports/sales-trend/', { params });
      const series = (data.series || data.results || []).map((point) => ({
        label: point.label || formatDate(point.date, { day: 'numeric', month: 'short' }),
        value: Number(point.revenue ?? point.value ?? 0),
      }));
      resolveRegion(region, lineChart(series, { currency: data.currency || 'NGN', ariaLabel: 'Sales over the selected period' }));
    } catch (error) {
      renderRegionError(region, error, () => loadChart(params), { title: 'Sales chart unavailable' });
    }
  }

  async function loadTable(regionSelector, endpoint, params, { columns, emptyTitle, money = true }) {
    const region = $(regionSelector);
    region.innerHTML = skeletons.table(5, columns.length);
    try {
      const data = await api.privateGet(endpoint, { params });
      const rows = normalizeList(data).results;
      if (!rows.length) {
        resolveRegion(region, emptyState({ title: emptyTitle, text: 'No records for the selected period.', iconName: 'chart', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="table-wrap"><table class="table table--responsive">
        <caption class="sr-only">${esc(emptyTitle)}</caption>
        <thead><tr>${columns.map((column) => `<th scope="col" class="${column.numeric ? 'num' : ''}">${esc(column.label)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${columns.map((column) => {
          const value = row[column.key];
          const rendered = column.money ? formatMoney(value ?? 0, row.currency || 'NGN')
            : column.number ? formatNumber(value ?? 0) : esc(value ?? '—');
          return `<td data-label="${esc(column.label)}" class="${column.numeric ? 'num' : ''}">${column.raw ? value : rendered}</td>`;
        }).join('')}</tr>`).join('')}</tbody>
      </table></div>`);
    } catch (error) {
      renderRegionError(region, error, () => loadTable(regionSelector, endpoint, params, { columns, emptyTitle, money }), { title: emptyTitle });
    }
  }

  function loadAll() {
    const params = currentFilters();
    loadSummary(params);
    loadChart(params);
    loadTable('[data-report-payments]', '/admin/reports/payment-outcomes/', params, {
      emptyTitle: 'Payment outcomes',
      columns: [{ key: 'status', label: 'Status' }, { key: 'count', label: 'Transactions', numeric: true, number: true }, { key: 'amount', label: 'Amount', numeric: true, money: true }],
    });
    loadTable('[data-report-categories]', '/admin/reports/sales-by-category/', params, {
      emptyTitle: 'Sales by category',
      columns: [{ key: 'category', label: 'Category' }, { key: 'units', label: 'Units', numeric: true, number: true }, { key: 'revenue', label: 'Revenue', numeric: true, money: true }],
    });
    loadTable('[data-report-lifecycle]', '/admin/reports/order-lifecycle/', params, {
      emptyTitle: 'Order lifecycle',
      columns: [{ key: 'stage', label: 'Stage' }, { key: 'count', label: 'Orders', numeric: true, number: true }],
    });
    loadTable('[data-report-products]', '/admin/reports/best-sellers/', { ...params, limit: 20 }, {
      emptyTitle: 'Best-selling products',
      columns: [
        { key: 'name', label: 'Product' },
        { key: 'units_sold', label: 'Units', numeric: true, number: true },
        { key: 'revenue', label: 'Revenue', numeric: true, money: true },
        { key: 'orders_count', label: 'Orders', numeric: true, number: true },
      ],
    });
  }

  form?.addEventListener('submit', (event) => { event.preventDefault(); loadAll(); });

  document.querySelectorAll('[data-export]').forEach((button) => {
    button.addEventListener('click', async () => {
      const format = button.dataset.export;
      button.disabled = true;
      const original = button.innerHTML;
      button.innerHTML = '<span class="btn__pending">Preparing</span>';
      try {
        const { blob, filename } = await api.download(`/admin/reports/export/`, { params: { ...currentFilters(), format } });
        downloadBlob(blob, filename || `starmond-report.${format}`);
        toast('Report downloaded.', { type: 'success' });
      } catch (error) {
        toast(error?.userMessage || 'The report export is not available.', { type: 'danger' });
      } finally {
        button.disabled = false;
        button.innerHTML = original;
        hydrateIcons(button);
      }
    });
  });

  loadCategories();
  loadAll();
}
