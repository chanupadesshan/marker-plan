import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let editable = true, failSave = true, saved;
  const order = { contract_number: '355800', tech_pack_reference: '16926', model_id: '1449', quality_id: '1845', color_id: '8699',
    total_quantity: '1,410', source_pages: [2], warnings: [],
    size_rows: [30,90,210,240,330,270,150,30,30,30].map((quantity, index) => ({ size: `C${44 + index * 2}`, quantity: String(quantity), source_page: 2 })) };
  const doc = { id: 'test-po', filename: 'PO editor test.pdf', status: 'approved', page_count: 2, approval_ready: true,
    extraction: { orders: [order, { ...structuredClone(order), contract_number: 'Other contract' }],
      processing_complete: true, page_results: [{ page_number: 2, result: { page_kind: 'purchase_order' } }], warnings: [] } };
  await page.addInitScript(() => localStorage.setItem('auth_token', 'isolated-browser-test'));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path === '/api/auth/me') body = { user: { full_name: 'PO review user', permissions: { purchase_orders: editable ? 'edit' : 'view' } } };
    if (path === '/api/purchase-orders') body = [doc];
    if (path === '/api/purchase-orders/test-po') body = doc;
    if (path === '/api/purchase-orders/test-po/extraction') {
      if (failSave) return route.fulfill({ status: 500, json: { detail: 'Test save unavailable' } });
      saved = route.request().postDataJSON();
      doc.extraction.orders = saved.orders; doc.status = 'needs_review';
      body = { ok: true, status: 'needs_review' };
    }
    await route.fulfill({ json: body });
  });
  async function open() {
    await page.goto('http://localhost:5173');
    await page.getByRole('tab', { name: /^Purchase Order/ }).click();
    await page.locator('button.document-entry').filter({ hasText: 'PO editor test.pdf' }).click();
    await page.getByRole('heading', { name: 'PO editor test.pdf', exact: true }).waitFor();
  }
  await open();
  await page.getByRole('button', { name: 'Edit PO', exact: true }).click();
  const model = page.getByLabel('Model ID, contract 1', { exact: true });
  await model.fill('Cancelled edit');
  assert.equal(await page.getByRole('button', { name: 'Approved', exact: true }).isDisabled(), true);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Edit PO', exact: true }).click();
  assert.equal(await model.inputValue(), '1449');
  assert.equal(await page.locator('.po-size-total').first().innerText(), 'Size quantity sum: 1410');
  await page.getByRole('button', { name: 'Add size row', exact: true }).first().click();
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Enter a size.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Remove size row 11 from contract 1', exact: true }).click();
  await page.getByRole('button', { name: 'Add contract', exact: true }).click();
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Enter a contract number.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Remove contract 3', exact: true }).click();
  await page.getByLabel('Quantity, contract 1, row 1', { exact: true }).fill('31');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Size quantities add up to 1411. Check the total and size rows.', { exact: true }).waitFor();
  await page.getByLabel('Total quantity, contract 1', { exact: true }).fill('1,411');
  await model.fill('Corrected model');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Test save unavailable', { exact: true }).waitFor();
  assert.equal(await model.inputValue(), 'Corrected model');
  await page.screenshot({ path: 'tmp/marker-export-qa/po-editor-ui.png', fullPage: true });
  failSave = false;
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Changes saved. Review the corrected purchase order, then approve it.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Approve PO', exact: true }).first().isEnabled(), true);
  assert.deepEqual(Object.keys(saved), ['orders']);
  assert.equal(saved.orders[0].model_id, 'Corrected model');
  assert.equal(saved.orders[0].total_quantity, '1,411');
  assert.equal(saved.orders[0].size_rows[0].source_page, 2);
  assert.equal(saved.orders[1].model_id, '1449');
  assert.equal(doc.extraction.processing_complete, true);
  assert.equal(await page.getByRole('button', { name: 'Edit PO JSON', exact: true }).count(), 0);
  editable = false;
  await open();
  assert.equal(await page.getByRole('button', { name: 'Edit PO', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Approve PO', exact: true }).first().isDisabled(), true);
  editable = true; doc.status = 'processing';
  await open();
  assert.equal(await page.getByRole('button', { name: 'Edit PO', exact: true }).count(), 0);
  assert.deepEqual(errors, []);
  console.log('PASS: PO contract/size editing, 355800 grouped total, cancel, add/remove rows/contracts, mismatch validation, save failure retention, corrected payload, reapproval and permissions; no live data changed.');
} finally { await browser.close(); }
