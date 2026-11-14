/**
 * charts.js — dependency-free inline SVG charts.
 * Values are supplied by backend reports; nothing is interpolated or invented.
 * Every chart has a text alternative for assistive technology.
 */
import { esc, formatMoney, formatNumber } from '../utils.js';

const W = 640;
const H = 220;
const PAD = { top: 16, right: 12, bottom: 28, left: 56 };

function niceMax(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

/**
 * Line/area chart.
 * @param {Array<{label:string, value:number}>} series
 */
export function lineChart(series, { currency = 'NGN', ariaLabel = 'Sales trend' } = {}) {
  if (!series?.length) return '<p class="t-sm t-muted">No data for this period.</p>';
  const max = niceMax(Math.max(...series.map((d) => Number(d.value) || 0)));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const stepX = series.length > 1 ? innerW / (series.length - 1) : 0;
  const points = series.map((d, i) => {
    const x = PAD.left + i * stepX;
    const y = PAD.top + innerH - ((Number(d.value) || 0) / max) * innerH;
    return [x, y];
  });
  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${path} L${points[points.length - 1][0].toFixed(1)},${PAD.top + innerH} L${PAD.left},${PAD.top + innerH} Z`;
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
    const y = PAD.top + innerH - fraction * innerH;
    return `<line class="chart__grid-line" x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}"/>
      <text class="chart__axis-label" x="${PAD.left - 8}" y="${y + 3}" text-anchor="end">${esc(formatMoney(max * fraction, currency, { decimals: 0 }))}</text>`;
  }).join('');
  const labelEvery = Math.max(1, Math.ceil(series.length / 7));
  const labels = series.map((d, i) => (i % labelEvery === 0 || i === series.length - 1
    ? `<text class="chart__axis-label" x="${points[i][0].toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(d.label)}</text>` : '')).join('');

  return `<div class="chart">
    <svg class="chart__svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(ariaLabel)}">
      ${gridLines}
      <path class="chart__area" d="${area}"/>
      <path class="chart__line" d="${path}"/>
      ${points.map(([x, y]) => `<circle class="chart__dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5"/>`).join('')}
      ${labels}
    </svg>
    <table class="sr-only"><caption>${esc(ariaLabel)}</caption><thead><tr><th>Period</th><th>Value</th></tr></thead>
      <tbody>${series.map((d) => `<tr><td>${esc(d.label)}</td><td>${esc(formatMoney(d.value, currency))}</td></tr>`).join('')}</tbody>
    </table>
  </div>`;
}

/** Horizontal bar list, used for category and product breakdowns. */
export function barList(items, { currency = 'NGN', valueKey = 'value', labelKey = 'label', money = true } = {}) {
  if (!items?.length) return '<p class="t-sm t-muted">No data for this period.</p>';
  const max = Math.max(...items.map((i) => Number(i[valueKey]) || 0), 1);
  return `<div class="stack stack--sm">${items.map((item) => {
    const value = Number(item[valueKey]) || 0;
    return `<div class="stack stack--xs">
      <div class="cluster cluster--between">
        <span class="t-sm t-clamp-1">${esc(item[labelKey])}</span>
        <span class="t-sm t-semibold t-tabular">${esc(money ? formatMoney(value, currency) : formatNumber(value))}</span>
      </div>
      <div class="rating-bar__track"><div class="rating-bar__fill" style="width:${(value / max) * 100}%;background:var(--color-primary)"></div></div>
    </div>`;
  }).join('')}</div>`;
}

export default { lineChart, barList };
