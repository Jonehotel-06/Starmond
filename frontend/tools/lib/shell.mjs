/**
 * shell.mjs — shared HTML partials for the build-time page generator.
 *
 * Why a generator? The brief requires meaningful initial HTML (titles, meta,
 * canonical, breadcrumbs, crawlable links) with no frontend framework. Writing
 * that HTML at build time from one set of partials guarantees every page has
 * identical, correct SEO scaffolding and navigation, and keeps the shipped
 * output as plain static HTML.
 *
 * Output: pure HTML5. No runtime dependency on this file.
 */

export const BUSINESS_NAME = 'STARMOND TECHNOLOGY LIMITED';
export const SHORT_NAME = 'Starmond';

/** Inline brand mark — no external request, no icon font. */
export const LOGO_SVG = `<svg class="brand__mark" viewBox="0 0 40 40" role="img" aria-label="Starmond Technology Limited">
  <rect width="40" height="40" rx="9" fill="#6335A8"/>
  <path d="M20 8.5l2.9 6.35 6.95.72-5.2 4.66 1.45 6.84L20 23.6l-6.1 3.47 1.45-6.84-5.2-4.66 6.95-.72z" fill="#fff"/>
  <circle cx="30.5" cy="10.5" r="2.1" fill="#CBB2F0"/>
</svg>`;

const CSS_BASE = [
  '/assets/css/variables.css',
  '/assets/css/typography.css',
  '/assets/css/main.css',
  '/assets/css/components.css',
  '/assets/css/skeletons.css',
  '/assets/css/pages/storefront.css',
  '/assets/css/responsive.css',
];

const CSS_ADMIN = ['/assets/css/pages/admin.css'];

/**
 * @param {object} page
 * @param {string} page.title      unique <title>
 * @param {string} page.description unique meta description
 * @param {string} page.path       canonical path, always with trailing slash or .html
 * @param {string} [page.robots]
 * @param {string} [page.ogImage]
 * @param {object[]} [page.jsonLd]
 * @param {string} [page.bodyClass]
 * @param {boolean} [page.admin]
 * @param {string} [page.module]   page JS entry point
 * @param {string} [page.preloadImage]
 */
export function head(page) {
  const styles = [...CSS_BASE, ...(page.admin ? CSS_ADMIN : [])];
  const robots = page.robots || 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1';
  const jsonLd = page.jsonLd || [];
  return `<!DOCTYPE html>
<html lang="en-NG">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${escapeHtml(page.title)}</title>
<meta name="description" content="${escapeHtml(page.description)}">
<link rel="canonical" href="${escapeHtml(page.canonical || page.path)}">
<meta name="robots" content="${escapeHtml(robots)}">
<meta name="theme-color" content="#6335A8">
<meta name="format-detection" content="telephone=no">
<meta name="author" content="${BUSINESS_NAME}">
<meta property="og:type" content="${page.ogType || 'website'}">
<meta property="og:site_name" content="${BUSINESS_NAME}">
<meta property="og:title" content="${escapeHtml(page.ogTitle || page.title)}">
<meta property="og:description" content="${escapeHtml(page.ogDescription || page.description)}">
<meta property="og:url" content="${escapeHtml(page.canonical || page.path)}">
<meta property="og:locale" content="en_NG">
${page.ogImage ? `<meta property="og:image" content="${escapeHtml(page.ogImage)}">` : ''}
<meta name="twitter:card" content="${page.ogImage ? 'summary_large_image' : 'summary'}">
<meta name="twitter:title" content="${escapeHtml(page.ogTitle || page.title)}">
<meta name="twitter:description" content="${escapeHtml(page.ogDescription || page.description)}">
${page.ogImage ? `<meta name="twitter:image" content="${escapeHtml(page.ogImage)}">` : ''}
<link rel="icon" href="/assets/icons/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/icons/icon-192.png">
<link rel="manifest" href="/manifest.webmanifest">
${page.preloadImage ? `<link rel="preload" as="image" href="${escapeHtml(page.preloadImage)}" fetchpriority="high">` : ''}
${styles.map((href) => `<link rel="stylesheet" href="${href}">`).join('\n')}
<script src="/assets/js/config.js"></script>
${jsonLd.map((data) => `<script type="application/ld+json">${JSON.stringify(data)}</script>`).join('\n')}
${page.module ? `<script type="module" src="${page.module}"></script>` : ''}
</head>
<body${page.bodyClass ? ` class="${page.bodyClass}"` : ''}>
<a class="sr-only sr-only-focusable skip-link" href="#main">Skip to main content</a>`;
}

