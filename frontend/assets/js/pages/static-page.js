/**
 * static-page.js — bootstrap for pages with no data of their own.
 *
 * Error pages (403/404/500) and the offline fallback still render the shared
 * header, mobile drawer and footer. Those contain category placeholders, so a
 * page that loads no module at all would leave skeletons animating forever.
 * This module boots the shell (which resolves or empties every placeholder)
 * and nothing else.
 *
 * On the offline page the shell's category request will fail; initShell's
 * error path replaces the skeleton with a real fallback, which is exactly the
 * behaviour we want.
 */
import boot from '../boot.js';

await boot();
