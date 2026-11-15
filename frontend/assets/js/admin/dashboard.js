/**
 * dashboard.js — business overview.
 *
 * One request: GET /api/dashboard/overview/?range=custom&date_from=&date_to=
 * (permission dashboard.view). Revenue counts verified successful payments
 * only; nothing is derived or estimated in the browser.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api from '../api.js';
import { skeletons, resolveRegion, renderRegionError, emptyState } from '../ui.js';
import { icon } from '../icons.js';
import { esc, $, formatMoney, formatNumber, formatDate } from '../utils.js';
import { lineChart } from './charts.js';
import { statusBadge } from '../orders.js';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

export function rangeParams(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (Number(days) - 1));
  return { range: 'custom', date_from: iso(start), date_to: iso(end) };
}

if (await initAdmin() && guardPermission('dashboard.view')) {
  const regions = {
    stats: $('[data-dashboard-stats]'),
    chart: $('[data-dashboard-chart]'),
    inventory: $('[data-dashboard-inventory]'),
    orders: $('[data-dashboard-orders]'),
    best: $('[data-dashboard-bestsellers]'),
  };

  const stat = ({ label, value, iconName, hint, href }) => `<div class="stat-card">
      <div class="stat-card__head"><span class="stat-card__label">${esc(label)}</span><span class="stat-card__icon">${icon(iconName, { size: 'sm' })}</span></div>
      <span class="stat-card__value">${esc(value)}</span>
      ${hint ? `<span class="stat-card__meta">${esc(hint)}</span>` : ''}
      ${href ? `<a class="stat-card__link t-sm" href="${esc(href)}">View</a>` : ''}
    </div>`;

  function renderStats(data) {
    const f = data.financials || {};
    const t = data.totals || {};
    const inv = data.inventory || {};
    const money = (value) => formatMoney(value ?? 0, f.currency || 'NGN');
    const n = (value) => formatNumber(value ?? 0);
    resolveRegion(regions.stats, `<div class="admin-stats">${[
      { label: 'Collected revenue', value: money(f.collected_revenue), iconName: 'wallet', hint: 'Verified successful payments in this period' },
      { label: 'Net sales', value: money(f.net_sales), iconName: 'chart', hint: `After ${money(f.refunds)} refunded` },
      { label: 'Orders created', value: n(f.orders_created), iconName: 'receipt', hint: `${n(f.orders_paid)} paid · ${n(f.orders_cancelled)} cancelled or expired` },
      { label: 'Average order value', value: money(f.average_order_value), iconName: 'credit-card', hint: 'Paid orders only' },
      { label: 'Awaiting payment', value: n(t.pending_orders), iconName: 'clock', hint: 'Not counted as revenue', href: '/admin/orders.html?status=pending_payment' },
      { label: 'Orders to fulfil', value: n(t.orders_to_fulfil), iconName: 'truck', hint: 'Paid, processing or packed', href: '/admin/orders.html' },
      { label: 'Open refund requests', value: n(t.open_refund_requests), iconName: 'undo', href: '/admin/refunds.html' },
      { label: 'Customers', value: n(t.total_customers), iconName: 'users', href: '/admin/customers.html' },
    ].map(stat).join('')}</div>
    <div class="admin-stats admin-stats--3" style="margin-top:var(--space-4)">${[
      { label: 'Active products', value: n(inv.total_active_products), iconName: 'package', hint: `${n(inv.total_units_available)} units available` },
      { label: 'Low stock', value: n(inv.low_stock_count), iconName: 'alert-triangle', hint: `${n(inv.out_of_stock_count)} out of stock` },
      { label: 'Active categories', value: n(t.active_categories), iconName: 'folder', hint: `${n(t.total_categories)} in total` },
    ].map(stat).join('')}</div>`);
  }

  function renderChart(data, days) {
    const trend = data.sales_trend || [];
    const caption = $('[data-trend-caption]');
    if (caption) caption.textContent = `Last ${days} days · verified payments only`;
    if (!trend.length) {
      resolveRegion(regions.chart, emptyState({ title: 'No verified payments in this period', text: 'The trend appears once customers complete payment.', iconName: 'chart', inline: true }));
      return;
    }
    const series = trend.map((point) => ({
      label: formatDate(point.date, { day: 'numeric', month: 'short' }),
      value: Number(point.revenue || 0),
    }));
    resolveRegion(regions.chart, lineChart(series, { currency: data.financials?.currency || 'NGN', ariaLabel: `Collected revenue per day over the last ${days} days` }));
  }

  function renderInventory(data) {
    const inv = data.inventory || {};
    const rows = [
      ...(inv.out_of_stock_items || []).map((item) => ({ ...item, available: 0 })),
      ...(inv.low_stock_items || []),
    ].slice(0, 8);
    if (!rows.length) {
      resolveRegion(regions.inventory, emptyState({ title: 'Stock levels look healthy', text: 'No products are below their low-stock threshold.', iconName: 'check-circle', inline: true }));
      return;
    }
    resolveRegion(regions.inventory, `<div class="data-list">${rows.map((row) => `
      <div class="data-list__item">
        <span class="data-list__body">
          <span class="t-sm t-medium t-clamp-1">${esc(row.name || '')}</span>
          <span class="t-meta">${esc(row.variation || row.sku || '')}</span>
        </span>
        <span class="badge badge--${Number(row.available) <= 0 ? 'danger' : 'warning'}">${Number(row.available) <= 0 ? 'Out of stock' : `${esc(row.available)} left`}</span>
      </div>`).join('')}</div>`);
  }

  function renderOrders(data) {
    const rows = (data.recent_orders || []).slice(0, 8);
    if (!rows.length) {
      resolveRegion(regions.orders, emptyState({ title: 'No orders yet', text: 'Orders will appear here as customers check out.', iconName: 'receipt', inline: true }));
      return;
    }
    resolveRegion(regions.orders, `<div class="table-wrap"><table class="table table--responsive">
      <caption class="sr-only">Recent orders</caption>
      <thead><tr><th scope="col">Reference</th><th scope="col">Placed</th><th scope="col">Status</th><th scope="col" class="num">Total</th></tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td data-label="Reference"><a class="table__primary" href="/admin/orders.html?q=${encodeURIComponent(row.reference)}">${esc(row.reference)}</a></td>
        <td data-label="Placed">${esc(formatDate(row.placed_at))}</td>
        <td data-label="Status">${statusBadge(row.status)}</td>
        <td data-label="Total" class="num">${esc(formatMoney(row.total ?? row.totals?.total ?? row.total_amount ?? 0, row.currency || 'NGN'))}</td>
      </tr>`).join('')}</tbody></table></div>`);
  }

  function renderBest(data) {
    const rows = (data.best_sellers || []).slice(0, 8);
    if (!rows.length) {
      resolveRegion(regions.best, emptyState({ title: 'No sales recorded yet', text: 'Best sellers are ranked by paid orders only.', iconName: 'chart', inline: true }));
      return;
    }
    resolveRegion(regions.best, `<div class="table-wrap"><table class="table table--responsive">
      <caption class="sr-only">Best-selling products</caption>
      <thead><tr><th scope="col">Product</th><th scope="col" class="num">Units</th><th scope="col" class="num">Revenue</th></tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td data-label="Product"><span class="cell-stack"><span class="table__primary t-clamp-1">${esc(row.name || '')}</span><span class="cell-muted">${esc(row.sku || '')}</span></span></td>
        <td data-label="Units" class="num">${esc(formatNumber(row.units ?? 0))}</td>
        <td data-label="Revenue" class="num">${esc(formatMoney(row.revenue ?? 0, 'NGN'))}</td>
      </tr>`).join('')}</tbody></table></div>`);
  }

  let request = 0;
  async function load() {
    const days = Number($('[data-dashboard-range]')?.value || 30);
    const current = ++request;
    Object.values(regions).forEach((region) => region?.setAttribute('aria-busy', 'true'));
    regions.stats.innerHTML = skeletons.statGrid(8);
    try {
      const data = await api.get('/dashboard/overview/', { params: rangeParams(days), cache: false, dedupe: false });
      if (current !== request) return;
      renderStats(data);
      renderChart(data, days);
      renderInventory(data);
      renderOrders(data);
      renderBest(data);
    } catch (error) {
      if (current !== request) return;
      renderRegionError(regions.stats, error, load, { title: 'Business figures could not be loaded' });
      [regions.chart, regions.inventory, regions.orders, regions.best].forEach((region) => {
        resolveRegion(region, '<p class="t-sm t-muted">Unavailable until the overview loads.</p>');
      });
    }
  }

  $('[data-dashboard-range]')?.addEventListener('change', load);
  $('[data-dashboard-refresh]')?.addEventListener('click', load);
  load();
}