/* ============================================================================
   Storefront header
   ========================================================================== */

export function header() {
  return `<div class="announce">
  <div class="container announce__inner">
    <span class="announce__item"><i data-icon="truck" data-size="sm"></i> Nationwide delivery across Nigeria</span>
    <span class="announce__item announce__item--secondary announce__item--muted"><i data-icon="shield" data-size="sm"></i> Secure checkout with Paystack</span>
    <span class="announce__item announce__item--secondary"><a href="/contact.html">Need help? Contact us</a></span>
  </div>
</div>

<header class="site-header">
  <div class="container site-header__inner">
    <button type="button" class="icon-btn only-mobile" data-menu-trigger aria-label="Open navigation menu" aria-controls="mobile-drawer">
      <i data-icon="menu"></i>
    </button>

    <a class="brand" href="/" aria-label="${BUSINESS_NAME} — home">
      ${LOGO_SVG}
      <span class="brand__text">
        <span class="brand__name">Starmond</span>
        <span class="brand__tag">Technology Limited</span>
      </span>
    </a>

    <nav class="main-nav" aria-label="Main navigation">
      <a class="main-nav__link" href="/shop.html">Shop</a>
      <span data-mega-wrapper>
        <button type="button" class="main-nav__link" data-mega-trigger aria-expanded="false" aria-controls="mega-panel">
          Categories <i data-icon="chevron-down" data-size="sm"></i>
        </button>
      </span>
      <a class="main-nav__link" href="/shop.html?sort=newest">New arrivals</a>
      <a class="main-nav__link" href="/shop.html?featured=1">Featured</a>
      <a class="main-nav__link" href="/about.html">About</a>
      <a class="main-nav__link" href="/contact.html">Contact</a>
    </nav>

    <div class="header-search" data-header-search>
      <form class="header-search__form" action="/search.html" method="get" role="search">
        <span class="header-search__icon"><i data-icon="search" data-size="sm"></i></span>
        <label class="sr-only" for="header-search-input">Search products</label>
        <input class="header-search__input" id="header-search-input" type="search" name="q"
               placeholder="Search products, brands and categories" autocomplete="off">
        <button class="header-search__submit" type="submit" aria-label="Submit search"><i data-icon="arrow-right" data-size="sm"></i></button>
      </form>
      <div class="search-panel" data-search-panel hidden></div>
    </div>

    <div class="header-actions">
      <a class="icon-btn only-mobile" href="/search.html" aria-label="Search products"><i data-icon="search"></i></a>
      <span class="header-actions__wrap">
        <button type="button" class="icon-btn" data-account-trigger aria-expanded="false" aria-controls="account-menu" aria-label="Sign in or create an account">
          <i data-icon="user"></i>
        </button>
        <div class="menu" id="account-menu" data-account-menu hidden></div>
      </span>
      <a class="icon-btn" href="/cart.html" data-cart-link aria-label="Cart">
        <i data-icon="cart"></i>
        <span class="icon-btn__count" data-cart-count hidden>0</span>
      </a>
    </div>
  </div>

  <div class="mega" id="mega-panel" data-mega-panel hidden>
    <div class="container" data-mega-content></div>
  </div>
</header>

<div class="drawer-backdrop" data-drawer-backdrop></div>
<aside class="drawer" id="mobile-drawer" data-mobile-drawer aria-label="Mobile navigation">
  <div class="drawer__head">
    <span class="drawer__title">Menu</span>
    <button type="button" class="icon-btn" data-drawer-close aria-label="Close navigation menu"><i data-icon="x"></i></button>
  </div>
  <div class="drawer__body">
    <nav class="drawer-nav" aria-label="Mobile main navigation">
      <a class="drawer-nav__link" href="/">Home</a>
      <a class="drawer-nav__link" href="/shop.html">Shop all products</a>
      <a class="drawer-nav__link" href="/shop.html?sort=newest">New arrivals</a>
      <a class="drawer-nav__link" href="/shop.html?featured=1">Featured products</a>
      <div class="drawer-nav__group">
        <p class="admin-nav__label" style="color:var(--color-muted)">Categories</p>
        <div data-drawer-categories>
          <div class="stack stack--sm" style="padding:var(--space-3)" aria-hidden="true">
            <span class="sk sk--text sk--w-70"></span><span class="sk sk--text sk--w-50"></span><span class="sk sk--text sk--w-60"></span>
          </div>
        </div>
      </div>
      <div class="drawer-nav__group">
        <a class="drawer-nav__link" href="/about.html">About us</a>
        <a class="drawer-nav__link" href="/contact.html">Contact us</a>
        <a class="drawer-nav__link" href="/faq.html">FAQs</a>
        <a class="drawer-nav__link" href="/track-order.html">Track an order</a>
      </div>
      <div class="drawer-nav__group">
        <a class="drawer-nav__link" href="/account.html" data-auth-user hidden>My account</a>
        <a class="drawer-nav__link" href="/orders.html" data-auth-user hidden>My orders</a>
        <a class="drawer-nav__link" href="/wishlist.html" data-auth-user hidden>Wishlist</a>
        <a class="drawer-nav__link" href="/login.html" data-auth-guest>Sign in</a>
        <a class="drawer-nav__link" href="/register.html" data-auth-guest>Create account</a>
      </div>
    </nav>
  </div>
</aside>`;
}

