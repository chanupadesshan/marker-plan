import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let editable = true, failSave = true, saved;
  const row = { material_code: 'R1514', developer_code: 'R1514', description: 'Original fabric', composition: '75% cotton',
    placement_type: 'Shell 1', placement: 'Body', quantity: '1.65', unit: 'm', source_pages: [1],
    colorways: [{ code: '8933', name: 'Navy', material_color_code: '8904', material_color_name: 'Navy', fabric_reference: 'keep-ref' }] };
  const doc = { id: 'test-bom', filename: 'BOM editor test.pdf', status: 'approved', page_count: 2, selected_pages: [1, 2],
    extraction: { category: 'Wovens', style_number: '1478', tech_pack_number: 'TP 24409', warnings: [], source_pages: [1, 2],
      materials: [row, { ...row, source_pages: [2] }], page_tables: [1, 2].map(page_number => ({ page_number,
        materials: [{ ...structuredClone(row), source_pages: [page_number] }], colorway_headers: [{ code: '8933', name: 'Navy' }] })) } };
  await page.addInitScript(() => localStorage.setItem('auth_token', 'isolated-browser-test'));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path === '/api/auth/me') body = { user: { full_name: 'Review user', permissions: { techpacks: editable ? 'edit' : 'view' } } };
    if (path === '/api/documents') body = [doc];
    if (path === '/api/documents/test-bom') body = doc;
    if (path === '/api/documents/test-bom/extraction') {
      if (failSave) return route.fulfill({ status: 500, json: { detail: 'Test save unavailable' } });
      saved = route.request().postDataJSON();
      doc.extraction = { ...saved, materials: saved.page_tables.flatMap(table => table.materials) };
      doc.status = 'needs_review'; body = { ok: true, status: 'needs_review' };
    }
    await route.fulfill({ json: body });
  });
  async function open() {
    await page.goto('http://localhost:5173');
    await page.locator('button.document-entry').filter({ hasText: 'BOM editor test.pdf' }).click();
  }
  await open();
  await page.getByRole('button', { name: 'Edit BOM', exact: true }).click();
  assert.equal(await page.getByRole('button', { name: 'Approved', exact: true }).isDisabled(), true);
  const code = page.getByLabel('Material code, table 1, row 1', { exact: true });
  await code.fill('changed');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Edit BOM', exact: true }).click();
  assert.equal(await code.inputValue(), 'R1514');
  await page.getByRole('button', { name: 'Add row', exact: true }).first().click();
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Enter a material code.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Remove material row 2 from table 1' }).click();
  await page.getByLabel('Description, table 1, row 1', { exact: true }).fill('Corrected fabric');
  const colours = page.locator('.bom-colour-cell').first();
  await colours.locator('summary').click();
  await colours.getByLabel('Material colour code', { exact: true }).fill('9999');
  await colours.getByRole('button', { name: 'Add colour', exact: true }).click();
  await colours.getByRole('button', { name: 'Remove colour', exact: true }).last().click();
  await colours.locator('summary').click();
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Test save unavailable', { exact: true }).waitFor();
  assert.equal(await page.getByLabel('Description, table 1, row 1', { exact: true }).inputValue(), 'Corrected fabric');
  await page.screenshot({ path: 'tmp/marker-export-qa/bom-editor-ui.png', fullPage: true });
  failSave = false;
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByText('Changes saved. Review the corrected BOM, then approve it.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Approve BOM', exact: true }).isEnabled(), true);
  assert.equal(saved.page_tables[0].materials[0].description, 'Corrected fabric');
  assert.equal(saved.page_tables[1].materials[0].description, 'Original fabric');
  assert.equal(saved.page_tables[0].materials[0].colorways[0].fabric_reference, 'keep-ref');
  assert.equal(saved.page_tables[0].materials[0].colorways[0].material_color_code, '9999');
  assert.equal(saved.page_tables[0].materials[0].colorways.length, 1);
  assert.equal('materials' in saved, false);
  assert.equal(await page.getByRole('button', { name: 'Edit JSON', exact: true }).count(), 0);
  editable = false;
  await open();
  assert.equal(await page.getByRole('button', { name: 'Edit BOM', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Approve BOM', exact: true }).isDisabled(), true);
  assert.deepEqual(errors, []);
  console.log('PASS: two-page editing, cancel, add/remove, validation, save failure draft retention, corrected payload, reapproval, view-only permissions; no live data changed.');
} finally { await browser.close(); }
