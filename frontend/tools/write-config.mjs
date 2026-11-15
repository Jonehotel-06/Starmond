#!/usr/bin/env node
/**
 * write-config.mjs — inject PUBLIC deployment configuration into the browser.
 *
 * A browser cannot read a server-side .env. This build step reads .env (or the
 * process environment) and rewrites:
 *   • assets/js/config.js   — the values window.STARMOND_CONFIG exposes
 *   • robots.txt            — the Sitemap host
 *
 * Only allow-listed PUBLIC keys are ever written. Anything else in .env is
 * ignored, so a stray secret cannot leak into the bundle.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

const PUBLIC_KEYS = {
  API_BASE_URL: 'string',
  SITE_URL: 'string',
  AUTH_MODE: 'string',
  CSRF_COOKIE_NAME: 'string',
  CSRF_HEADER_NAME: 'string',
  REQUEST_TIMEOUT_MS: 'number',
  RETRY_ATTEMPTS: 'number',
  RETRY_BASE_DELAY_MS: 'number',
  PUBLIC_CACHE_TTL_MS: 'number',
  SEARCH_DEBOUNCE_MS: 'number',
  CURRENCY: 'string',
  LOCALE: 'string',
  CONTRACT_PREVIEW: 'boolean',
  ENABLE_SW: 'boolean',
  BUILD_ID: 'string',
};

function parseEnv(text) {
  const out = {};
  text.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;
    const eq = trimmed.indexOf('=');
    if (eq < 0) return;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  });
  return out;
}

const envPath = join(root, '.env');
const fileEnv = existsSync(envPath) ? parseEnv(await readFile(envPath, 'utf8')) : {};
const env = { ...fileEnv, ...process.env };

const config = {};
for (const [key, type] of Object.entries(PUBLIC_KEYS)) {
  if (env[key] === undefined) continue;
  const raw = env[key];
  if (type === 'number') {
    const n = Number(raw);
    if (Number.isFinite(n)) config[key] = n;
  } else if (type === 'boolean') {
    config[key] = /^(1|true|yes|on)$/i.test(raw);
  } else {
    config[key] = String(raw);
  }
}

if (config.SITE_URL) config.SITE_URL = config.SITE_URL.replace(/\/+$/, '');
if (config.API_BASE_URL && !/^https?:\/\//i.test(config.API_BASE_URL)) {
  config.API_BASE_URL = config.API_BASE_URL.replace(/\/+$/, '');
}

// Safety rail: refuse to ship a preview banner to a production-looking host.
if (config.CONTRACT_PREVIEW && config.SITE_URL && !/localhost|127\.0\.0\.1|\.local|staging|preview/i.test(config.SITE_URL)) {
  console.error('Refusing to enable CONTRACT_PREVIEW for a production SITE_URL. Set CONTRACT_PREVIEW=false.');
  process.exit(1);
}

const configPath = join(root, 'assets/js/config.js');
const original = await readFile(configPath, 'utf8');
const marker = 'var provided = global.STARMOND_CONFIG || {};';
const injection = `var provided = Object.assign({}, global.STARMOND_CONFIG || {}, ${JSON.stringify(config, null, 2)});`;

if (!original.includes(marker) && !original.includes('var provided = Object.assign(')) {
  console.error('config.js does not contain the expected injection marker. Restore it from version control.');
  process.exit(1);
}
const updated = original.includes(marker)
  ? original.replace(marker, injection)
  : original.replace(/var provided = Object\.assign\([\s\S]*?\);/, injection);

await writeFile(configPath, updated, 'utf8');
console.log(`Wrote public config → assets/js/config.js (${Object.keys(config).length} keys)`);

if (config.SITE_URL) {
  const robotsPath = join(root, 'robots.txt');
  const robots = await readFile(robotsPath, 'utf8');
  await writeFile(robotsPath, robots.replace(/^Sitemap:.*$/m, `Sitemap: ${config.SITE_URL}/sitemap.xml`), 'utf8');
  console.log('Updated robots.txt Sitemap host.');
}

if (!config.API_BASE_URL) {
  console.log('NOTE: API_BASE_URL not set — the default same-origin /api reverse proxy is used.');
}