/* ============================================================================
   Storefront footer
   ========================================================================== */

export function footer() {
  return `<footer class="site-footer">
  <div class="container">
    <div class="site-footer__grid">
      <div class="site-footer__about">
        <a class="brand" href="/" aria-label="${BUSINESS_NAME} — home">
          ${LOGO_SVG}
          <span class="brand__text">
            <span class="brand__name">Starmond</span>
            <span class="brand__tag">Technology Limited</span>
          </span>
        </a>
        <p class="t-sm t-muted" data-business-description>Electrical supplies, fashion, electronics and household products, supplied by ${BUSINESS_NAME}.</p>
        <div class="site-footer__contact">
          <span class="site-footer__contact-item" data-contact-row hidden><i data-icon="mail" data-size="sm"></i><a data-business-email href="#"></a></span>
          <span class="site-footer__contact-item" data-contact-row hidden><i data-icon="phone" data-size="sm"></i><a data-business-phone href="#"></a></span>
          <span class="site-footer__contact-item" data-contact-row hidden><i data-icon="map-pin" data-size="sm"></i><span data-business-address></span></span>
        </div>
        <div class="site-footer__social" data-social-links hidden></div>
      </div>

      <nav aria-labelledby="footer-shop">
        <h2 class="site-footer__title" id="footer-shop">Shop</h2>
        <ul class="site-footer__links" data-footer-categories>
          <li><a href="/shop.html">All products</a></li>
        </ul>
      </nav>

      <nav aria-labelledby="footer-care">
        <h2 class="site-footer__title" id="footer-care">Customer care</h2>
        <ul class="site-footer__links">
          <li><a href="/contact.html">Contact us</a></li>
          <li><a href="/faq.html">Frequently asked questions</a></li>
          <li><a href="/track-order.html">Track an order</a></li>
          <li><a href="/policies/shipping.html">Shipping policy</a></li>
          <li><a href="/policies/returns.html">Returns and refunds</a></li>
          <li><a href="/account.html">My account</a></li>
        </ul>
      </nav>

      <nav aria-labelledby="footer-company">
        <h2 class="site-footer__title" id="footer-company">Company</h2>
        <ul class="site-footer__links">
          <li><a href="/about.html">About us</a></li>
          <li><a href="/policies/privacy.html">Privacy policy</a></li>
          <li><a href="/policies/terms.html">Terms and conditions</a></li>
          <li><a href="/shop.html?sort=newest">New arrivals</a></li>
          <li><a href="/shop.html?featured=1">Featured products</a></li>
        </ul>
      </nav>
    </div>

    <div class="site-footer__bottom">
      <p>&copy; <span data-current-year>2026</span> <span data-business-name>${BUSINESS_NAME}</span>. All rights reserved.</p>
      <div class="site-footer__legal">
        <a href="/policies/privacy.html">Privacy</a>
        <a href="/policies/terms.html">Terms</a>
        <a href="/policies/shipping.html">Shipping</a>
        <a href="/policies/returns.html">Returns</a>
      </div>
    </div>
  </div>
</footer>`;
}

