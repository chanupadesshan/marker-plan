import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const plan = JSON.parse(await fs.readFile(`${root}/${process.argv[2] || 'output/marker-plan-03/saved-plan.json'}`, 'utf8'));
const env = Object.fromEntries((await fs.readFile(`${root}/.env`, 'utf8')).split(/\r?\n/).map(line => {
  const match = line.match(/^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$/);
  return match ? [match[1], match[2].replace(/^(['"])(.*)\1$/, '$2')] : ['', ''];
}));
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const login = await page.request.post('http://127.0.0.1:8000/api/auth/login', { data: {
    email: env.ADMIN_EMAIL || env.admin_email, password: env.ADMIN_PASSWORD || env.admin_password } });
  assert.ok(login.ok(), 'Test login failed');
  const { token } = await login.json();
  await page.addInitScript(value => localStorage.setItem('auth_token', value), token);
  await page.goto(`http://localhost:5173/marker-plans/${plan.id}`);
  await page.getByRole('heading', { name: plan.order_labels.join(', '), exact: true }).waitFor();
  await page.getByText('Saved to database', { exact: true }).waitFor();
  assert.equal(await page.locator('.plan-material').count(), plan.materials.length);
  assert.equal(await page.getByText(`${plan.total_quantity} garments`, { exact: true }).count(), 1);
  assert.equal(await page.getByText(`${plan.sizes.length} sizes`, { exact: true }).count(), 1);
  assert.equal(await page.getByText(`Capacity ${plan.materials[0].capacity} sets per marker (estimated)`, { exact: true }).count(), 1);
  assert.equal(await page.getByRole('link', { name: 'Download Excel', exact: true }).count(), 1);
  await page.screenshot({ path: `${root}/tmp/marker-export-qa/${plan.order_labels[0]}-saved-plan-ui.png`, fullPage: true });
  console.log(`PASS: real saved plan page shows contract ${plan.order_labels[0]}, ${plan.total_quantity} garments, ${plan.sizes.length} sizes, all material groups, correct capacity, and Excel download.`);
} finally { await browser.close(); }
