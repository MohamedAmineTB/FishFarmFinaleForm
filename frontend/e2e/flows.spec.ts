// Main flows of each role, against the real API and a seeded demo farm.
import { expect, test, type Page } from '@playwright/test';

async function signIn(page: Page, email: string, team = false) {
  await page.goto(team ? '/worker-auth' : '/owner-auth');
  await page.fill(team ? '#tEmail' : '#oEmail', email);
  await page.fill(team ? '#tPass' : '#oPass', 'demo1234');
  await page.click('button[type=submit]');
}

test.describe('sign in', () => {
  test('wrong password shows a helpful message', async ({ page }) => {
    await page.goto('/owner-auth');
    await page.fill('#oEmail', 'nadia@lacvert.farm');
    await page.fill('#oPass', 'nope-nope');
    await page.click('button[type=submit]');
    await expect(page.locator('#oErr')).toContainText('Wrong email or password');
  });

  test('a worker on the owner page is sent to team sign in', async ({ page }) => {
    await page.goto('/owner-auth');
    await page.fill('#oEmail', 'karim@lacvert.farm');
    await page.fill('#oPass', 'demo1234');
    await page.click('button[type=submit]');
    await expect(page.locator('#oErr')).toContainText('This is a worker account');
  });

  test('create-farm validation runs on submit', async ({ page }) => {
    await page.goto('/owner-auth');
    await page.click('[role=tab]:has-text("Create farm")');
    await page.click('button[type=submit]');
    await expect(page.locator('.field.invalid')).toHaveCount(5);
    await page.fill('#rName', 'Ana');
    await expect(page.locator('.field.invalid')).toHaveCount(4); // the error clears as soon as it is fixed
  });

  test('a protected page redirects to sign in', async ({ page }) => {
    await page.goto('/owner/alerts');
    await expect(page).toHaveURL(/owner-auth/);
    await expect(page.locator('.toast')).toContainText('Sign in');
  });
});

test.describe('owner', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, 'nadia@lacvert.farm');
    await expect(page.locator('#viewTitle')).toHaveText('Overview');
  });

  test('overview shows live farm data', async ({ page }) => {
    await expect(page.locator('.tickets .card')).toHaveCount(4);
    await expect(page.locator('.todo li')).toHaveCount(3);
    await expect(page.locator('.brow')).toHaveCount(4);
    await expect(page.locator('#clock')).toContainText('live');
  });

  test('resolve an alert with a note, then reopen it', async ({ page }) => {
    await page.click('nav >> text=Alerts');
    const first = page.locator('.alert').first();
    const title = (await first.locator('h4').textContent())!;
    await first.locator('.check').click();
    await page.click('.modal button[type=submit]');
    await expect(page.locator('.modal .field.invalid')).toBeVisible(); // a note is required
    await page.fill('#resNote', 'Ran the aerator and cut the evening feed');
    await page.click('.modal button[type=submit]');
    await expect(page.locator('.alert.just-done')).toBeVisible();
    await page.click('[role=tab]:has-text("Done")');
    const done = page.locator('.alert', { hasText: title });
    await expect(done.locator('.a-status')).toContainText('Resolved by Nadia Amrani');
    // survives a refresh
    await page.reload();
    await page.click('[role=tab]:has-text("Done")');
    await expect(page.locator('.alert', { hasText: title })).toBeVisible();
    await page.locator('.alert', { hasText: title }).locator('.check').click();
    await page.click('text=Reopen alert');
    await expect(page.locator('.toast')).toContainText('Reopened');
  });

  test('mark a report as read', async ({ page }) => {
    await page.click('nav >> text=Reports');
    const unread = page.locator('.report:not(.is-read)').first();
    await expect(unread).toBeVisible();
    await unread.locator('.read-btn').click();
    await expect(page.locator('.toast')).toContainText('Marked as read');
    await page.reload();
    await expect(page.locator('.report:not(.is-read)')).toHaveCount(0);
  });

  test('add a member, then that member can sign in', async ({ page, browser }) => {
    const email = `e2e-${Date.now()}@lacvert.farm`;
    await page.click('nav >> text=Team');
    await page.click('text=+ Add member');
    await page.fill('#mName', 'Test Worker');
    await page.fill('#mEmail', email);
    await page.fill('#mPass', 'farm-e2e-123');
    await page.click('text=Create account');
    await expect(page.locator('.toast')).toContainText('Account created');
    await expect(page.locator('td', { hasText: email })).toBeVisible();
    const other = await browser.newPage();
    await other.goto('/worker-auth');
    await other.fill('#tEmail', email);
    await other.fill('#tPass', 'farm-e2e-123');
    await other.click('button[type=submit]');
    await expect(other.locator('#viewTitle')).toHaveText('Today');
    await other.close();
  });

  test('changing a permission updates the member menu live', async ({ page, browser }) => {
    const worker = await browser.newPage();
    await signIn(worker, 'karim@lacvert.farm', true);
    await expect(worker.locator('nav >> text=Shift report')).toBeVisible();
    await page.click('nav >> text=Team');
    await page.locator('tr', { hasText: 'karim@lacvert.farm' }).locator('text=Edit permissions').click();
    await page.click('.sheet [role=switch][aria-label=Reports]');
    await expect(page.locator('.toast')).toContainText('can no longer see reports');
    await expect(worker.locator('nav >> text=Shift report')).toHaveCount(0); // pushed over the WebSocket
    await page.click('.sheet [role=switch][aria-label=Reports]');
    await expect(worker.locator('nav >> text=Shift report')).toBeVisible();
    await worker.close();
  });

  test('assistant answers in demo mode and creates a task after approval', async ({ page }) => {
    await page.click('text=Ask the farm');
    await expect(page.locator('.demo-banner')).toBeVisible();
    await page.click('.ai-empty .chip:has-text("Why did oxygen drop in Basin 3")');
    await expect(page.locator('.msg-ai .stepchip').first()).toBeVisible();
    await expect(page.locator('.msg-ai .chart svg')).toBeVisible();
    await expect(page.locator('.msg-ai .src').first()).toBeVisible();
    await page.click('text=Approve and create task');
    await expect(page.locator('.approve.done')).toContainText('Task created');
    await page.click('.fb button[aria-label=Useful]');
    await expect(page.locator('.fb button[aria-label=Useful]')).toHaveAttribute('aria-pressed', 'true');
  });
});