/* ============================================================================
   Admin shell
   ========================================================================== */

export const ADMIN_MODULES = [
  { group: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', href: '/admin/index.html', icon: 'dashboard' },
    { id: 'reports', label: 'Reports', href: '/admin/reports.html', icon: 'chart', perm: 'reports.view' },
  ]},
  { group: 'Catalogue', items: [
    { id: 'products', label: 'Products', href: '/admin/products.html', icon: 'package', perm: 'products.view' },
    { id: 'categories', label: 'Categories', href: '/admin/categories.html', icon: 'folder', perm: 'categories.view' },
    { id: 'subcategories', label: 'Subcategories', href: '/admin/subcategories.html', icon: 'layers', perm: 'categories.view' },
    { id: 'variations', label: 'Variations', href: '/admin/variations.html', icon: 'grid', perm: 'products.view' },
    { id: 'inventory', label: 'Inventory', href: '/admin/inventory.html', icon: 'clipboard', perm: 'inventory.view' },
    { id: 'media', label: 'Media library', href: '/admin/media.html', icon: 'image', perm: 'media.view' },
  ]},
  { group: 'Sales', items: [
    { id: 'orders', label: 'Orders', href: '/admin/orders.html', icon: 'receipt', perm: 'orders.view' },
    { id: 'payments', label: 'Payments', href: '/admin/payments.html', icon: 'credit-card', perm: 'payments.view' },
    { id: 'refunds', label: 'Refunds', href: '/admin/refunds.html', icon: 'undo', perm: 'refunds.view' },
    { id: 'delivery', label: 'Delivery', href: '/admin/delivery.html', icon: 'truck', perm: 'delivery.view' },
    { id: 'shipping-zones', label: 'Shipping zones', href: '/admin/shipping-zones.html', icon: 'map-pin', perm: 'delivery.view' },
  ]},
  { group: 'Customers', items: [
    { id: 'customers', label: 'Customers', href: '/admin/customers.html', icon: 'users', perm: 'customers.view' },
    { id: 'reviews', label: 'Reviews', href: '/admin/reviews.html', icon: 'star', perm: 'reviews.view' },
    { id: 'enquiries', label: 'Enquiries', href: '/admin/enquiries.html', icon: 'message', perm: 'enquiries.view' },
    { id: 'newsletter', label: 'Newsletter', href: '/admin/newsletter.html', icon: 'mail', perm: 'newsletter.view' },
  ]},
  { group: 'Marketing', items: [
    { id: 'discounts', label: 'Discounts', href: '/admin/discounts.html', icon: 'percent', perm: 'discounts.view' },
    { id: 'promotions', label: 'Promotions', href: '/admin/promotions.html', icon: 'tag', perm: 'promotions.view' },
  ]},
  { group: 'Content', items: [
    { id: 'content', label: 'Website content', href: '/admin/content.html', icon: 'file-text', perm: 'content.view' },
    { id: 'homepage', label: 'Homepage', href: '/admin/homepage.html', icon: 'home', perm: 'content.view' },
    { id: 'seo', label: 'SEO settings', href: '/admin/seo.html', icon: 'globe', perm: 'seo.view' },
  ]},
  { group: 'System', items: [
    { id: 'notifications', label: 'Notifications', href: '/admin/notifications.html', icon: 'bell', perm: 'notifications.view' },
    { id: 'email-logs', label: 'Email logs', href: '/admin/email-logs.html', icon: 'send', perm: 'notifications.view' },
    { id: 'staff', label: 'Staff & permissions', href: '/admin/staff.html', icon: 'shield', perm: 'staff.view' },
    { id: 'audit-logs', label: 'Audit logs', href: '/admin/audit-logs.html', icon: 'eye', perm: 'audit.view' },
    { id: 'settings', label: 'Business settings', href: '/admin/settings.html', icon: 'settings', perm: 'settings.view' },
  ]},
];

