#!/usr/bin/env node
/**
 * build-pages.mjs — generate every static HTML page from shared partials.
 *
 * Usage:  node tools/build-pages.mjs
 *
 * This is a build-time step, not a runtime framework. The emitted files are
 * plain HTML5 with real titles, descriptions, canonicals, JSON-LD, breadcrumbs
 * and crawlable navigation. Vanilla JS then hydrates the dynamic regions.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { storefrontPage, adminPage } from './lib/shell.mjs';
import { storefrontPages } from './pages/storefront.mjs';
import { adminPages } from './pages/admin.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

async function write(relative, contents) {
  const target = join(root, relative);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, contents, 'utf8');
  return relative;
}

const written = [];

for (const page of storefrontPages) {
  const canonical = page.canonical || `${(process.env.SITE_URL || '').replace(/\/$/, '')}${page.path}`;
  written.push(await write(page.file, storefrontPage({ ...page, canonical }, page.body)));
}

for (const page of adminPages) {
  written.push(await write(page.file, adminPage(page, page.body)));
}

console.log(`Built ${written.length} HTML pages.`);
written.sort().forEach((file) => console.log(`  ${file}`));
