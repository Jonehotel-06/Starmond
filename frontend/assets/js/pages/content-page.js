/**
 * content-page.js — CMS-driven informational pages (about, policies, FAQs).
 * Content is authored by the administrator; nothing is invented here.
 */
import boot from '../boot.js';
import api, { normalizeList } from '../api.js';
import { getSettings, renderPolicyContent } from '../site.js';
import { getCategories, renderCategoryCards } from '../categories.js';
import { resolveRegion, emptyState, skeletons } from '../ui.js';
import { hydrateIcons, icon } from '../icons.js';
import { $, esc, sanitizeHtml } from '../utils.js';

await boot();

/* Policy / about bodies --------------------------------------------------- */
const cmsHolder = $('[data-cms-page]');
if (cmsHolder) {
  const key = cmsHolder.dataset.cmsPage;
  const settings = await getSettings();
  const title = document.querySelector('h1')?.textContent || key;
  renderPolicyContent(cmsHolder, settings, key, { title });
  // Sanitize admin-authored HTML before it stays in the DOM.
  cmsHolder.innerHTML = sanitizeHtml(cmsHolder.innerHTML);
  hydrateIcons(cmsHolder);

  // FAQPage structured data only when genuine FAQ content exists.
  const faqs = settings?.policies?.[key]?.faqs;
  if (Array.isArray(faqs) && faqs.length) {
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faqs.map((faq) => ({
        '@type': 'Question',
        name: faq.question,
        acceptedAnswer: { '@type': 'Answer', text: faq.answer },
      })),
    });
    document.head.appendChild(script);
  }
}

/* About page category grid ------------------------------------------------ */
const aboutCategories = $('[data-about-categories]');
if (aboutCategories) {
  try {
    const tree = await getCategories();
    if (!tree.length) {
      resolveRegion(aboutCategories, emptyState({ title: 'Departments coming soon', text: 'Our categories will appear here once published.', iconName: 'folder', inline: true }));
    } else {
      resolveRegion(aboutCategories, `<div class="category-grid">${renderCategoryCards(tree)}</div>`);
    }
  } catch {
    resolveRegion(aboutCategories, emptyState({ title: 'Categories unavailable', text: 'Please refresh to try again.', iconName: 'folder', inline: true }));
  }
}

/* FAQ list ---------------------------------------------------------------- */
const faqHolder = $('[data-faq-list]');
if (faqHolder) {
  try {
    const data = await api.publicGet('/faqs/');
    const faqs = normalizeList(data).results;
    if (!faqs.length) {
      resolveRegion(faqHolder, emptyState({
        title: 'No FAQs published yet',
        text: 'Our team is preparing answers to common questions. In the meantime, contact us and we will help directly.',
        iconName: 'message',
        actionHtml: '<a class="btn btn--primary btn--sm" href="/contact.html">Contact us</a>',
      }));
    } else {
      resolveRegion(faqHolder, `<div class="accordion">${faqs.map((faq, index) => `
        <details class="accordion__item" ${index === 0 ? 'open' : ''}>
          <summary class="accordion__summary">${esc(faq.question)} ${icon('chevron-down', { size: 'sm' })}</summary>
          <div class="accordion__content">${sanitizeHtml(faq.answer_html || esc(faq.answer || ''))}</div>
        </details>`).join('')}</div>`);
      const script = document.createElement('script');
      script.type = 'application/ld+json';
      script.textContent = JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: faqs.map((faq) => ({
          '@type': 'Question', name: faq.question,
          acceptedAnswer: { '@type': 'Answer', text: String(faq.answer || faq.answer_html || '').replace(/<[^>]*>/g, ' ').trim() },
        })),
      });
      document.head.appendChild(script);
    }
  } catch {
    resolveRegion(faqHolder, emptyState({
      title: 'FAQs could not be loaded', text: 'Please refresh, or contact us with your question.', iconName: 'alert-triangle',
      actionHtml: '<a class="btn btn--primary btn--sm" href="/contact.html">Contact us</a>',
    }));
  }
}