export function adminSidebar(activeId) {
  return `<aside class="admin-sidebar" id="admin-sidebar" data-admin-sidebar aria-label="Administration navigation">
  <div class="admin-sidebar__head">
    <a class="admin-sidebar__brand" href="/admin/index.html">
      ${LOGO_SVG}
      <span class="brand__text">
        <span class="admin-sidebar__brand-name">Starmond</span>
        <span class="admin-sidebar__brand-tag">Admin console</span>
      </span>
    </a>
    <button type="button" class="icon-btn only-mobile" data-admin-close aria-label="Close administration menu" style="color:#c9c6d4;margin-left:auto"><i data-icon="x"></i></button>
  </div>
  <nav class="admin-sidebar__nav">
    ${ADMIN_MODULES.map((group) => `
    <div class="admin-nav__group">
      <p class="admin-nav__label">${group.group}</p>
      ${group.items.map((item) => `<a class="admin-nav__link" href="${item.href}"${item.id === activeId ? ' aria-current="page"' : ''}${item.perm ? ` data-perm="${item.perm}"` : ''}>
        <i data-icon="${item.icon}" data-size="sm"></i><span>${item.label}</span>
      </a>`).join('')}
    </div>`).join('')}
  </nav>
  <div class="admin-sidebar__foot">
    <a class="admin-nav__link" href="/" target="_blank" rel="noopener"><i data-icon="external-link" data-size="sm"></i><span>View storefront</span></a>
    <button type="button" class="admin-nav__link" data-admin-logout style="width:100%"><i data-icon="log-out" data-size="sm"></i><span>Sign out</span></button>
  </div>
</aside>`;
}

export function adminTopbar(title) {
  return `<div class="admin-topbar">
  <button type="button" class="icon-btn admin-menu-trigger" data-admin-menu aria-label="Open administration menu" aria-controls="admin-sidebar"><i data-icon="menu"></i></button>
  <h1 class="admin-topbar__title">${escapeHtml(title)}</h1>
  <div class="admin-topbar__search">
    <i data-icon="search" data-size="sm"></i>
    <label class="sr-only" for="admin-global-search">Search the administration console</label>
    <input class="input" id="admin-global-search" type="search" placeholder="Search products, orders, customers" data-admin-search>
  </div>
  <div class="admin-topbar__actions">
    <a class="icon-btn" href="/admin/notifications.html" aria-label="Notifications"><i data-icon="bell"></i></a>
    <span class="header-actions__wrap">
      <button type="button" class="icon-btn" data-admin-profile aria-expanded="false" aria-controls="admin-profile-menu" aria-label="Account menu"><i data-icon="user"></i></button>
      <div class="menu" id="admin-profile-menu" data-admin-profile-menu hidden></div>
    </span>
  </div>
</div>`;
}

/* ============================================================================
   Page assembly
   ========================================================================== */

export function storefrontPage(page, body) {
  return `${head(page)}
${header()}
<main id="main">
${body}
</main>
${footer()}
</body>
</html>
`;
}

export function adminPage(page, body) {
  return `${head({ ...page, admin: true, robots: 'noindex, nofollow', bodyClass: 'admin-body' })}
<div class="drawer-backdrop" data-admin-backdrop></div>
<div class="admin-shell">
${adminSidebar(page.adminId)}
<div class="admin-main">
${adminTopbar(page.heading || page.title.split(' — ')[0])}
<div class="admin-content" id="main">
${body}
</div>
</div>
</div>
</body>
</html>
`;
}

/** Minimal shell for error/offline pages — no API calls, works offline. */
export function barePage(page, body) {
  return `${head({ ...page, module: page.module ?? null })}
${header()}
<main id="main">
${body}
</main>
${footer()}
</body>
</html>
`;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Site-wide Organization + WebSite JSON-LD. No fabricated ratings or address. */
export function baseJsonLd(origin) {
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      '@id': `${origin}/#organization`,
      name: BUSINESS_NAME,
      url: `${origin}/`,
      logo: `${origin}/assets/icons/icon-512.png`,
    },
    {
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      '@id': `${origin}/#website`,
      name: BUSINESS_NAME,
      url: `${origin}/`,
      publisher: { '@id': `${origin}/#organization` },
      inLanguage: 'en-NG',
      potentialAction: {
        '@type': 'SearchAction',
        target: { '@type': 'EntryPoint', urlTemplate: `${origin}/search.html?q={search_term_string}` },
        'query-input': 'required name=search_term_string',
      },
    },
  ];
}
