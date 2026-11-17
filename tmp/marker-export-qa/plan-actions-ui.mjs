import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  const request = { table_length_m: '8', min_plies: 10, time_limit_seconds: 20,
    orders: [{ label: '355800', size_rows: [{ size: 'S', quantity: '10' }] }],
    materials: [{ material_code: 'R1845', placement: 'Main Fabric', consumption: '0.89', unit: 'm', max_plies: 120 }] };
  const plan = { id: 'original-plan', status: 'complete', saved: true, created_at: '2026-10-27T03:00:00Z',
    sizes: ['S'], quantities: [10], total_quantity: 10, order_labels: ['355800'], warnings: [],
    settings: request, request, summary: { complete: true, marker_count: 1, lay_count: 1, failed: 0 }, materials: [] };
  let deleted = false, failDelete = false, failCreate = true, editable = true, active = false, payload, deletes = 0;
  await page.addInitScript(() => localStorage.setItem('auth_token', 'isolated-test-token'));
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    let body = [];
    if (path === '/api/auth/me') body = { user: { full_name: 'Reviewer', permissions: { marker_plan: editable ? 'edit' : 'view' } } };
    if (path === '/api/marker-plans') {
      if (req.method() === 'POST') {
        if (failCreate) return route.fulfill({ status: 503, json: { detail: 'Test start unavailable' } });
        payload = req.postDataJSON(); body = { ...plan, id: 'new-plan' };
      } else body = deleted ? [] : [{ ...plan, status: active ? 'running' : 'complete', material_count: 1 }];
    }
    if (path === '/api/marker-plans/original-plan' && req.method() === 'DELETE') {
      deletes++;
      if (failDelete) return route.fulfill({ status: 503, json: { detail: 'Test delete unavailable' } });
      deleted = true; body = { ok: true };
    } else if (path === '/api/marker-plans/original-plan') body = plan;
    if (path === '/api/marker-plans/new-plan') body = { ...plan, id: 'new-plan' };
    if (path.endsWith('/rerun-settings')) body = { request: { ...request, materials: [{ ...request.materials[0], max_plies: 60 }] }, notes: [] };
    await route.fulfill({ json: body });
  });
  async function history() {
    await page.goto('http://localhost:5173/?tab=plan');
    await page.getByRole('link', { name: 'Open', exact: true }).waitFor();
  }
  await history();
  await page.getByRole('link', { name: 'Run again', exact: true }).click();
  await page.getByRole('heading', { name: 'Run again', exact: true }).waitFor();
  const ply = page.getByLabel('Maximum plies for material 1', { exact: true });
  assert.equal(await ply.inputValue(), '60');
  await ply.fill('55');
  await page.getByLabel('Table length (m)', { exact: true }).fill('10');
  await page.getByRole('button', { name: 'Generate new plan', exact: true }).click();
  await page.getByText('Test start unavailable', { exact: true }).waitFor();
  assert.equal(await ply.inputValue(), '55');
  failCreate = false;
  await page.getByRole('button', { name: 'Generate new plan', exact: true }).click();
  await page.waitForURL('**/marker-plans/new-plan');
  assert.equal(payload.materials[0].max_plies, 55);
  assert.equal(payload.table_length_m, '10');
  assert.deepEqual(payload.orders, request.orders);
  assert.equal(request.materials[0].max_plies, 120);
  await history();
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.equal(deletes, 0);
  failDelete = true;
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete plan', exact: true }).click();
  await page.getByText('Test delete unavailable', { exact: true }).waitFor();
  assert.equal(await page.getByRole('link', { name: 'Open', exact: true }).count(), 1);
  failDelete = false;
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete plan', exact: true }).click();
  await page.getByText('No saved plans yet. Generate a cutting plan to save your first result.', { exact: true }).waitFor();
  deleted = false; editable = false;
  await history();
  assert.equal(await page.getByRole('button', { name: 'Delete', exact: true }).count(), 0);
  assert.equal(await page.getByRole('link', { name: 'Run again', exact: true }).count(), 0);
  editable = true; active = true;
  await history();
  assert.equal(await page.getByRole('button', { name: 'Delete', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Run again', exact: true }).isDisabled(), true);
  assert.deepEqual(errors, []);
  console.log('PASS: rerun current plies/review/settings/new generation/failure retention, delete confirm/cancel/failure/success, view-only and active-job protection. No live records changed.');
} finally { await browser.close(); }
