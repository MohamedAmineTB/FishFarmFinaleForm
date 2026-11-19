// Visual check: captures the same 36 states as docs/screenshots into docs/screenshots-build/.
// Usage: node scripts/capture.mjs [filter]   (needs the API, the pipeline and the dev server running,
// and a freshly seeded demo farm: python -m app.seed --reset)
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = resolve(import.meta.dirname, '../../docs/screenshots-build');
mkdirSync(OUT, { recursive: true });
const only = process.argv[2];

const D = (h) => ({ viewport: { width: 1440, height: h }, deviceScaleFactor: 1 });
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
const OWNER = ['nadia@lacvert.farm', 'owner'];
const WORKER = ['karim@lacvert.farm', 'team'];
const TECH = ['samir@lacvert.farm', 'team'];

const settle = (page, ms = 900) => page.waitForTimeout(ms);
async function basin3(page) {
  const r = await page.request.get(BASE + '/api/basins', { headers: { Authorization: 'Bearer ' + (await token(page)) } });
  return (await r.json()).find((b) => b.name === 'Basin 3').id;
}
async function token(page) {
  const r = await page.request.post(BASE + '/api/auth/refresh');
  return (await r.json()).access_token;
}

const S = [
  ['01-website-full-desktop', D(900), null, '/', null, { full: true, wait: 2500 }],
  ['02-website-hero-desktop', D(900), null, '/', null, { wait: 2500 }],
  ['03-owner-sign-in', D(900), null, '/owner-auth'],
  ['04-owner-sign-in-wrong-password', D(900), null, '/owner-auth', async (p) => {
    await p.fill('#oEmail', 'nadia@lacvert.farm');
    await p.fill('#oPass', 'wrong-password');
    await p.click('button[type=submit]');
    await p.waitForSelector('#oErr');
  }],
  ['05-owner-create-farm-validation', D(900), null, '/owner-auth', async (p) => {
    await p.click('text=Create farm >> nth=0');
    await p.fill('#rEmail', 'not-an-email');
    await p.fill('#rPass', 'short');
    await p.click('button[type=submit]');
  }],
  ['06-team-sign-in', D(900), null, '/worker-auth'],
  ['10-owner-overview', D(1900), OWNER, '/owner'],
  ['11-owner-basins', D(1900), OWNER, '/owner/basins'],
  ['12-owner-basin-detail-oxygen', D(1900), OWNER, async (p) => `/owner/basins/${await basin3(p)}`],
  ['13-owner-basin-detail-temperature', D(1900), OWNER, async (p) => `/owner/basins/${await basin3(p)}`, async (p) => {
    await p.click('[role=tab]:has-text("Temp")');
  }],
  ['14-owner-alerts-open', D(1900), OWNER, '/owner/alerts'],
  ['15-alert-resolve-dialog', D(1900), OWNER, '/owner/alerts', async (p) => {
    await p.click('.alert >> nth=1 >> .check');
  }],
  ['16-alert-just-resolved', D(1900), OWNER, '/owner/alerts', async (p) => {
    await p.click('.alert >> nth=1 >> .check');
    await p.fill('#resNote', 'Tested ammonia, all fine. Will re-check pH at 15:00.');
    await p.click('.modal button[type=submit]');
    await p.waitForSelector('.alert.just-done');
  }, { wait: 300 }],
  ['17-alerts-done-tab', D(1900), OWNER, '/owner/alerts', async (p) => {
    await p.click('[role=tab]:has-text("Done")');
  }],
  ['18-owner-reports', D(1900), OWNER, '/owner/reports'],
  ['19-report-open-mark-as-read', D(1900), OWNER, '/owner/reports', async (p) => {
    await p.click('.report-open >> nth=0');
  }],
  ['20-reports-all-read', D(1900), OWNER, '/owner/reports', async (p) => {
    const btn = p.locator('text=Mark all as read');
    if (await btn.count()) await btn.click();
  }],
  ['21-owner-team', D(1900), OWNER, '/owner/team'],
  ['22-team-permissions-sheet', D(1900), OWNER, '/owner/team', async (p) => {
    await p.click('text=Edit permissions >> nth=0');
  }],
  ['23-team-add-member-sheet', D(1900), OWNER, '/owner/team', async (p) => {
    await p.click('text=+ Add member');
  }],
  ['24-notifications-dropdown', D(1900), OWNER, '/owner', async (p) => {
    await p.click('#bellBtn');
  }],
  ['25-assistant-empty', D(1900), OWNER, '/owner', async (p) => {
    await p.click('text=Ask the farm');
  }, { wait: 700 }],
  ['26-assistant-answer-with-chart', D(1900), OWNER, '/owner', async (p) => {
    await p.click('text=Ask the farm');
    await p.click('.ai-empty .chip:has-text("Why did oxygen drop in Basin 3")');
    await p.waitForSelector('.msg-ai .fb', { timeout: 20000 });
  }],
  ['30-worker-today', D(1900), WORKER, '/worker'],
  ['31-worker-alerts', D(1900), WORKER, '/worker/alerts'],
  ['32-worker-shift-report-validation', D(1900), WORKER, '/worker/report', async (p) => {
    await p.click('button:has-text("Send report")');
  }],
  ['33-worker-basin-detail', D(1900), WORKER, async (p) => `/worker/basins/${await basin3(p)}`],
  ['40-technician-today', D(1500), TECH, '/technician'],
  ['41-technician-hardware-alerts', D(1500), TECH, '/technician/alerts'],
  ['42-technician-sensor-health', D(1500), TECH, '/technician/sensors'],
  ['43-technician-maintenance', D(1500), TECH, '/technician/maintenance'],
  ['50-mobile-website-hero', PHONE, null, '/', null, { wait: 2500 }],
  ['51-mobile-sign-in', PHONE, null, '/owner-auth'],
  ['52-mobile-owner-overview', PHONE, OWNER, '/owner'],
  ['53-mobile-alerts', PHONE, OWNER, '/owner/alerts'],
  ['54-mobile-assistant', PHONE, OWNER, '/owner', async (p) => {
    await p.click('.top-acts .small-btn.primary');
    await p.click('.ai-empty .chip:has-text("Why did oxygen drop in Basin 3")');
    await p.waitForSelector('.msg-ai .fb', { timeout: 20000 });
  }],
];

const browser = await chromium.launch();
let failed = 0;
for (const [name, device, login, path, action, opts = {}] of S) {
  if (only && !name.includes(only)) continue;
  const ctx = await browser.newContext({ ...device, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  try {
    if (login) {
      const r = await page.request.post(BASE + '/api/auth/login', { data: { email: login[0], password: 'demo1234', portal: login[1] } });
      if (!r.ok()) throw new Error('login failed ' + r.status());
    }
    const url = typeof path === 'function' ? await path(page) : path;
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    await settle(page, opts.wait ?? 1200);
    if (action) {
      await action(page);
      await settle(page, opts.wait ?? 900);
    }
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: !!opts.full });
    console.log('✓', name, errors.length ? 'page errors: ' + errors.join(' | ') : '');
  } catch (e) {
    failed++;
    console.log('✗', name, e.message.split('\n')[0]);
  }
  await ctx.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
