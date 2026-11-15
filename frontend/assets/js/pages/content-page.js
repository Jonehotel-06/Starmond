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
    // FAQs are a CMS page (slug "faq") managed in Admin → Pages. Each <h2>/<h3>
    // heading in the page body becomes a question; the content under it is the answer.
    const settings = await getSettings();
    if (!settings.loaded) throw new Error('settings unavailable');
    const page = settings.policies?.faq;
    const faqs = [];
    if (page?.body_html) {
      const doc = new DOMParser().parseFromString(sanitizeHtml(page.body_html), 'text/html');
      let current = null;
      [...doc.body.children].forEach((node) => {
        if (/^H[2-4]$/.test(node.tagName)) { current = { question: node.textContent.trim(), answer_html: '' }; faqs.push(current); }
        else if (current) current.answer_html += node.outerHTML;
      });
      if (!faqs.length) faqs.push({ question: page.title || 'Frequently asked questions', answer_html: doc.body.innerHTML });
    }
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
