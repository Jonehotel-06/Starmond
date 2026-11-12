/** Promotions landing page: same listing engine, pinned to on-sale products. */
import '../app.js';
import { setupListing } from './listing.js';

const listing = setupListing({ preset: { on_sale: 1, ordering: '-discount_percentage' } });
export default listing;
