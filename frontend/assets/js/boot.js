/**
 * boot.js — shared page bootstrap.
 *
 * Every page module imports `boot()`. It initialises the shell, global
 * commerce actions, PWA registration and error reporting in a fixed order,
 * and never blocks first paint on a secondary API request.
 */

import { initShell } from './navigation.js';
import { initLiveRegions, initSkeletonVisibility } from './ui.js';
import { initCommerceActions } from './shop-actions.js';
import { registerServiceWorker } from './pwa.js';

let booted = false;

export async function boot({ auth = true, shell = true } = {}) {
  if (booted) return;
  booted = true;

  initLiveRegions();
  initCommerceActions();
  initSkeletonVisibility();

  if (shell) {
    // Do not await: the page's own data loading should start immediately.
    initShell({ auth });
  }

  registerServiceWorker();
  reportFatalErrors();
}

function reportFatalErrors() {
  if (typeof window === 'undefined') return;
  window.addEventListener('error', (event) => {
    // Surface a recoverable message rather than leaving a skeleton running.
    console.error('[starmond] uncaught error', event.error || event.message);
  });
  window.addEventListener('unhandledrejection', (event) => {
    console.error('[starmond] unhandled rejection', event.reason);
  });
}

export default boot;
