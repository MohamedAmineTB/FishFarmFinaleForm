// Quick screenshot: node scripts/shot.mjs <url-path> <out.png> [desktop|phone] [full]
import { chromium } from '@playwright/test';

const [, , path = '/', out = 'shot.png', device = 'desktop', full = ''] = process.argv;
const base = process.env.BASE_URL ?? 'http://localhost:5173';
const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: device === 'phone' ? { width: 390, height: 844 } : { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  reducedMotion: 'reduce',
});
const page = await ctx.newPage();
page.on('pageerror', (e) => console.log('PAGE ERROR', e.message));
page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text()));
// LOGIN=email,portal signs in first (the refresh cookie restores the session in the app)
if (process.env.LOGIN) {
  const [email, portal = 'owner'] = process.env.LOGIN.split(',');
  const r = await page.request.post(base + '/api/auth/login', { data: { email, password: 'demo1234', portal } });
  if (!r.ok()) console.log('LOGIN FAILED', r.status());
}
await page.goto(base + path, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.screenshot({ path: out, fullPage: full === 'full' });
await browser.close();
console.log('saved', out);
