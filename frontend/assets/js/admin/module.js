/**
 * module.js — entry point for every configuration-driven admin module.
 * The page declares its module with [data-admin-module]; the config supplies
 * the endpoint, columns, filters, form and permissions.
 */
import { initAdmin, guardPermission } from './admin-core.js';
import { AdminTable } from './admin-table.js';
import { MODULES } from './admin-modules.js';
import { emptyState } from '../ui.js';
import { hydrateIcons } from '../icons.js';
import { $ } from '../utils.js';

const root = $('[data-admin-module]');
const id = root?.dataset.adminModule;
const config = MODULES[id];

if (!root || !config) {
  if (root) {
    root.innerHTML = emptyState({
      title: 'Module configuration missing',
      text: 'This administration module has no configuration registered. See docs/API_CONTRACT.md.',
      iconName: 'alert-triangle',
    });
    hydrateIcons(root);
  }
} else {
  const permitted = await initAdmin();
  if (permitted) {
    const viewPermission = config.viewPermission || `${id.replace(/-/g, '_')}.view`;
    // Presentation-only gate. (The previous `|| guardPermission(null)` always
    // returned true and silently defeated it; the backend still enforces.)
    if (guardPermission(viewPermission)) {
      const table = new AdminTable(root, config);
      await table.mount();
      window.addEventListener('starmond:auth-changed', () => table.load());
    }
  }
}
