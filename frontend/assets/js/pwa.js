/**
 * pwa.js — service worker registration and update detection.
 *
 * The worker caches only public static assets and the offline page. It never
 * caches cart, checkout, account, order or payment responses.
 */

import { toast } from './ui.js';

export function registerServiceWorker() {
  const config = (typeof window !== 'undefined' && window.STARMOND_CONFIG) || {};
  if (!config.ENABLE_SW) return;
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    // Service workers require a secure context. Skip silently on plain http.
    return;
  }

  window.addEventListener('load', async () => {
    try {
      const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });

      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) {
            toast('A new version of the store is available.', {
              type: 'info',
              duration: 0,
              action: {
                label: 'Reload to update',
                onClick: () => {
                  worker.postMessage({ type: 'SKIP_WAITING' });
                  navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), { once: true });
                },
              },
            });
          }
        });
      });
    } catch (error) {
      console.warn('[pwa] service worker registration failed', error);
    }
  });
}

/** Prompt the browser install flow when the platform offers it. */
export function initInstallPrompt(selector = '[data-install-app]') {
  let deferred = null;
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferred = event;
    document.querySelectorAll(selector).forEach((node) => { node.hidden = false; });
  });
  document.addEventListener('click', async (event) => {
    const button = event.target.closest(selector);
    if (!button || !deferred) return;
    deferred.prompt();
    await deferred.userChoice;
    deferred = null;
    button.hidden = true;
  });
  window.addEventListener('appinstalled', () => {
    document.querySelectorAll(selector).forEach((node) => { node.hidden = true; });
  });
}

export default registerServiceWorker;
