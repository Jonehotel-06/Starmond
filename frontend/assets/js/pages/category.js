/** Category landing page (/category/<slug>/). Category is fixed by the URL path. */
import '../app.js';
import { setupListing } from './listing.js';

const segments = window.location.pathname.split('/').filter(Boolean);
const categoryIndex = segments.indexOf('category');
const slug = categoryIndex >= 0 ? segments[categoryIndex + 1] : null;

const listing = setupListing({ fixedCategory: slug || null });

/* Personalise the intro copy with the live count once products arrive. */
document.addEventListener('starmond:products-loaded', (event) => {
  const count = event.detail?.count;
  const lede = document.querySelector('.page-head__lede');
  if (!lede || typeof count !== 'number') return;
  if (count > 0) lede.dataset.count = String(count);
});

export default listing;
