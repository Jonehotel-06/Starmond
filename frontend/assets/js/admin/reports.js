/**
 * reports.js — reporting screen (permission reports.view).
 *
 * Backend routes (all accept range=custom&date_from=&date_to=):
 *   GET /api/reports/sales/       → { summary, trend[] }
 *   GET /api/reports/categories/  → [{ category, revenue, units }]
 *   GET /api/reports/products/    → [{ sku, name, units, revenue }]
 *   GET /api/reports/orders/      → [{ reference, date, status, total, … }]
 *   GET /api/reports/payments/    → payment ledger   (finance.view)
 *   GET /api/reports/refunds/     → refund ledger    (finance.view)
 * Adding ?format=csv|xlsx|pdf to any of them returns the file.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api, { normalizeList } from '../api.js';
import { skeletons, resolveRegion, renderRegionError, emptyState, toast, downloadBlob } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, formatNumber, formatDate, formatDateTime, titleCase } from '../utils.js';
import { lineChart } from './charts.js';
import { statusBadge } from '../orders.js';

if (await initAdmin() && guardPermission('reports.view')) {
  const form = $('[data-report-filters]');
  const errorNode = $('[data-report-error]');
  const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

  // Default period: the last 30 days.
  const today = new Date();
  const monthAgo = new Date();
  monthAgo.setDate(today.getDate() - 29);
  form.elements.date_from.value = iso(monthAgo);
  form.elements.date_to.value = iso(today);
  form.elements.date_from.max = iso(today);
  form.elements.date_to.max = iso(today);

  function currentParams() {
    const from = form.elements.date_from.value;
    const to = form.elements.date_to.value;
    if (!from || !to) { errorNode.textContent = 'Choose both a start and an end date.'; return null; }
    if (from > to) { errorNode.textContent = 'The start date must be on or before the end date.'; return null; }
    errorNode.textContent = '';
    return { range: 'custom', date_from: from, date_to: to };
  }

  const get = (path, params) => api.get(path, { params, cache: false, dedupe: false });

  async function loadSales(params) {
    const summaryRegion = $('[data-report-summary]');
    const chartRegion = $('[data-report-chart]');
    summaryRegion.setAttribute('aria-busy', 'true');
    summaryRegion.innerHTML = skeletons.statGrid(8);
    chartRegion.innerHTML = skeletons.chart();
    try {
      const data = await get('/reports/sales/', params);
      const s = data.summary || {};
      const currency = s.currency || 'NGN';
      const cards = [
        ['Collected revenue', s.collected_revenue, 'wallet', false, 'Verified successful payments'],
        ['Net sales', s.net_sales, 'chart', false, 'Collected revenue less refunds'],
        ['Gross product sales', s.gross_sales, 'package', false, 'Item subtotals of paid orders'],
        ['Refunds', s.refunds, 'undo'],
        ['Discounts given', s.discounts_given, 'percent'],
        ['Delivery fees collected', s.shipping_revenue, 'truck'],
        ['Average order value', s.average_order_value, 'receipt'],
        ['Orders paid', s.orders_paid, 'check-circle', true, `${formatNumber(s.orders_created ?? 0)} created · ${formatNumber(s.orders_awaiting_payment ?? 0)} awaiting payment`],
      ];
      resolveRegion(summaryRegion, `<div class="admin-stats">${cards.map(([label, value, iconName, isCount, hint]) => `
        <div class="stat-card">
          <div class="stat-card__head"><span class="stat-card__label">${esc(label)}</span><span class="stat-card__icon">${icon(iconName, { size: 'sm' })}</span></div>
          <span class="stat-card__value">${value == null ? '—' : esc(isCount ? formatNumber(value) : formatMoney(value, currency))}</span>
          ${hint ? `<span class="stat-card__meta">${esc(hint)}</span>` : ''}
        </div>`).join('')}</div>`);
      const trend = data.trend || [];
      if (!trend.length) {
        resolveRegion(chartRegion, emptyState({ title: 'No verified payments in this period', text: 'Choose a different period or wait for paid orders.', iconName: 'chart', inline: true }));
      } else {
        resolveRegion(chartRegion, lineChart(trend.map((point) => ({
          label: formatDate(point.date, { day: 'numeric', month: 'short' }), value: Number(point.revenue || 0),
        })), { currency, ariaLabel: 'Collected revenue per day for the selected period' }));
      }
    } catch (error) {
      renderRegionError(summaryRegion, error, () => loadSales(params), { title: 'Sales summary unavailable' });
      resolveRegion(chartRegion, '<p class="t-sm t-muted">Unavailable until the summary loads.</p>');
    }
  }

  /** Generic report table. `rowsOf` may reshape the API rows (e.g. group them). */
  async function loadTable(selector, path, params, { title, columns, rowsOf = (rows) => rows, limit = 0, countNode = null, forbiddenText = '' }) {
    const region = $(selector);
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.table(5, columns.length);
    try {
      const all = rowsOf(normalizeList(await get(path, params)).results);
      const rows = limit ? all.slice(0, limit) : all;
      if (countNode) countNode.textContent = all.length ? `${formatNumber(rows.length)} of ${formatNumber(all.length)} shown — download for the full list` : '';
      if (!rows.length) {
        resolveRegion(region, emptyState({ title: `No ${title.toLowerCase()} in this period`, text: 'Nothing was recorded for the selected dates.', iconName: 'chart', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="table-wrap"><table class="table table--responsive">
        <caption class="sr-only">${esc(title)}</caption>
        <thead><tr>${columns.map((c) => `<th scope="col" class="${c.numeric ? 'num' : ''}">${esc(c.label)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${columns.map((c) => {
          const value = row[c.key];
          const html = c.render ? c.render(row)
            : c.money ? esc(formatMoney(value ?? 0, row.currency || 'NGN'))
            : c.number ? esc(formatNumber(value ?? 0))
            : esc(value ?? '—');
          return `<td data-label="${esc(c.label)}" class="${c.numeric ? 'num' : ''}">${html}</td>`;
        }).join('')}</tr>`).join('')}</tbody></table></div>`);
    } catch (error) {
      if (countNode) countNode.textContent = '';
      if (error.isForbidden && forbiddenText) {
        resolveRegion(region, emptyState({ title: 'Not available for your role', text: forbiddenText, iconName: 'lock', inline: true }));
        return;
      }
      renderRegionError(region, error, () => loadTable(selector, path, params, { title, columns, rowsOf, limit, countNode, forbiddenText }), { title: `${title} unavailable` });
    }
  }

  /** Orders report rows → one line per status with count and value. */
  function groupByStatus(rows) {
    const groups = new Map();
    rows.forEach((row) => {
      const entry = groups.get(row.status) || { status: row.status, count: 0, total: 0 };
      entry.count += 1;
      entry.total += Number(row.total || 0);
      groups.set(row.status, entry);
    });
    return [...groups.values()].sort((a, b) => b.count - a.count);
  }

  function loadAll() {
    const params = currentParams();
    if (!params) return;
    loadSales(params);
    loadTable('[data-report-lifecycle]', '/reports/orders/', params, {
      title: 'Orders', rowsOf: groupByStatus,
      columns: [
        { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
        { key: 'count', label: 'Orders', numeric: true, number: true },
        { key: 'total', label: 'Order value', numeric: true, money: true },
      ],
    });
    loadTable('[data-report-categories]', '/reports/categories/', params, {
      title: 'Category sales',
      columns: [{ key: 'category', label: 'Category' }, { key: 'units', label: 'Units', numeric: true, number: true }, { key: 'revenue', label: 'Revenue', numeric: true, money: true }],
    });
    loadTable('[data-report-products]', '/reports/products/', params, {
      title: 'Product sales', limit: 20,
      columns: [
        { key: 'name', label: 'Product', render: (r) => `<span class="cell-stack"><span class="table__primary t-clamp-1">${esc(r.name || '')}</span><span class="cell-muted">${esc(r.sku || '')}</span></span>` },
        { key: 'units', label: 'Units', numeric: true, number: true },
        { key: 'revenue', label: 'Revenue', numeric: true, money: true },
      ],
    });
    const financeOnly = 'The payment and refund ledgers need the finance.view permission.';
    loadTable('[data-report-payments]', '/reports/payments/', params, {
      title: 'Payments', limit: 25, countNode: $('[data-report-payments-count]'), forbiddenText: financeOnly,
      columns: [
        { key: 'order_reference', label: 'Order', render: (r) => `<span class="cell-stack"><span class="table__primary">${esc(r.order_reference || '')}</span><span class="cell-muted">${esc(r.reference || '')}</span></span>` },
        { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
        { key: 'channel', label: 'Channel' },
        { key: 'verified_at', label: 'Verified', render: (r) => esc(r.verified_at ? formatDateTime(r.verified_at) : '—') },
        { key: 'amount', label: 'Amount', numeric: true, money: true },
      ],
    });
    loadTable('[data-report-refunds]', '/reports/refunds/', params, {
      title: 'Refunds', limit: 25, countNode: $('[data-report-refunds-count]'), forbiddenText: financeOnly,
      columns: [
        { key: 'order_reference', label: 'Order', render: (r) => `<span class="cell-stack"><span class="table__primary">${esc(r.order_reference || '')}</span><span class="cell-muted">${esc(r.reference || '')}</span></span>` },
        { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
        { key: 'processed_at', label: 'Processed', render: (r) => esc(r.processed_at ? formatDateTime(r.processed_at) : '—') },
        { key: 'requested_amount', label: 'Requested', numeric: true, money: true },
        { key: 'approved_amount', label: 'Approved', numeric: true, render: (r) => esc(r.approved_amount ? formatMoney(r.approved_amount) : '—') },
      ],
    });
  }

  form.addEventListener('submit', (event) => { event.preventDefault(); loadAll(); });

  document.querySelectorAll('[data-export]').forEach((button) => {
    button.addEventListener('click', async () => {
      const params = currentParams();
      if (!params) return;
      const format = button.dataset.export;
      const report = $('[data-export-report]').value;
      const original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="btn__pending">Preparing</span>';
      try {
        const { blob, filename } = await api.download(`/reports/${report}/`, { params: { ...params, format } });
        downloadBlob(blob, filename || `starmond-${report}-${params.date_from}-${params.date_to}.${format}`);
        toast(`${titleCase(report)} report downloaded.`, { type: 'success' });
      } catch (error) {
        toast(error?.userMessage || 'The report could not be downloaded.', { type: 'danger' });
      } finally {
        button.disabled = false;
        button.innerHTML = original;
        hydrateIcons(button);
      }
    });
  });

  loadAll();
}
