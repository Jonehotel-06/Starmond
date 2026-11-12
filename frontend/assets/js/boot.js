/* Early, render-blocking-safe boot script.
   It only flags capabilities on <html> so the first paint is correct and the
   page never flashes a "no JavaScript" layout. No business logic lives here. */
(function () {
  var html = document.documentElement;
  html.classList.add('js');

  var cfg = window.STARMOND_CONFIG || {};
  var host = window.location.hostname;
  var hosts = cfg.PRODUCTION_HOSTS || [];
  var isProdHost = hosts.indexOf(host) !== -1;
  var hasApi = !!(cfg.API_BASE_URL && cfg.API_BASE_URL.trim());
  var forcedDemo = /[?&]demo=1\b/.test(window.location.search);

  var demo = forcedDemo || (!hasApi && !isProdHost);
  html.dataset.demo = demo ? 'on' : 'off';

  /* Network Information API + Service Worker support flags (progressive). */
  if ('serviceWorker' in navigator) html.dataset.sw = 'on';
  window.__STARMOND_BOOT__ = { demo: demo, bootedAt: Date.now() };
})();
