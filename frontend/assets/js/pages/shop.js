/** Shop-all listing page. Query string is the single source of truth. */
import '../app.js';
import { setupListing } from './listing.js';
import { qs } from '../utils.js';

const summary = qs('[data-shop-summary]');
const listing = setupListing({ summaryEl: summary });

/* Keep the H1 useful when the page is opened with a search term. */
function reflectSearch() {
  const term = new URLSearchParams(location.search).get('q');
  const title = qs('#shop-title');
  if (term && title) {
    title.textContent = `Search results for “${term}”`;
    document.title = `${term} — Search | STARMOND TECHNOLOGY LIMITED`;
  }
}
reflectSearch();
document.addEventListener('starmond:products-loaded', reflectSearch);
window.addEventListener('popstate', reflectSearch);
export default listing;