test.describe('worker', () => {
  test('send a shift report', async ({ page }) => {
    await signIn(page, 'karim@lacvert.farm', true);
    await page.click('nav >> text=Shift report');
    await page.click('button:has-text("Send report")');
    await expect(page.locator('.field.invalid')).toHaveCount(2);
    const title = `E2E morning shift ${Date.now()}`;
    await page.fill('#srTitle', title);
    await page.fill('#srBody', 'All basins checked, fish fed normally.');
    await page.click('button:has-text("Send report")');
    await expect(page.locator('.toast')).toContainText("owner's inbox");
    await expect(page.getByText(title)).toBeVisible();
  });
});

test.describe('technician', () => {
  test('sensor health and maintenance log', async ({ page }) => {
    await signIn(page, 'samir@lacvert.farm', true);
    await expect(page.locator('#viewTitle')).toHaveText('Today');
    await page.click('nav >> text=Sensor health');
    await expect(page.locator('tbody tr')).toHaveCount(12);
    await expect(page.locator('.badge', { hasText: 'Stuck' })).toBeVisible();
    await page.click('nav >> text=Maintenance');
    await page.fill('#mtDue', '2026-12-01');
    await page.fill('#mtDesc', 'Calibrated with buffers 7 and 10.');
    await page.click('text=Save log');
    await expect(page.locator('.toast')).toContainText("owner's reports");
  });
});

test.describe('new owner', () => {
  test('creates a farm, adds the first basin', async ({ page }) => {
    await page.goto('/owner-auth');
    await page.click('[role=tab]:has-text("Create farm")');
    await page.fill('#rName', 'New Owner');
    await page.fill('#rEmail', `owner-${Date.now()}@example.com`);
    await page.fill('#rPass', 'longenough1');
    await page.fill('#rFarm', 'E2E Farm');
    await page.fill('#rCo', 'E2E Co');
    await page.click('button[type=submit]');
    await expect(page.locator('text=Add your first basin.')).toBeVisible();
    await page.click('button:has-text("Add your first basin")');
    await page.fill('#bName', 'Pond 1');
    await page.fill('#bCap', '120');
    await page.fill('#bFish', '2000');
    await page.click('text=Add basin');
    await expect(page.locator('.toast', { hasText: 'Basin added' })).toBeVisible();
    await page.click('nav >> text=Basins');
    await expect(page.locator('.basin-card h3')).toHaveText('Pond 1');
  });
});
