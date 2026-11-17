import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const job = { id: 'saved-plan-test', status: 'complete', saved: true, created_at: '2026-10-27T03:00:00Z',
    sizes: ['S'], quantities: [10], total_quantity: 10, order_labels: ['361061'], warnings: [],
    settings: { time_limit_seconds: 20 }, summary: { complete: true, marker_count: 1, lay_count: 1, failed: 0 }, materials: [] };
  let failLoad = false, allowed = true, running = false, loads = 0, downloads = 0;
  await page.addInitScript(() => localStorage.setItem('auth_token', 'isolated-test-token'));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body = [];
    if (path === '/api/auth/me') body = { user: { full_name: 'Plan reviewer', permissions: { marker_plan: allowed ? 'view' : undefined } } };
    if (path === '/api/marker-plans') body = [{ ...job, material_count: 1, tech_pack_filename: 'Saved BOM.pdf' }];
    if (path === '/api/marker-plans/saved-plan-test') {
      loads++;
      assert.equal(request.headers().authorization, 'Bearer isolated-test-token');
      if (failLoad) return route.fulfill({ status: 404, json: { detail: 'Saved plan not found' } });
      body = running ? { ...job, status: 'running', summary: { complete: false }, materials: [] } : job;
    }
    if (path.endsWith('/excel')) {
      downloads++;
      assert.equal(request.headers().authorization, 'Bearer isolated-test-token');
      return route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: Buffer.from('isolated download check') });
    }
    return route.fulfill({ json: body });
  });
  await page.goto('http://localhost:5173/?tab=plan');
  const row = page.getByRole('row').filter({ hasText: '361061' });
  const open = row.getByRole('link', { name: 'Open', exact: true });
  await open.waitFor();
  assert.equal(await open.getAttribute('href'), '/marker-plans/saved-plan-test');
  assert.equal(await page.locator('.saved-plan-opened').count(), 0);
  await open.click();
  await page.waitForURL('**/marker-plans/saved-plan-test');
  await page.getByText('Saved to database', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Refresh saved plans' }).count(), 0);
  await page.reload();
  await page.getByText('Saved to database', { exact: true }).waitFor();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'Download Excel', exact: true }).click()]);
  assert.equal(await download.failure(), null);
  assert.equal(downloads, 1);
  await page.screenshot({ path: 'tmp/marker-export-qa/saved-plan-page-ui.png', fullPage: true });
  await page.getByRole('link', { name: 'Back to Marker Plan', exact: true }).click();
  await page.waitForURL('**/?tab=plan');
  assert.equal(await page.getByRole('tab', { name: 'Marker Plan', exact: true }).getAttribute('aria-selected'), 'true');
  await page.getByRole('link', { name: 'Open', exact: true }).waitFor();
  await page.goBack();
  await page.waitForURL('**/marker-plans/saved-plan-test');
  await page.getByText('Saved to database', { exact: true }).waitFor();
  failLoad = true;
  await page.reload();
  await page.getByText(/Could not load the saved plan: Saved plan not found/).waitFor();
  assert.equal(await page.getByRole('link', { name: 'Back to Marker Plan', exact: true }).isVisible(), true);
  failLoad = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await page.getByText('Saved to database', { exact: true }).waitFor();
  running = true;
  await page.reload();
  await page.locator('.plan-running').waitFor();
  const beforePoll = loads;
  running = false;
  await page.getByText('Saved to database', { exact: true }).waitFor();
  assert.ok(loads > beforePoll, 'running plans refresh to completion');
  allowed = false;
  const beforeDenied = loads;
  await page.reload();
  await page.getByRole('heading', { name: 'No access', exact: true }).waitFor();
  assert.equal(loads, beforeDenied);
  assert.deepEqual(errors, []);
  console.log('PASS: dedicated page, direct refresh, back to Marker Plan, browser history, authenticated download, missing-plan retry/back, running-plan polling and view permission; no live data changed.');
} finally { await browser.close(); }
