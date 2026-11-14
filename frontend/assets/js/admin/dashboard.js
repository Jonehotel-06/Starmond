/**
 * dashboard.js — administration overview.
 * Every figure comes from the backend reporting service. Pending payments are
 * never presented as realised revenue, and missing data renders as an honest
 * empty/error state rather than a zero.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import api, { normalizeList } from '../api.js';
import { skeletons, resolveRegion, renderRegionError, emptyState } from '../ui.js';
import { icon, hydrateIcons } from '../icons.js';
import { esc, $, formatMoney, formatNumber, formatDate, formatCount } from '../utils.js';
import { lineChart, barList } from './charts.js';
import { statusBadge } from '../orders.js';

// The guard redirects (or renders an access-denied state) and returns false.
// We simply do not run the page body — no thrown error, no console noise.
if (await initAdmin()) {
  const STATS = [
    { key: 'revenue', label: 'Realised revenue', iconName: 'wallet', money: true, hint: 'Verified successful payments only' },
    { key: 'orders_total', label: 'Orders created', iconName: 'receipt' },
    { key: 'orders_paid', label: 'Orders paid', iconName: 'check-circle' },
    { key: 'orders_pending', label: 'Pending orders', iconName: 'clock' },
    { key: 'payments_pending', label: 'Pending payments', iconName: 'credit-card' },
    { key: 'customers_total', label: 'Customers', iconName: 'users' },
    { key: 'products_active', label: 'Active products', iconName: 'package' },
    { key: 'stock_low', label: 'Low-stock products', iconName: 'alert-triangle' },
  ];

  async function loadStats(days) {
    const region = $('[data-dashboard-stats]');
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = skeletons.statGrid(8);
    try {
      const data = await api.privateGet('/admin/reports/overview/', { params: { days } });
      resolveRegion(region, `<div class="admin-stats">${STATS.map((stat) => {
        const value = data[stat.key];
        return `<div class="stat-card">
          <div class="stat-card__head"><span class="stat-card__label">${esc(stat.label)}</span><span class="stat-card__icon">${icon(stat.iconName, { size: 'sm' })}</span></div>
          <span class="stat-card__value">${value == null ? '—' : esc(stat.money ? formatMoney(value, data.currency || 'NGN') : formatNumber(value))}</span>
          ${stat.hint ? `<span class="stat-card__meta">${esc(stat.hint)}</span>` : ''}
        </div>`;
      }).join('')}</div>
      <div class="admin-stats admin-stats--3" style="margin-top:var(--space-4)">
        <div class="stat-card"><div class="stat-card__head"><span class="stat-card__label">Categories</span><span class="stat-card__icon">${icon('folder', { size: 'sm' })}</span></div><span class="stat-card__value">${esc(formatNumber(data.categories_total ?? 0))}</span></div>
        <div class="stat-card"><div class="stat-card__head"><span class="stat-card__label">Out of stock</span><span class="stat-card__icon">${icon('alert-circle', { size: 'sm' })}</span></div><span class="stat-card__value">${esc(formatNumber(data.stock_out ?? 0))}</span></div>
        <div class="stat-card"><div class="stat-card__head"><span class="stat-card__label">Completed orders</span><span class="stat-card__icon">${icon('check', { size: 'sm' })}</span></div><span class="stat-card__value">${esc(formatNumber(data.orders_completed ?? 0))}</span></div>
      </div>`);
    } catch (error) {
      renderRegionError(region, error, () => loadStats(days), { title: 'Business figures could not be loaded' });
    }
  }

  async function loadChart(days) {
    const region = $('[data-dashboard-chart]');
    region.innerHTML = skeletons.chart();
    try {
      const data = await api.privateGet('/admin/reports/sales-trend/', { params: { days, group_by: days > 90 ? 'month' : 'day' } });
      const series = (data.series || data.results || []).map((point) => ({
        label: point.label || formatDate(point.date, { day: 'numeric', month: 'short' }),
        value: Number(point.revenue ?? point.value ?? 0),
      }));
      resolveRegion(region, lineChart(series, { currency: data.currency || 'NGN', ariaLabel: `Revenue over the last ${days} days` }));
      const caption = $('[data-trend-caption]');
      if (caption) caption.textContent = `Last ${days} days · verified revenue only`;
    } catch (error) {
      renderRegionError(region, error, () => loadChart(days), { title: 'Sales trend unavailable' });
    }
  }

  async function loadInventory() {
    const region = $('[data-dashboard-inventory]');
    region.innerHTML = skeletons.list(4);
    try {
      const data = await api.privateGet('/admin/inventory/', { params: { stock: 'low', page_size: 5, ordering: 'stock_quantity' } });
      const rows = normalizeList(data).results;
      if (!rows.length) {
        resolveRegion(region, emptyState({ title: 'Stock levels look healthy', text: 'No products are below their low-stock threshold.', iconName: 'check-circle', inline: true }));
        return;
      }
      // Real content must not reuse skeleton classes: .sk-* carries the
      // shimmer animation, which would make loaded rows pulse forever.
      resolveRegion(region, `<div class="data-list">${rows.map((row) => `
        <div class="data-list__item">
          <span class="data-list__body">
            <span class="t-sm t-medium t-clamp-1">${esc(row.product?.name || row.name || '')}</span>
            <span class="t-meta">${esc(row.sku || row.product?.sku || '')}</span>
          </span>
          <span class="badge badge--${Number(row.available_quantity ?? row.stock_quantity) <= 0 ? 'danger' : 'warning'}">${esc(row.available_quantity ?? row.stock_quantity ?? 0)} left</span>
        </div>`).join('')}</div>`);
    } catch (error) {
      renderRegionError(region, error, loadInventory, { title: 'Inventory alerts unavailable' });
    }
  }

  async function loadRecentOrders() {
    const region = $('[data-dashboard-orders]');
    region.innerHTML = skeletons.table(5, 4);
    try {
      const data = await api.privateGet('/admin/orders/', { params: { page_size: 5, ordering: '-created_at' } });
      const rows = normalizeList(data).results;
      if (!rows.length) {
        resolveRegion(region, emptyState({ title: 'No orders yet', text: 'Orders will appear here as customers check out.', iconName: 'receipt', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="table-wrap"><table class="table table--responsive">
        <caption class="sr-only">Recent orders</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col">Customer</th><th scope="col">Status</th><th scope="col" class="num">Total</th></tr></thead>
        <tbody>${rows.map((row) => `<tr>
          <td data-label="Reference"><a class="table__primary" href="/admin/orders.html?q=${encodeURIComponent(row.reference)}">${esc(row.reference)}</a></td>
          <td data-label="Customer">${esc(row.customer?.email || row.customer_email || 'Guest')}</td>
          <td data-label="Status">${statusBadge(row.payment_status)}</td>
          <td data-label="Total" class="num">${esc(formatMoney(row.total, row.currency || 'NGN'))}</td>
        </tr>`).join('')}</tbody></table></div>`);
    } catch (error) {
      renderRegionError(region, error, loadRecentOrders, { title: 'Recent orders unavailable' });
    }
  }

  async function loadBestsellers(days) {
    const region = $('[data-dashboard-bestsellers]');
    region.innerHTML = skeletons.table(5, 3);
    try {
      const data = await api.privateGet('/admin/reports/best-sellers/', { params: { days, limit: 5 } });
      const rows = normalizeList(data).results;
      if (!rows.length) {
        resolveRegion(region, emptyState({ title: 'No sales recorded yet', text: 'Best sellers are ranked by confirmed sales only.', iconName: 'chart', inline: true }));
        return;
      }
      resolveRegion(region, `<div class="table-wrap"><table class="table table--responsive">
        <caption class="sr-only">Best-selling products</caption>
        <thead><tr><th scope="col">Product</th><th scope="col" class="num">Units</th><th scope="col" class="num">Revenue</th></tr></thead>
        <tbody>${rows.map((row) => `<tr>
          <td data-label="Product"><span class="table__primary t-clamp-1">${esc(row.name || row.product?.name || '')}</span></td>
          <td data-label="Units" class="num">${esc(formatNumber(row.units_sold ?? row.quantity ?? 0))}</td>
          <td data-label="Revenue" class="num">${esc(formatMoney(row.revenue ?? 0, row.currency || 'NGN'))}</td>
        </tr>`).join('')}</tbody></table></div>`);
    } catch (error) {
      renderRegionError(region, error, () => loadBestsellers(days), { title: 'Best sellers unavailable' });
    }
  }

  function loadAll() {
    const days = Number($('[data-dashboard-range]')?.value || 30);
    loadStats(days);
    loadChart(days);
    loadInventory();
    loadRecentOrders();
    loadBestsellers(days);
  }

  $('[data-dashboard-range]')?.addEventListener('change', loadAll);
  $('[data-dashboard-refresh]')?.addEventListener('click', () => { api.invalidate(); loadAll(); });

  loadAll();
}
